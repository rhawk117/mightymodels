"""A real git checkout and a data directory the recorder runs over."""

import io
from typing import TYPE_CHECKING

import pytest

from tests.core.git.git_builders import run_git
from tests.hooks.recorder.recorder_builders import RecorderHarness

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
async def checkout(tmp_path: Path) -> Path:
    root = tmp_path.joinpath('checkout')
    root.mkdir()
    await run_git(root, 'init', '--initial-branch', 'main')
    return root


@pytest.fixture
def harness(checkout: Path, tmp_path: Path) -> RecorderHarness:
    return RecorderHarness(
        checkout=checkout, data_directory=tmp_path.joinpath('plugin data'), stderr=io.StringIO()
    )
