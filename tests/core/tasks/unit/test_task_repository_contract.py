"""The task repository contract against the fake."""

from mightymodels_core.tasks import TaskRepository

from tests.core.tasks.fakes import FakeTaskRepository, TaskLedger
from tests.core.tasks.task_repository_suite import TaskRepositoryContract


class TestFakeTaskRepository(TaskRepositoryContract):
    pass


class TestFakeImplementation:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeTaskRepository(ledger=TaskLedger()), TaskRepository)
