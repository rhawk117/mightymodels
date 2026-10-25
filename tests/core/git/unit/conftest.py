"""The git tests over the in-memory backend."""

from typing import TYPE_CHECKING

import pytest

from tests.core.git.git_builders import MEMORY_ROOT, create_memory_harness

if TYPE_CHECKING:
    from tests.core.git.git_builders import RepositoryHarness


@pytest.fixture
def harness() -> RepositoryHarness:
    return create_memory_harness(MEMORY_ROOT)
