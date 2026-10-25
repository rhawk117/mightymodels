"""The fixtures the git tests share; the builders they draw on live in `git_builders`."""

from typing import TYPE_CHECKING

import pytest

from tests.core.git.git_builders import create_scripted_harness

if TYPE_CHECKING:
    from tests.core.git.git_builders import ScriptedHarness


@pytest.fixture
def scripted() -> ScriptedHarness:
    return create_scripted_harness()
