"""The git queries answered by running `git -C <root>` through a `ProcessRunner`.

Every operation waits at most `timeout` seconds, 30 unless the caller says otherwise. A revision
or branch name is checked before any process starts.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mightymodels_core.process import FailedRun, get_process_runner

from .errors import GitUnavailableError, NotARepositoryError
from .records import Checkout, GitAnswer, unanswered_error
from .revisions import revision_error

if TYPE_CHECKING:
    from mightymodels_core.process import ProcessRunner

    from .errors import GitRefusal
    from .queries import Git
    from .records import UntrackedFiles

GIT_EXECUTABLE = 'git'
GIT_NOT_FOUND = 'no git executable is on PATH'
GIT_TIMEOUT_SECONDS = 30


@dataclass(slots=True, kw_only=True, frozen=True)
class GitCommand:
    root: Path
    executable: str | None
    processes: ProcessRunner
    timeout: float = GIT_TIMEOUT_SECONDS

    async def answer(self, *arguments: str) -> GitAnswer:
        if self.executable is None:
            return GitAnswer(exit=None, stdout='', stderr=GIT_NOT_FOUND, failure='not_found')

        argv = [self.executable, '-C', str(self.root), *arguments]
        run = await self.processes.run(argv, timeout=self.timeout)
        if isinstance(run, FailedRun):
            return GitAnswer(exit=None, stdout='', stderr=run.detail, failure=run.kind)

        return GitAnswer(exit=run.exit, stdout=run.stdout, stderr=run.stderr, failure=None)


def checkout_of(toplevel: str, origin: GitAnswer) -> Checkout:
    url = origin.stdout.removesuffix('\n')
    return Checkout(
        toplevel=Path(toplevel.removesuffix('\n')).resolve(),
        origin_url=url if origin.exit == 0 and url else None,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ProcessGit:
    command: GitCommand

    async def refusal(self) -> GitRefusal | None:
        answer = await self.command.answer('rev-parse', '--git-dir')
        if (unanswered := unanswered_error(answer)) is not None:
            return unanswered

        if answer.exit != 0:
            return NotARepositoryError(root=self.command.root, detail=answer.stderr.strip())

        return None

    async def checkout(self) -> Checkout | GitRefusal:
        toplevel = await self.command.answer('rev-parse', '--show-toplevel')
        if (unanswered := unanswered_error(toplevel)) is not None:
            return unanswered

        if toplevel.exit != 0:
            return NotARepositoryError(root=self.command.root, detail=toplevel.stderr.strip())

        origin = await self.command.answer('config', '--get', 'remote.origin.url')
        if (unanswered := unanswered_error(origin)) is not None:
            return unanswered

        return checkout_of(toplevel.stdout, origin)

    async def common_directory(self) -> Path | None:
        answer = await self.command.answer(
            'rev-parse', '--path-format=absolute', '--git-common-dir'
        )
        return Path(answer.stdout.strip()) if answer.exit == 0 else None

    async def resolve_head(self) -> str | None:
        answer = await self.command.answer('rev-parse', '--verify', '--quiet', 'HEAD')
        return answer.stdout.strip() if answer.exit == 0 else None

    async def resolve_commit(self, revision: str) -> str | None:
        if (error := revision_error(revision)) is not None:
            raise error

        answer = await self.command.answer(
            'rev-parse', '--verify', '--quiet', f'{revision}^{{commit}}'
        )
        return answer.stdout.strip() if answer.exit == 0 else None

    async def is_ancestor(self, base: str, commit: str) -> bool:
        if (error := revision_error(base, commit)) is not None:
            raise error

        answer = await self.command.answer('merge-base', '--is-ancestor', base, commit)
        if answer.exit not in {0, 1}:
            raise GitUnavailableError(detail=answer.stderr.strip())

        return answer.exit == 0

    async def changed_files(self, base: str, commit: str) -> set[str]:
        if (error := revision_error(base, commit)) is not None:
            raise error

        answer = await self.command.answer('diff', '--name-only', f'{base}..{commit}', '--')
        if answer.exit != 0:
            raise GitUnavailableError(detail=answer.stderr.strip())

        return {line for line in answer.stdout.splitlines() if line}

    async def current_branch(self) -> str | None:
        answer = await self.command.answer('symbolic-ref', '--quiet', '--short', 'HEAD')
        return answer.stdout.strip() if answer.exit == 0 else None

    async def dirty_paths(self, *, untracked: UntrackedFiles) -> list[str] | None:
        answer = await self.command.answer(
            'status', '--porcelain', f'--untracked-files={untracked}'
        )
        if answer.exit != 0:
            return None

        return [line[3:] for line in answer.stdout.splitlines() if line.strip()]

    async def commits_on_no_remote(self, branch: str) -> int | None:
        if (error := revision_error(branch)) is not None:
            raise error

        answer = await self.command.answer(
            'rev-list', '--count', f'refs/heads/{branch}', '--not', '--remotes'
        )
        return int(answer.stdout) if answer.exit == 0 else None


def create_git(root: Path) -> Git:
    command = GitCommand(
        root=root.resolve(),
        executable=shutil.which(GIT_EXECUTABLE),
        processes=get_process_runner(),
    )
    return ProcessGit(command=command)
