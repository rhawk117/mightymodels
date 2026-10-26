"""A real git checkout with a ticket directory, a data directory and the handler over them."""

import io
from typing import TYPE_CHECKING

import pytest

from tests.core.git.git_builders import run_git
from tests.hooks.pointer.pointer_builders import PointerHarness

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
async def checkout(tmp_path: Path) -> Path:
    root = tmp_path.joinpath('checkout')
    root.mkdir()
    await run_git(root, 'init', '--initial-branch', 'main')
    return root


@pytest.fixture
def harness(checkout: Path, tmp_path: Path) -> PointerHarness:
    harness = PointerHarness(
        checkout=checkout, data_directory=tmp_path.joinpath('plugin data'), stderr=io.StringIO()
    )
    harness.make_ticket_directory()
    return harness
