"""A real git checkout, the environment `verify run` reads and the contract approved in it."""

import asyncio
import os
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.workspace import PROJECT_DIR_VARIABLE

from tests.cli.integration.verify_builders import ApprovedContract
from tests.core.git.git_builders import run_git

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def clean_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [name for name in os.environ if name.startswith('GIT_')]:
        monkeypatch.delenv(name)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path.joinpath('repository')
    root.mkdir()
    asyncio.run(run_git(root, 'init', '--quiet', '--initial-branch', 'main'))
    asyncio.run(run_git(root, 'commit', '--quiet', '--allow-empty', '-m', 'first commit'))
    return root


@pytest.fixture
def subdirectory(repository: Path) -> Path:
    below = repository.joinpath('src', 'queue')
    below.mkdir(parents=True)
    return below


@pytest.fixture
def session_in_the_repository(repository: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(repository))
    return repository


@pytest.fixture
def session_in_the_subdirectory(subdirectory: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(subdirectory))


@pytest.fixture
def contract(repository: Path, session_data_directory: Path) -> ApprovedContract:
    return ApprovedContract(repository=repository, data_directory=session_data_directory)
