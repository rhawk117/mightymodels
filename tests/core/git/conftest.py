"""The fixtures the git tests share; the builders they draw on live in `git_builders`."""

from typing import TYPE_CHECKING

import pytest

from tests.core.git.git_builders import (
    GIT_ROOT_NAME,
    create_memory_harness,
    create_process_harness,
    create_scripted_harness,
)

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.fixtures import SubRequest

    from tests.core.git.git_builders import RepositoryHarness, ScriptedHarness


@pytest.fixture
async def harness(request: SubRequest, tmp_path: Path) -> RepositoryHarness:
    root = tmp_path.joinpath(GIT_ROOT_NAME).resolve()
    if request.param == 'process':
        return await create_process_harness(root)

    return create_memory_harness(root)


@pytest.fixture
def scripted() -> ScriptedHarness:
    return create_scripted_harness()
