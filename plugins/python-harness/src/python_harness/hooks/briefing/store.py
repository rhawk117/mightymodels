"""The project's files as one scan reads them: bounded, fail-soft, nearest first."""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path, PurePath, PurePosixPath
from types import MappingProxyType

from python_harness.core.files import describe_os_error
from python_harness.core.workspace import find_search_boundary, list_ancestors_to
from python_harness.hooks.briefing.domain import (
    ConfigTable,
    IniRead,
    MissingFile,
    PackageFacts,
    ScanOptions,
    TextFile,
    TextRead,
    TomlDocument,
    TomlRead,
    UnreadableFile,
)
from python_harness.hooks.briefing.policy import (
    classify_declaration,
    is_workspace_member,
)
from python_harness.hooks.briefing.util.configs import parse_locked_versions
from python_harness.hooks.briefing.util.parsing import (
    decode_text,
    parse_ini,
    parse_toml,
)
from python_harness.hooks.domain import SEARCH_BOUNDARY_MARKERS
from python_harness.survey.domain import PYPROJECT, UV_LOCK, ProjectManifest
from python_harness.survey.util import manifest_from_document, read_nested_table

EMPTY_TABLE: ConfigTable = MappingProxyType({})
UV_WORKSPACE_TABLE = ('tool', 'uv', 'workspace')


def read_prefix(path: Path, max_bytes: int) -> bytes:
    with path.open('rb') as stream:
        return stream.read(max_bytes + 1)


def read_text(path: Path, label: str, max_bytes: int) -> TextRead:
    if not path.is_file():
        return MissingFile()
    try:
        content = read_prefix(path, max_bytes)
    except OSError as error:
        return UnreadableFile(label, f'cannot be read: {describe_os_error(error)}')
    if len(content) > max_bytes:
        return UnreadableFile(label, f'is larger than {max_bytes} bytes')
    return decode_text(content, label)


def read_toml(path: Path, label: str, max_bytes: int) -> TomlRead:
    read = read_text(path, label, max_bytes)
    if not isinstance(read, TextFile):
        return read
    return parse_toml(read.text, label)


def read_ini(path: Path, label: str, max_bytes: int) -> IniRead:
    read = read_text(path, label, max_bytes)
    if not isinstance(read, TextFile):
        return read
    return parse_ini(read.text, label)


def has_file(directory: Path, name: str) -> bool:
    return directory.joinpath(name).is_file()


def has_directory(directory: Path, name: str) -> bool:
    return directory.joinpath(name).is_dir()


def relative_label(path: Path, root: Path) -> str:
    return PurePath(os.path.relpath(path, root)).as_posix()


def holds_any_file(directory: Path, names: tuple[str, ...]) -> bool:
    return any(has_file(directory, name) for name in names)


def manifest_of(read: TomlRead | None) -> ProjectManifest | None:
    if not isinstance(read, TomlDocument):
        return None
    return manifest_from_document(read.table)


def table_of(read: TomlRead | None) -> ConfigTable:
    if isinstance(read, TomlDocument):
        return read.table
    return EMPTY_TABLE


@dataclass(frozen=True, slots=True)
class ScanContext:
    root: Path
    boundary: Path
    directories: tuple[Path, ...]
    project_directories: tuple[Path, ...]
    pyprojects: Mapping[Path, TomlRead]
    manifest: ProjectManifest | None
    lock: TomlRead
    locked_versions: Mapping[str, str]
    options: ScanOptions
    variables: Mapping[str, str]

    def pyproject_table(self, directory: Path) -> ConfigTable:
        return table_of(self.pyprojects.get(directory))

    def package(self, name: str) -> PackageFacts:
        declaration = classify_declaration(self.manifest, name)
        return PackageFacts(name, declaration, self.locked_versions.get(name))

    def display(self, path: Path) -> str:
        return relative_label(path, self.root)

    def read_toml(self, path: Path) -> TomlRead:
        return read_toml(path, self.display(path), self.options.max_file_bytes)

    def read_ini(self, path: Path) -> IniRead:
        return read_ini(path, self.display(path), self.options.max_file_bytes)

    def find_directory(self, contains: Callable[[Path], bool]) -> Path | None:
        return next((path for path in self.directories if contains(path)), None)

    def find_project_directory(self, contains: Callable[[Path], bool]) -> Path | None:
        found = (path for path in self.project_directories if contains(path))
        return next(found, None)

    @property
    def dependency_directory(self) -> Path | None:
        names = self.options.dependency_file_names
        return self.find_project_directory(partial(holds_any_file, names=names))


def read_pyprojects(
    directories: tuple[Path, ...], root: Path, max_bytes: int
) -> Mapping[Path, TomlRead]:
    paths = ((directory, directory.joinpath(PYPROJECT)) for directory in directories)
    reads = {
        directory: read_toml(path, relative_label(path, root), max_bytes)
        for directory, path in paths
    }
    return MappingProxyType(reads)


def find_workspace_root(
    root: Path, directories: tuple[Path, ...], pyprojects: Mapping[Path, TomlRead]
) -> Path:
    candidates = (
        directory
        for directory in directories[1:]
        if is_workspace_member(
            read_nested_table(table_of(pyprojects.get(directory)), *UV_WORKSPACE_TABLE),
            PurePosixPath(root.relative_to(directory).as_posix()),
        )
    )
    return next(candidates, root)


def find_root(start: Path) -> tuple[Path, Path]:
    boundary = find_search_boundary(start, SEARCH_BOUNDARY_MARKERS)
    reachable = list_ancestors_to(start, boundary)
    root = next((path for path in reachable if has_file(path, PYPROJECT)), start)
    return root, boundary


def read_workspace_lock(workspace_root: Path, root: Path, options: ScanOptions) -> TomlRead:
    path = workspace_root.joinpath(UV_LOCK)
    return read_toml(path, relative_label(path, root), options.max_file_bytes)


def open_scan_context(cwd: Path, options: ScanOptions, variables: Mapping[str, str]) -> ScanContext:
    root, boundary = find_root(cwd.absolute())
    directories = list_ancestors_to(root, boundary)
    pyprojects = read_pyprojects(directories, root, options.max_file_bytes)
    workspace_root = find_workspace_root(root, directories, pyprojects)
    lock = read_workspace_lock(workspace_root, root, options)
    return ScanContext(
        root=root,
        boundary=boundary,
        directories=directories,
        project_directories=list_ancestors_to(root, workspace_root),
        pyprojects=pyprojects,
        manifest=manifest_of(pyprojects.get(root)),
        lock=lock,
        locked_versions=parse_locked_versions(table_of(lock)),
        options=options,
        variables=variables,
    )
