"""A real git checkout, a data directory and the hook over them."""

import io
from typing import TYPE_CHECKING

import pytest

from tests.core.git.git_builders import run_git
from tests.hooks.dispatch.dispatch_builders import BRANCH, DispatchHarness
from tests.hooks.pre_compact.pre_compact_builders import PreCompactHarness

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
async def checkout(tmp_path: Path) -> Path:
    root = tmp_path.joinpath('checkout')
    root.mkdir()
    await run_git(root, 'init', '--initial-branch', BRANCH)
    return root


@pytest.fixture
def harness(checkout: Path, tmp_path: Path) -> PreCompactHarness:
    dispatch = DispatchHarness(checkout=checkout, data_directory=tmp_path.joinpath('plugin data'))
    dispatch.make_ticket_directory()
    return PreCompactHarness(dispatch=dispatch, stderr=io.StringIO())


@pytest.fixture
async def ticketed(harness: PreCompactHarness) -> PreCompactHarness:
    await harness.dispatch.seed(())
    return harness


@pytest.fixture
async def ticketed_elsewhere(ticketed: PreCompactHarness) -> PreCompactHarness:
    await run_git(ticketed.dispatch.checkout, 'checkout', '-b', 'feat/other')
    return ticketed
