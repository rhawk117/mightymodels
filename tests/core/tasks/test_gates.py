"""The task gates: what keeps a task from verified and a ticket from ready."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract.records import Receipt, RecordedCommand
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
from mightymodels_core.tasks.gates import criterion_of_command

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.schemas.contract import Outcome
    from mightymodels_core.schemas.tasks import TaskStatus

HEAD = 'abc1234'
BRIEF = '## ASKED\n  - AC-1: first\n  - AC-2: second\n## DONE\ncommit: abc1234\n'
TASK = TaskId('T7')


def create_command(key: str) -> RecordedCommand:
    return RecordedCommand(key=key, task_key=TASK, argv=('true',), expect_exit=0, timeout=30)


def create_receipt(key: str, *, outcome: Outcome = 'pass', head: str | None = HEAD) -> Receipt:
    return Receipt(
        key=key,
        argv=('true',),
        outcome=outcome,
        exit=0,
        duration_ms=1,
        stdout_tail=redact(''),
        stderr_tail=redact(''),
        digest='d',
        head=head,
        phase='task',
        at=datetime(2026, 1, 2, tzinfo=UTC),
    )


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
            assertions={'AC-2': 'src/a.py:1'},
            commands=[create_command('T7.AC-1')],
            receipts={'T7.AC-1': create_receipt('T7.AC-1')},
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
    key = 'T7.AC-1'
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
        with_evidence(
            'receipt-missing',
            (f'{key} has no receipt at the current HEAD',),
            receipts={},
        ),
        with_evidence(
            'receipt-from-another-head',
            (f'{key} has no receipt at the current HEAD',),
            receipts={key: create_receipt(key, head='old0000')},
        ),
        with_evidence(
            'receipt-failed',
            (f'{key} fail at HEAD',),
            receipts={key: create_receipt(key, outcome='fail')},
        ),
        with_evidence('brief-missing', ('the task brief is missing',), brief=Brief(text=None)),
        with_git(
            'done-names-another-commit',
            ('the DONE brief must name the reported HEAD commit',),
            named_commit='old0000',
        ),
        with_evidence(
            'criterion-unproven',
            ('AC-2 has neither a contract command nor a citation',),
            assertions={},
        ),
        with_evidence(
            'nothing-proves-the-task',
            ('no contract command and no cited assertion proves this task',),
            brief=None,
            commands=[],
            receipts={},
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
            ['T1 has contract commands but was never started'],
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


def proven_criteria_cases() -> pytest.MarkDecorator:
    dotless = replace(
        proven().evidence, commands=[create_command('T7.AC-1'), create_command('nodot')]
    )
    cases = [
        pytest.param(
            GateScenario(name='dotless-command-key', evidence=dotless),
            {'AC-1', 'AC-2'},
            id='dotless-command-key',
        )
    ]
    return pytest.mark.parametrize(('scenario', 'criteria'), cases)


class TestVerificationGate:
    @verification_cases()
    def test_verification_problems(self, scenario: GateScenario) -> None:
        assert scenario.gate.get_verification_problems() == list(scenario.problems)

    @proven_criteria_cases()
    def test_proven_criteria(self, scenario: GateScenario, criteria: set[str]) -> None:
        assert scenario.gate.proven_criteria == criteria


class TestDoneCommit:
    @pytest.mark.parametrize(
        ('brief_text', 'named'),
        [
            pytest.param(BRIEF, 'abc1234', id='named'),
            pytest.param('## ASKED\ncommit: abc1234\n', None, id='before-the-done-heading'),
            pytest.param('## DONE\nno hash\n', None, id='done-without-a-commit'),
            pytest.param('## DONE\ncommit: xyz\n', None, id='not-a-hash'),
        ],
    )
    def test_done_commit(self, brief_text: str, named: str | None) -> None:
        assert done_commit(brief_text) == named


class TestCriterionOfCommand:
    @pytest.mark.parametrize(
        ('key', 'criterion'), [('T7.AC-1', 'AC-1'), ('R17.AC-2', 'AC-2'), ('nodot', None)]
    )
    def test_criterion_of_command(self, key: str, criterion: str | None) -> None:
        assert criterion_of_command(key) == criterion


class TestPlanTask:
    @pytest.mark.parametrize(('key', 'expected'), [('T1', True), ('R1', False), ('C1', False)])
    def test_only_the_t_prefix_is_a_plan_task(self, key: str, expected: bool) -> None:
        assert is_plan_task(TaskId(key)) is expected

    def test_closed_plan_task_has_no_problem(self) -> None:
        assert get_plan_task_problem(create_record('T1', 'verified')) is None


class TestReadiness:
    @readiness_cases()
    def test_readiness_problems(self, records: list[TaskRecord], problems: list[str]) -> None:
        assert get_readiness_problems(records) == problems
