"""A real git checkout on the ticket's branch, a data directory and the handler over them."""

from typing import TYPE_CHECKING

import pytest

from tests.core.git.git_builders import run_git
from tests.hooks.dispatch.dispatch_builders import BRANCH, DispatchHarness

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
async def checkout(tmp_path: Path) -> Path:
    root = tmp_path.joinpath('checkout')
    root.mkdir()
    await run_git(root, 'init', '--initial-branch', BRANCH)
    return root


@pytest.fixture
def harness(checkout: Path, tmp_path: Path) -> DispatchHarness:
    return DispatchHarness(checkout=checkout, data_directory=tmp_path.joinpath('plugin data'))
