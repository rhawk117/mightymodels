"""A real git checkout, with or without a ticket directory, and a data directory."""

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
def bare_harness(checkout: Path, tmp_path: Path) -> PointerHarness:
    return PointerHarness(
        checkout=checkout, data_directory=tmp_path.joinpath('plugin data'), stderr=io.StringIO()
    )


@pytest.fixture
def harness(bare_harness: PointerHarness) -> PointerHarness:
    bare_harness.make_ticket_directory()
    return bare_harness
