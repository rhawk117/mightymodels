"""The task gates: what keeps a ticket from ready."""

from typing import TYPE_CHECKING

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.primitives import TaskId, redact
from mightymodels_core.tasks import (
    TaskRecord,
    get_plan_task_problem,
    get_readiness_problems,
    is_plan_task,
)

if TYPE_CHECKING:
    from mightymodels_core.schemas.tasks import TaskStatus


def create_record(key: str, status: TaskStatus, reasons: tuple[str, ...] = ()) -> TaskRecord:
    return TaskRecord(key=TaskId(key), status=status, reasons=tuple(map(redact, reasons)))


def readiness_cases() -> pytest.MarkDecorator:
    cases = [
        pytest.param([create_record('T1', 'verified')], [], id='plan-task-verified'),
        pytest.param(
            [create_record('T1', 'verified'), create_record('T2', 'superseded')],
            [],
            id='plan-task-superseded',
        ),
        pytest.param([], ['no plan task has been started'], id='no-plan-task'),
        pytest.param(
            [create_record('R1', 'verified')],
            ['no plan task has been started'],
            id='only-a-residual',
        ),
        pytest.param(
            [create_record('T1', 'pending')],
            ['T1 was never started'],
            id='plan-task-pending',
        ),
        pytest.param(
            [create_record('T1', 'in-progress')],
            ['T1 is in-progress, not verified'],
            id='plan-task-in-progress',
        ),
        pytest.param(
            [create_record('T1', 'verified'), create_record('R1', 'blocked', ('a', 'b'))],
            ['R1 is blocked: a; b'],
            id='residual-blocked',
        ),
        pytest.param(
            [create_record('T1', 'verified'), create_record('C1', 'failed', ('red',))],
            ['C1 is failed: red'],
            id='ci-check-failed',
        ),
        pytest.param(
            [create_record('T1', 'verified'), create_record('R1', 'in-progress')],
            [],
            id='residual-in-progress-is-not-stuck',
        ),
    ]
    return pytest.mark.parametrize(('records', 'problems'), cases)


class TestPlanTask:
    keys = st.text()

    @given(key=keys)
    @example(key='T1')
    @example(key='R1')
    @example(key='C1')
    def test_only_the_t_prefix_is_a_plan_task(self, key: str) -> None:
        assert is_plan_task(TaskId(key)) is key.startswith('T')

    def test_closed_plan_task_has_no_problem(self) -> None:
        assert get_plan_task_problem(create_record('T1', 'verified')) is None


class TestReadiness:
    @readiness_cases()
    def test_readiness_problems(self, records: list[TaskRecord], problems: list[str]) -> None:
        assert get_readiness_problems(records) == problems
