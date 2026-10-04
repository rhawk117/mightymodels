"""Root-contained filesystem access and external command dispatch shared by every use case."""

import asyncio
import shutil
import subprocess
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from itertools import chain
from os import PathLike
from pathlib import Path
from typing import NotRequired, Protocol, TypedDict, Unpack
from urllib.parse import urlparse
from urllib.request import url2pathname

from mcp.shared.exceptions import MCPError
from mcp_types import ListRootsResult

CONTAINMENT_ERROR = 'Path must be inside the workspace'
DATA_DIRECTORY = '.__NAME__'


class RootsSession(Protocol):
    async def list_roots(self) -> ListRootsResult: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class ContainedPath:
    absolute: Path
    relative: str


class CommandDispatch(TypedDict):
    arguments: Sequence[str]
    cwd: Path
    timeout: NotRequired[int]


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandResult:
    succeeded: bool
    stdout: str = ''
    stderr: str = ''
    error: str | None = None


def timeout_result(error: subprocess.TimeoutExpired, message: str) -> CommandResult:
    return CommandResult(
        succeeded=False,
        stdout=_output_text(error.stdout),
        stderr=_output_text(error.stderr),
        error=message,
    )


def captured_result(result: subprocess.CompletedProcess[str]) -> CommandResult:
    succeeded = result.returncode == 0
    return CommandResult(
        succeeded=succeeded,
        stdout=result.stdout,
        stderr=result.stderr,
        error=None if succeeded else f'error: {result.stderr}',
    )


def contains_extension(directory: Path, extension: str, *, max_depth: int = 20) -> bool:
    extension = extension.removeprefix('.')
    return any(
        path.is_file()
        for path in chain.from_iterable(
            directory.glob(f'{"*/" * depth}*.{extension}') for depth in range(max_depth + 1)
        )
    )


def resolve_contained(parent: Path, *, path: str) -> ContainedPath:
    parent = parent.resolve(strict=True)
    absolute = parent.joinpath(path).resolve(strict=True)

    try:
        relative_path = absolute.relative_to(parent)
    except ValueError as error:
        raise ValueError(CONTAINMENT_ERROR) from error

    return ContainedPath(absolute=absolute, relative=relative_path.as_posix())


def resolve_relative(parent: Path, *, path: str) -> ContainedPath:
    directory = resolve_contained(parent, path=path)

    if not directory.absolute.is_dir():
        message = f'{path} is not a directory'
        raise ValueError(message)

    return directory


def resolve_relative_file(parent: Path, *, path: str) -> ContainedPath:
    file = resolve_contained(parent, path=path)

    if not file.absolute.is_file():
        message = f'{path} is not a file'
        raise ValueError(message)

    return file


def _output_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors='replace')

    return value or ''


@dataclass(slots=True, kw_only=True, frozen=True)
class WorkspaceTool:
    binary: str
    timeout: int = 5

    def execute(self, **request: Unpack[CommandDispatch]) -> CommandResult:
        timeout = request.get('timeout', self.timeout)

        try:
            result = subprocess.run(  # noqa: S603 arguments come from use cases, never from the model verbatim
                [self.binary, *request['arguments']],
                capture_output=True,
                check=False,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=request['cwd'],
                timeout=timeout,
            )
        except FileNotFoundError as error:
            return CommandResult(succeeded=False, error=f'Could not start {self.binary}: {error}')
        except subprocess.TimeoutExpired as error:
            return timeout_result(error, f'{self.binary} command timed out after {timeout} seconds')

        return captured_result(result)

    def available(self) -> bool:
        return shutil.which(self.binary) is not None


class WorkspaceCommandDispatch(TypedDict):
    binary: str
    arguments: Sequence[str]
    timeout: NotRequired[int]
    relative_cwd: NotRequired[str]


@dataclass(slots=True, kw_only=True, frozen=True)
class RepositoryWorkspace:
    workspace_tools: dict[str, WorkspaceTool]
    root: Path = field(default_factory=Path.cwd)

    def get_tools(self, *tool_names: str) -> Sequence[WorkspaceTool]:
        return [self.workspace_tools[name] for name in tool_names]

    def missing_tools(self) -> Sequence[str]:
        return [name for name, tool in self.workspace_tools.items() if not tool.available()]

    def contains_extension(self, extension: str) -> bool:
        return contains_extension(self.root, extension)

    def resolve_relative(self, relative: str | PathLike[str]) -> ContainedPath:
        return resolve_relative(self.root, path=str(relative))

    def resolve_relative_file(self, relative: str | PathLike[str]) -> ContainedPath:
        return resolve_relative_file(self.root, path=str(relative))

    def resolve_relative_path(self, relative: str | PathLike[str]) -> ContainedPath:
        return resolve_contained(self.root, path=str(relative))

    def data_directory(self) -> Path:
        return self.root.joinpath(DATA_DIRECTORY)

    def execute_tool(self, **dispatch: Unpack[WorkspaceCommandDispatch]) -> CommandResult:
        command = self.workspace_tools[dispatch['binary']]
        cwd = self.root

        if relative := dispatch.get('relative_cwd'):
            cwd = self.resolve_relative(relative).absolute

        return command.execute(
            arguments=dispatch['arguments'],
            cwd=cwd,
            timeout=dispatch.get('timeout', command.timeout),
        )

    def execute_dispatch(self, dispatch: WorkspaceCommandDispatch) -> CommandResult:
        return self.execute_tool(**dispatch)

    async def execute_concurrently(
        self,
        *tool_calls: WorkspaceCommandDispatch,
    ) -> tuple[CommandResult, ...]:
        async with asyncio.TaskGroup() as task_group:
            futures = [
                task_group.create_task(
                    asyncio.to_thread(self.execute_dispatch, dispatch),
                    name=f'__NAME__:workspace:{index}:{dispatch["binary"]}',
                )
                for index, dispatch in enumerate(tool_calls)
            ]

        return tuple(future.result() for future in futures)

    @contextmanager
    def relative_workspace(self, relative: str = '.') -> Generator['RepositoryWorkspace']:
        if relative == '.':
            yield self
            return

        relative_path = self.resolve_relative(relative)
        yield RepositoryWorkspace(workspace_tools=self.workspace_tools, root=relative_path.absolute)


def current_workspace(
    *workspace_tools: WorkspaceTool, root: Path | None = None
) -> RepositoryWorkspace:
    tools = {tool.binary: tool for tool in workspace_tools}
    return RepositoryWorkspace(workspace_tools=tools, root=(root or Path.cwd()).resolve())


async def listed_root(session: RootsSession) -> Path | None:
    try:
        listing = await session.list_roots()
    except MCPError:
        return None

    found = None
    for root in listing.roots:
        path = Path(url2pathname(urlparse(str(root.uri)).path))
        if await asyncio.to_thread(path.is_dir):
            found = path
            break

    return found
