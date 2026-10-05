import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest


def run_git(directory: Path, *arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed git argv, every argument is a separate word
        ['git', '-C', str(directory), *arguments],  # noqa: S607 - git is resolved from PATH like in the package
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


type GitRunner = Callable[..., str]


@pytest.fixture
def git() -> GitRunner:
    return run_git


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path.joinpath('repository')
    root.mkdir()
    run_git(root, 'init', '--quiet')
    return root
