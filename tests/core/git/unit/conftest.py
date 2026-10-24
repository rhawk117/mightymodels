"""The git tests over the in-memory backend."""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.core.git.git_builders import create_memory_harness

if TYPE_CHECKING:
    from tests.core.git.git_builders import RepositoryHarness

MEMORY_ROOT = Path('/repository')


@pytest.fixture
def harness() -> RepositoryHarness:
    return create_memory_harness(MEMORY_ROOT)
