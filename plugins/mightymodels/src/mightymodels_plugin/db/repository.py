"""Find the repository the plugin works in and keep its `.mightymodels/` state out of git."""

import subprocess
from collections.abc import Mapping
from pathlib import Path

from mightymodels_plugin.errors import StateError

PROJECT_DIR_VARIABLE = 'CLAUDE_PROJECT_DIR'
STATE_DIRECTORY = '.mightymodels'
EXCLUDE_LINE = f'{STATE_DIRECTORY}/'


class NotARepositoryError(StateError):
    def __init__(self, root: Path, detail: str) -> None:
        super().__init__(f'{root} is not inside a git repository: {detail}')
        self.root = root
        self.detail = detail


def find_root(environ: Mapping[str, str], cwd: Path) -> Path:
    project_dir = environ.get(PROJECT_DIR_VARIABLE)
    return Path(project_dir) if project_dir else cwd


def common_git_dir(root: Path) -> Path | NotARepositoryError:
    completed = subprocess.run(  # noqa: S603 - fixed git argv, the root is a separate word
        ['git', '-C', str(root), 'rev-parse', '--path-format=absolute', '--git-common-dir'],  # noqa: S607 - git is resolved from PATH like every other tool the plugin runs
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return NotARepositoryError(root, completed.stderr.strip())
    return Path(completed.stdout.strip())


def exclude_state(common_dir: Path) -> None:
    exclude = common_dir.joinpath('info', 'exclude')
    current = exclude.read_text(encoding='utf-8') if exclude.is_file() else ''
    if EXCLUDE_LINE in current.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    separator = '' if not current or current.endswith('\n') else '\n'
    exclude.write_text(f'{current}{separator}{EXCLUDE_LINE}\n', encoding='utf-8')


def exclude_state_in_repository(root: Path) -> NotARepositoryError | None:
    common_dir = common_git_dir(root)
    if isinstance(common_dir, NotARepositoryError):
        return common_dir
    exclude_state(common_dir)
    return None
