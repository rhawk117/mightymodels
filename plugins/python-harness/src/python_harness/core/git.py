"""Read-only git queries the inspect commands need."""

import shutil
import subprocess

from python_harness.core.errors import GitCommandError, GitUnavailableError
from python_harness.core.workspace import Workspace


def find_git_executable() -> str:
    executable = shutil.which('git')
    if executable is None:
        raise GitUnavailableError
    return executable


def run_git(workspace: Workspace, *arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603  fixed git verbs from this CLI, no shell.
        (find_git_executable(), *arguments),
        cwd=workspace.root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise GitCommandError(arguments, completed.returncode, completed.stderr)
    return completed.stdout


def list_changed_python_files(workspace: Workspace, base: str, head: str) -> tuple[str, ...]:
    output = run_git(
        workspace,
        'diff',
        '--name-only',
        '--relative',
        '--diff-filter=d',
        f'{base}...{head}',
        '--',
        '*.py',
    )
    return tuple(line for line in output.splitlines() if line)
