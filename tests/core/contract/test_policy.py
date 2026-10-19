"""The contract policy: command shape, approval, run pick and the receipt assessment."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract import (
    ApprovalPolicy,
    ChangedCommandError,
    CommandPolicy,
    ContractOptions,
    InvalidArgvError,
    InvalidCommandKeyError,
    InvalidTimeoutError,
    MissingApprovalError,
    NoContractError,
    PickPolicy,
    ReceiptAssessment,
    RecordedCommand,
    UnknownCommandError,
    is_argv,
)
from mightymodels_core.primitives import Slug, TaskId

from .conftest import FIRST_KEY, HEAD, SECOND_KEY, create_command, create_receipt

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.contract import ReceiptState
    from mightymodels_core.schemas.contract import Outcome

SLUG = Slug('policy-subject')
OPTIONS = ContractOptions()


@dataclass(slots=True, kw_only=True, frozen=True)
class ShapeScenario:
    name: str
    key: str = FIRST_KEY
    argv: tuple[str, ...] = ('make', 'test')
    timeout: int = 300
    approved_by: str = 'planner'
    error_type: type[Exception] | None = None

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


@dataclass(slots=True, kw_only=True, frozen=True)
class AssessmentScenario:
    name: str
    taken_at: str | None
    head: str | None
    outcome: Outcome
    state: ReceiptState
    outcome_at_head: Outcome | None

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def recorded(key: str, argv: tuple[str, ...] = ('make', 'test')) -> RecordedCommand:
    return RecordedCommand(key=key, task_key=TaskId('T1'), argv=argv, expect_exit=0, timeout=300)


def command_shape_cases() -> pytest.MarkDecorator:
    scenarios = [
        ShapeScenario(name='valid'),
        ShapeScenario(name='key-at-limit', key='a' * OPTIONS.key_limit),
        ShapeScenario(
            name='key-over-limit',
            key='a' * (OPTIONS.key_limit + 1),
            error_type=InvalidCommandKeyError,
        ),
        ShapeScenario(name='key-empty', key='', error_type=InvalidCommandKeyError),
        ShapeScenario(name='key-with-space', key='T1 AC-1', error_type=InvalidCommandKeyError),
        ShapeScenario(name='key-with-slash', key='T1/AC-1', error_type=InvalidCommandKeyError),
        ShapeScenario(name='key-with-newline', key='T1.AC-1\n', error_type=InvalidCommandKeyError),
        ShapeScenario(name='argv-empty', argv=(), error_type=InvalidArgvError),
        ShapeScenario(name='timeout-at-floor', timeout=OPTIONS.timeout_floor),
        ShapeScenario(
            name='timeout-below-floor',
            timeout=OPTIONS.timeout_floor - 1,
            error_type=InvalidTimeoutError,
        ),
        ShapeScenario(name='timeout-at-limit', timeout=OPTIONS.timeout_limit),
        ShapeScenario(
            name='timeout-over-limit',
            timeout=OPTIONS.timeout_limit + 1,
            error_type=InvalidTimeoutError,
        ),
        ShapeScenario(name='approver-blank', approved_by='  ', error_type=MissingApprovalError),
    ]
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


def argv_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('value', 'expected'),
        [
            pytest.param(('make', 'test'), True, id='tuple'),
            pytest.param(['make', 'test'], True, id='list'),
            pytest.param('make test', False, id='shell-string'),
            pytest.param((), False, id='empty'),
            pytest.param(['make', 1], False, id='non-string-argument'),
            pytest.param(None, False, id='none'),
        ],
    )


def assessment_cases() -> pytest.MarkDecorator:
    scenarios = [
        AssessmentScenario(
            name='never-run',
            taken_at=None,
            head=HEAD,
            outcome='pass',
            state='never-run',
            outcome_at_head=None,
        ),
        AssessmentScenario(
            name='stale',
            taken_at='old0001',
            head=HEAD,
            outcome='pass',
            state='stale',
            outcome_at_head=None,
        ),
        AssessmentScenario(
            name='no-head-is-never-at-head',
            taken_at=HEAD,
            head=None,
            outcome='pass',
            state='stale',
            outcome_at_head=None,
        ),
        AssessmentScenario(
            name='at-head-pass',
            taken_at=HEAD,
            head=HEAD,
            outcome='pass',
            state='at-head',
            outcome_at_head='pass',
        ),
        AssessmentScenario(
            name='at-head-fail',
            taken_at=HEAD,
            head=HEAD,
            outcome='fail',
            state='at-head',
            outcome_at_head='fail',
        ),
    ]
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


class TestCommandPolicy:
    def find_problem(self, scenario: ShapeScenario) -> Exception | None:
        command = replace(
            create_command(scenario.key, argv=scenario.argv),
            timeout=scenario.timeout,
            approved_by=scenario.approved_by,
        )
        return CommandPolicy(command=command).get_command_problem()

    @command_shape_cases()
    def test_command_shape(self, scenario: ShapeScenario) -> None:
        problem = self.find_problem(scenario)

        assert type(problem) is (scenario.error_type or type(None))

    @argv_cases()
    def test_argv_is_a_non_empty_list_of_strings(self, value: object, expected: bool) -> None:
        assert is_argv(value) is expected


class TestApprovalPolicy:
    held = (recorded(FIRST_KEY),)

    def test_changed_argv_is_refused(self) -> None:
        changed = create_command(FIRST_KEY, argv=('make', 'lint'))

        problem = ApprovalPolicy(commands=[changed], held=self.held).get_approval_problem()

        assert isinstance(problem, ChangedCommandError)
        assert problem.command_key == FIRST_KEY

    def test_two_argvs_for_one_new_id_in_a_batch_are_refused(self) -> None:
        batch = [create_command(SECOND_KEY), create_command(SECOND_KEY, argv=('make', 'lint'))]

        problem = ApprovalPolicy(commands=batch, held=self.held).get_approval_problem()

        assert isinstance(problem, ChangedCommandError)

    def test_shape_problem_is_returned_before_a_change(self) -> None:
        batch = [create_command(FIRST_KEY, argv=('make', 'lint')), create_command('bad id')]

        problem = ApprovalPolicy(commands=batch, held=self.held).get_approval_problem()

        assert isinstance(problem, InvalidCommandKeyError)

    def test_identical_reapproval_is_not_new(self) -> None:
        policy = ApprovalPolicy(commands=[create_command(FIRST_KEY)], held=self.held)

        assert policy.get_approval_problem() is None
        assert policy.new_commands == []

    def test_new_commands_keep_the_first_of_a_repeated_id_in_order(self) -> None:
        second = create_command(SECOND_KEY)
        batch = [second, create_command(FIRST_KEY), second]

        policy = ApprovalPolicy(commands=batch, held=self.held)

        assert policy.get_approval_problem() is None
        assert policy.new_commands == [second]


class TestPickPolicy:
    held = (recorded(SECOND_KEY), recorded(FIRST_KEY))

    def test_a_ticket_with_no_commands_has_no_contract(self) -> None:
        problem = PickPolicy(slug=SLUG, held=(), asked=None).get_pick_problem()

        assert isinstance(problem, NoContractError)
        assert problem.slug == SLUG

    def test_ids_outside_the_contract_are_unknown(self) -> None:
        asked = [FIRST_KEY, 'T9.AC-9', 'T8.AC-8']

        problem = PickPolicy(slug=SLUG, held=self.held, asked=asked).get_pick_problem()

        assert isinstance(problem, UnknownCommandError)
        assert problem.unknown == ('T9.AC-9', 'T8.AC-8')

    def test_no_ids_picks_every_command_in_key_order(self) -> None:
        policy = PickPolicy(slug=SLUG, held=self.held, asked=None)

        assert policy.get_pick_problem() is None
        assert [command.key for command in policy.picked_commands] == [FIRST_KEY, SECOND_KEY]

    def test_asked_ids_pick_in_the_order_asked(self) -> None:
        policy = PickPolicy(slug=SLUG, held=self.held, asked=[SECOND_KEY, FIRST_KEY])

        assert policy.get_pick_problem() is None
        assert [command.key for command in policy.picked_commands] == [SECOND_KEY, FIRST_KEY]


class TestReceiptAssessment:
    @assessment_cases()
    def test_assessment_at_a_head(self, scenario: AssessmentScenario) -> None:
        receipt = create_receipt(FIRST_KEY, scenario.outcome)
        taken = None if scenario.taken_at is None else replace(receipt, head=scenario.taken_at)

        assessment = ReceiptAssessment(receipt=taken, head=scenario.head)

        assert assessment.state == scenario.state
        assert assessment.outcome_at_head == scenario.outcome_at_head
        assert assessment.is_passing is (scenario.outcome_at_head == 'pass')
