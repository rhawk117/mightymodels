"""Starting a plan task that was never declared is refused; residual and CI tasks need no row."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import TaskId
from mightymodels_core.tasks.errors import UndeclaredPlanTaskError

from tests.core.tasks.service_builders import FIRST_TASK, SERVICE_SLUG, create_start_request

if TYPE_CHECKING:
    from tests.core.tasks.service_builders import ServiceHarness


class TestStartRefusal:
    def test_an_undeclared_plan_task_is_refused_naming_task_declare(
        self, service_harness: ServiceHarness
    ) -> None:
        with pytest.raises(UndeclaredPlanTaskError, match='task_declare'):
            service_harness.service.start(SERVICE_SLUG, create_start_request())

        assert service_harness.tasks.tasks(service_harness.ticket_id) == []

    def test_a_declared_plan_task_starts(self, declared_harness: ServiceHarness) -> None:
        record = declared_harness.service.start(SERVICE_SLUG, create_start_request())

        assert (record.key, record.status) == (FIRST_TASK, 'in-progress')

    @pytest.mark.parametrize('task_key', ['R1', 'C1'])
    def test_a_residual_or_ci_task_starts_without_a_declared_row(
        self, service_harness: ServiceHarness, task_key: str
    ) -> None:
        request = create_start_request(task_key=TaskId(task_key))

        record = service_harness.service.start(SERVICE_SLUG, request)

        assert (record.key, record.status) == (task_key, 'in-progress')
