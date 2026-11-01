"""The task gates: what keeps a task from verified and a ticket from ready."""

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.primitives import TaskId, redact
from mightymodels_core.tasks import (
    Brief,
    Evidence,
    GitFacts,
    TaskRecord,
    VerificationGate,
    done_commit,
    get_plan_task_problem,
    get_readiness_problems,
    is_plan_task,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.schemas.tasks import TaskStatus

HEAD = 'abc1234'
BRIEF = '## ASKED\n  - AC-1: first\n  - AC-2: second\n## DONE\ncommit: abc1234\n'
TASK = TaskId('T7')


def create_record(key: str, status: TaskStatus, reasons: tuple[str, ...] = ()) -> TaskRecord:
    return TaskRecord(key=TaskId(key), status=status, reasons=tuple(map(redact, reasons)))


@dataclass(slots=True, kw_only=True, frozen=True)
class GateScenario:
    name: str
    git: GitFacts = field(
        default_factory=lambda: GitFacts(
            head=HEAD,
            base_resolves=True,
            base_is_ancestor=True,
            changed_files=frozenset({'src/a.py'}),
            named_commit=HEAD,
        )
    )
    evidence: Evidence = field(
        default_factory=lambda: Evidence(
            commit=HEAD,
            brief=Brief(text=BRIEF),
            assertions={'AC-1': 'src/a.py:1', 'AC-2': 'src/a.py:2'},
        )
    )
    base: str | None = 'base123'
    problems: tuple[str, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)

    @property
    def gate(self) -> VerificationGate:
        task = TaskRecord(key=TASK, status='in-progress', owned=('src/a.py',), base=self.base)
        return VerificationGate(task=task, evidence=self.evidence, git=self.git)


def proven() -> GateScenario:
    return GateScenario(name='proven')


def with_git(name: str, problems: tuple[str, ...], **changes: object) -> GateScenario:
    return GateScenario(name=name, git=replace(proven().git, **changes), problems=problems)


def with_evidence(name: str, problems: tuple[str, ...], **changes: object) -> GateScenario:
    return GateScenario(
        name=name, evidence=replace(proven().evidence, **changes), problems=problems
    )


def verification_cases() -> pytest.MarkDecorator:
    scenarios = [
        proven(),
        with_git(
            'head-moved-past-the-commit',
            ('the reported commit must resolve to the current HEAD',),
            head='fff9999',
        ),
        with_git('no-head', ('the reported commit must resolve to the current HEAD',), head=None),
        with_git('base-unresolved', ('the task has no valid base commit',), base_resolves=False),
        GateScenario(name='base-unset', base=None, problems=('the task has no valid base commit',)),
        with_git(
            'base-not-an-ancestor',
            ('the task base is not an ancestor of the reported commit',),
            base_is_ancestor=False,
        ),
        with_git(
            'changed-outside-the-owned-set',
            ('changed outside the owned set: src/b.py',),
            changed_files=frozenset({'src/a.py', 'src/b.py'}),
        ),
        with_evidence('brief-missing', ('the task brief is missing',), brief=Brief(text=None)),
        with_git(
            'done-names-another-commit',
            ('the DONE brief must name the reported HEAD commit',),
            named_commit='old0000',
        ),
        with_evidence(
            'criterion-unproven',
            ('AC-2 has no citation',),
            assertions={'AC-1': 'src/a.py:1'},
        ),
        with_evidence(
            'nothing-proves-the-task',
            ('no cited assertion proves this task',),
            brief=None,
            assertions={},
        ),
        with_evidence('residual-has-no-brief', (), brief=None),
    ]
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


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


class TestVerificationGate:
    @verification_cases()
    def test_verification_problems(self, scenario: GateScenario) -> None:
        assert scenario.gate.get_verification_problems() == list(scenario.problems)


def done_commit_cases() -> pytest.MarkDecorator:
    cases = [
        pytest.param(BRIEF, 'abc1234', id='named'),
        pytest.param('## ASKED\ncommit: abc1234\n', None, id='before-the-done-heading'),
        pytest.param('## DONE\nno hash\n', None, id='done-without-a-commit'),
        pytest.param('## DONE\ncommit: xyz\n', None, id='not-a-hash'),
    ]
    return pytest.mark.parametrize(('brief_text', 'named'), cases)


class TestDoneCommit:
    @done_commit_cases()
    def test_done_commit(self, brief_text: str, named: str | None) -> None:
        assert done_commit(brief_text) == named


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
