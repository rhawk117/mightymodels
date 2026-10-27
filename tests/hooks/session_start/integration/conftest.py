"""A real git checkout, a data directory and the handler over them, with a clock the test sets."""

import io
from typing import TYPE_CHECKING

import pytest

from tests.core.git.git_builders import run_git
from tests.core.primitives.clock import create_fake_clock
from tests.hooks.session_start.session_start_builders import NOW, SessionStartHarness

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
async def checkout(tmp_path: Path) -> Path:
    root = tmp_path.joinpath('checkout')
    root.mkdir()
    await run_git(root, 'init')
    return root


@pytest.fixture
def harness(checkout: Path, data_directory: Path, env_file: Path) -> SessionStartHarness:
    return SessionStartHarness(
        checkout=checkout,
        data_directory=data_directory,
        env_file=env_file,
        clock=create_fake_clock(NOW),
        stderr=io.StringIO(),
    )
