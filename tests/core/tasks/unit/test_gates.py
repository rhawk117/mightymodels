"""The task gates: what keeps a ticket from ready."""

from typing import TYPE_CHECKING

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.primitives import TaskId, redact
from mightymodels_core.tasks import (
    GitFacts,
    TaskRecord,
    VerifyRequest,
    get_plan_task_problem,
    get_readiness_problems,
    get_verify_facts,
    is_plan_task,
)

if TYPE_CHECKING:
    from mightymodels_core.schemas.tasks import TaskStatus
    from mightymodels_core.tasks import VerifyFacts


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


def create_verify_facts(
    *,
    commit: str = 'abc',
    head: str | None = 'abc',
    base_resolves: bool = True,
    base_is_ancestor: bool = True,
    changed_files: frozenset[str] = frozenset(),
) -> VerifyFacts:
    record = TaskRecord(key=TaskId('T1'), status='in-progress', owned=('src/a.py',))
    git = GitFacts(
        head=head,
        base_resolves=base_resolves,
        base_is_ancestor=base_is_ancestor,
        changed_files=changed_files,
    )
    request = VerifyRequest(seen=record, commit=commit, verdict='verified', reason=None, git=git)
    return get_verify_facts(request, record)


class TestVerifyFacts:
    def test_a_resolved_ancestor_base_reads_ancestor(self) -> None:
        assert create_verify_facts().base_status == 'ancestor'

    def test_a_resolved_base_that_is_not_an_ancestor_reads_not_ancestor(self) -> None:
        facts = create_verify_facts(base_is_ancestor=False)

        assert facts.base_status == 'not-ancestor'

    @pytest.mark.parametrize('base_is_ancestor', [True, False])
    def test_an_unresolved_base_reads_unresolved_whatever_the_raw_ancestor_flag(
        self, *, base_is_ancestor: bool
    ) -> None:
        facts = create_verify_facts(base_resolves=False, base_is_ancestor=base_is_ancestor)

        assert facts.base_status == 'unresolved'

    def test_the_commit_is_head_only_when_it_equals_head(self) -> None:
        assert create_verify_facts().commit_is_head
        assert not create_verify_facts(commit='old').commit_is_head
        assert not create_verify_facts(head=None).commit_is_head

    def test_outside_owned_lists_the_changed_files_not_owned_sorted(self) -> None:
        facts = create_verify_facts(changed_files=frozenset({'z.py', 'src/a.py', 'b.py'}))

        assert facts.outside_owned == ('b.py', 'z.py')
