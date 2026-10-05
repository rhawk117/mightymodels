"""The repository the plugin works in: where it is, its paths under `.mightymodels/`, and git.

Each edge builds one workspace, the server in its lifespan and `verify run` for its one command.

Every path under the state directory comes whole from `Workspace.contained`, which resolves it
and refuses one that leaves the resolved state directory, so a symlink planted below it carries no
read and no write outside. The state directory is held privately, so nothing outside this module
joins a part onto it and every path passes through `contained`.

A persona report is the one path a symlink may not stand in for, wherever the symlink points.
Resolving the report would hide that its last part is one, so `Workspace.persona_report` looks at
the name as the reviewer wrote it before resolving it, and hands out a contained file only when
that name is no symlink.

Git runs in `Git._answer` and nowhere else. A missing git binary is an answer without an exit
code, never an exception, so HEAD is absent there as it is outside a repository or before the
first commit. An operation that cannot work without git asks `Git.refusal` first and raises what
it returns.
"""

import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from mightymodels_plugin.errors import StateError
from mightymodels_plugin.run_id import RunId
from mightymodels_plugin.slug import Slug
from mightymodels_plugin.tools.review.schema import Persona

PROJECT_DIR_VARIABLE = 'CLAUDE_PROJECT_DIR'
STATE_DIRECTORY = '.mightymodels'
RUNTIME_DIRECTORY = '.runtime'
DATABASE_NAME = 'mightymodels.db'
TICKET_FILE = 'ticket.yml'
TICKET_DRAFT = f'{TICKET_FILE}.tmp'
EXCLUDE_LINE = f'{STATE_DIRECTORY}/'
SAFE_REVISION = re.compile(r'[0-9A-Za-z][0-9A-Za-z._/-]*')
REPORT_FILES: Mapping[Persona, str] = MappingProxyType(
    {
        Persona.MERGE_VADER: 'MERGE-VADER-REPORT.md',
        Persona.UNCLE_BOB: 'UNCLE-BOB-REPORT.md',
    }
)


class OutsideStateDirectoryError(StateError):
    def __init__(self, shown: str) -> None:
        super().__init__(
            f'{shown} resolves outside {STATE_DIRECTORY}/ and is not read or written; '
            'remove the symlink that leads there'
        )
        self.shown = shown


class GitMissingError(StateError):
    def __init__(self) -> None:
        super().__init__('this needs git and no git executable is on PATH')


class NotARepositoryError(StateError):
    def __init__(self, root: Path, detail: str) -> None:
        super().__init__(f'{root} is not inside a git repository: {detail}')
        self.root = root
        self.detail = detail


class UnsafeRevisionError(StateError):
    def __init__(self, revision: str) -> None:
        super().__init__(f'{revision!r} is not a plain revision name')
        self.revision = revision


class GitUnavailableError(StateError):
    def __init__(self, detail: str) -> None:
        super().__init__(f'git could not list the commit changes: {detail}')
        self.detail = detail


type GitRefusal = GitMissingError | NotARepositoryError


@dataclass(slots=True, kw_only=True, frozen=True)
class GitAnswer:
    exit: int | None
    stdout: str
    stderr: str


@dataclass(slots=True, kw_only=True, frozen=True)
class PersonaReport:
    relative: str
    file: Path | None


def find_root(environ: Mapping[str, str], cwd: Path) -> Path:
    project_dir = environ.get(PROJECT_DIR_VARIABLE, '')
    return Path(project_dir) if project_dir else cwd


def revision_error(*revisions: str) -> UnsafeRevisionError | None:
    unsafe = next(
        (revision for revision in revisions if not SAFE_REVISION.fullmatch(revision)), None
    )
    return None if unsafe is None else UnsafeRevisionError(unsafe)


def review_parts(slug: Slug | None, run: RunId) -> tuple[str, ...]:
    if slug is None:
        return RUNTIME_DIRECTORY, 'reviews', run.root
    return slug.root, 'review', run.root


def exclude_state(common_directory: Path) -> None:
    exclude = common_directory.joinpath('info', 'exclude')
    current = exclude.read_text(encoding='utf-8') if exclude.is_file() else ''
    if EXCLUDE_LINE in current.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    separator = '' if not current or current.endswith('\n') else '\n'
    exclude.write_text(f'{current}{separator}{EXCLUDE_LINE}\n', encoding='utf-8')


@dataclass(slots=True, kw_only=True, frozen=True)
class Git:
    root: Path

    def _answer(self, *arguments: str) -> GitAnswer:
        try:
            completed = subprocess.run(  # noqa: S603 - fixed git argv, every argument is a separate word and revisions are checked plain names
                ['git', '-C', str(self.root), *arguments],  # noqa: S607 - git is resolved from PATH like every other tool the plugin runs
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as error:
            return GitAnswer(exit=None, stdout='', stderr=str(error))
        return GitAnswer(
            exit=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
        )

    def refusal(self) -> GitRefusal | None:
        answer = self._answer('rev-parse', '--git-dir')
        if answer.exit is None:
            return GitMissingError()
        if answer.exit != 0:
            return NotARepositoryError(self.root, answer.stderr.strip())
        return None

    def common_directory(self) -> Path | None:
        answer = self._answer('rev-parse', '--path-format=absolute', '--git-common-dir')
        return Path(answer.stdout.strip()) if answer.exit == 0 else None

    def resolve_head(self) -> str | None:
        answer = self._answer('rev-parse', '--verify', '--quiet', 'HEAD')
        return answer.stdout.strip() if answer.exit == 0 else None

    def resolve_commit(self, revision: str) -> str | None:
        error = revision_error(revision)
        if error is not None:
            raise error
        answer = self._answer('rev-parse', '--verify', '--quiet', f'{revision}^{{commit}}')
        return answer.stdout.strip() if answer.exit == 0 else None

    def is_ancestor(self, base: str, commit: str) -> bool:
        error = revision_error(base, commit)
        if error is not None:
            raise error
        answer = self._answer('merge-base', '--is-ancestor', base, commit)
        if answer.exit not in {0, 1}:
            raise GitUnavailableError(answer.stderr.strip())
        return answer.exit == 0

    def changed_files(self, base: str, commit: str) -> set[str]:
        error = revision_error(base, commit)
        if error is not None:
            raise error
        answer = self._answer('diff', '--name-only', f'{base}..{commit}', '--')
        if answer.exit != 0:
            raise GitUnavailableError(answer.stderr.strip())
        return {line for line in answer.stdout.splitlines() if line}


@dataclass(slots=True, kw_only=True, frozen=True)
class Workspace:
    root: Path
    _state_directory: Path
    git: Git

    def contained(self, *parts: str) -> Path:
        resolved = self._state_directory.joinpath(*parts).resolve()
        if not resolved.is_relative_to(self._state_directory):
            raise OutsideStateDirectoryError(str(Path(STATE_DIRECTORY, *parts)))
        return resolved

    def relative_to_root(self, contained: Path) -> str:
        return str(Path(STATE_DIRECTORY).joinpath(contained.relative_to(self._state_directory)))

    def database_file(self) -> Path:
        return self.contained(DATABASE_NAME)

    def ticket_file(self, slug: Slug) -> Path:
        return self.contained(slug.root, TICKET_FILE)

    def ticket_draft(self, slug: Slug) -> Path:
        return self.contained(slug.root, TICKET_DRAFT)

    def task_brief(self, slug: Slug, number: int) -> Path:
        return self.contained(slug.root, 'briefs', f'task-{number:02d}.md')

    def investigation_ledger(self, investigation: Slug) -> Path:
        return self.contained(RUNTIME_DIRECTORY, 'investigations', f'{investigation.root}.jsonl')

    def review_directory(self, slug: Slug | None, run: RunId) -> Path:
        return self.contained(*review_parts(slug, run))

    def persona_report(self, slug: Slug | None, run: RunId, *, persona: Persona) -> PersonaReport:
        name = REPORT_FILES[persona]
        parts = (*review_parts(slug, run), name)
        directory = self.review_directory(slug, run)
        is_symlink = self._state_directory.joinpath(*parts).is_symlink()
        return PersonaReport(
            relative=str(Path(self.relative_to_root(directory), name)),
            file=None if is_symlink else self.contained(*parts),
        )

    def exclude_state_from_git(self) -> None:
        common_directory = self.git.common_directory()
        if common_directory is None:
            return
        exclude_state(common_directory)


def workspace_at(root: Path) -> Workspace:
    resolved = root.resolve()
    return Workspace(
        root=resolved,
        _state_directory=resolved.joinpath(STATE_DIRECTORY).resolve(),
        git=Git(root=resolved),
    )
