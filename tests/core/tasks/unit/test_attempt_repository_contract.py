"""The attempt repository contract against the fake."""

from mightymodels_core.tasks import AttemptRepository

from tests.core.tasks.attempt_repository_suite import AttemptRepositoryContract
from tests.core.tasks.fakes import FakeAttemptRepository, TaskLedger


class TestFakeAttemptRepository(AttemptRepositoryContract):
    pass


class TestFakeImplementation:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeAttemptRepository(ledger=TaskLedger()), AttemptRepository)
