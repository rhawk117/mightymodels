"""The crashout repository over the fake."""

import pytest

from tests.core.crashouts.crashout_builders import CrashoutHarness
from tests.core.crashouts.fakes import FakeCrashoutRepository


@pytest.fixture
def harness() -> CrashoutHarness:
    return CrashoutHarness(crashouts=FakeCrashoutRepository())
