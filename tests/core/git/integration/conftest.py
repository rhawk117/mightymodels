"""The git tests over real git."""

from typing import TYPE_CHECKING

import pytest

from tests.core.git.git_builders import GIT_ROOT_NAME, create_process_harness

if TYPE_CHECKING:
    from pathlib import Path

    from tests.core.git.git_builders import RepositoryHarness


@pytest.fixture
async def harness(tmp_path: Path) -> RepositoryHarness:
    return await create_process_harness(tmp_path.joinpath(GIT_ROOT_NAME).resolve())
