"""The crashout repository contract against the fake."""

from mightymodels_core.crashouts import CrashoutRepository

from tests.core.crashouts.crashout_repository_suite import CrashoutRepositoryContract
from tests.core.crashouts.fakes import FakeCrashoutRepository


class TestFakeCrashoutRepository(CrashoutRepositoryContract):
    pass


class TestFakeImplementation:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeCrashoutRepository(), CrashoutRepository)
