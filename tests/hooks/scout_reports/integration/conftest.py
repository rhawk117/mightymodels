"""A real git checkout, a data directory and the keeper over them."""

import io
from typing import TYPE_CHECKING

import pytest

from tests.core.git.git_builders import run_git
from tests.hooks.scout_reports.scout_reports_builders import ScoutHarness

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
async def checkout(tmp_path: Path) -> Path:
    root = tmp_path.joinpath('checkout')
    root.mkdir()
    await run_git(root, 'init', '--initial-branch', 'main')
    return root


@pytest.fixture
def harness(checkout: Path, tmp_path: Path) -> ScoutHarness:
    return ScoutHarness(
        checkout=checkout, data_directory=tmp_path.joinpath('plugin data'), stderr=io.StringIO()
    )


@pytest.fixture
def bare_directory(tmp_path: Path) -> Path:
    directory = tmp_path.joinpath('not a work tree')
    directory.mkdir()
    return directory
