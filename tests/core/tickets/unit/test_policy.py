from dataclasses import dataclass
from dataclasses import replace as replace_record
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import Slug
from mightymodels_core.tickets import (
    ClosedTicketError,
    InvalidTicketError,
    TicketPolicy,
    TicketRecord,
)
from mightymodels_core.tickets.policy import OpenTicket, get_closed_problem, open_ticket
from mightymodels_core.workspace import CompanionDocsFile, HandoffContextFile, TicketFile
from msgspec.structs import replace

from tests.core.tickets.ticket_builders import create_section

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

SLUG = Slug('add-widget')
UNRECORDED = Slug('never-added')
VALID_HANDOFF = HandoffContextFile(
    branch_name='feat/widget', scope='med', plan_first=True, auto_escalate=False
)
VALID_MODELS = {'primary-agent': None, 'engineer': 'sonnet', 'architect': 'opus'}
VALID_TICKET = TicketFile(
    task=str(SLUG),
    summary='add the widget',
    triaged_at='2026-01-02T03:04:05Z',
    handoff_context=VALID_HANDOFF,
    subagent_models=VALID_MODELS,
    companion_docs=CompanionDocsFile(issue_number=7),
    context=('one line',),
    investigations=(),
)


@dataclass(slots=True, kw_only=True, frozen=True)
class PolicyScenario:
    name: str
    ticket: TicketFile
    problems: tuple[str, ...]
    unrecorded: tuple[Slug, ...] = ()
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


def create_ticket(**changes: object) -> TicketFile:
    return replace(VALID_TICKET, **changes)


def create_handoff_ticket(**changes: object) -> TicketFile:
    return create_ticket(handoff_context=replace(VALID_HANDOFF, **changes))


def create_models_ticket(**changes: str | None) -> TicketFile:
    return create_ticket(subagent_models={**VALID_MODELS, **changes})


def ticket_top_level_refusal_cases() -> pytest.MarkDecorator:
    scenarios = [
        PolicyScenario(
            name='task-is-not-the-slug',
            ticket=create_ticket(task='other-ticket'),
            problems=("task must be 'add-widget'",),
        ),
        PolicyScenario(
            name='task-is-missing',
            ticket=create_ticket(task=None),
            problems=("task must be 'add-widget'",),
        ),
        PolicyScenario(
            name='summary-is-empty',
            ticket=create_ticket(summary=''),
            problems=('summary is empty',),
        ),
        PolicyScenario(
            name='summary-is-missing',
            ticket=create_ticket(summary=None),
            problems=('summary is empty',),
        ),
        PolicyScenario(
            name='context-is-empty',
            ticket=create_ticket(context=()),
            problems=('context must be a list of 1 to 6 lines',),
        ),
        PolicyScenario(
            name='context-is-missing',
            ticket=create_ticket(context=None),
            problems=('context must be a list of 1 to 6 lines',),
        ),
        PolicyScenario(
            name='context-has-seven-lines',
            ticket=create_ticket(context=tuple(map(str, range(7)))),
            problems=('context must be a list of 1 to 6 lines',),
        ),
    ]
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


def ticket_handoff_refusal_cases() -> pytest.MarkDecorator:
    scenarios = [
        PolicyScenario(
            name='branch-name-is-empty',
            ticket=create_handoff_ticket(branch_name=''),
            problems=('branch-name is empty',),
        ),
        PolicyScenario(
            name='branch-name-is-missing',
            ticket=create_handoff_ticket(branch_name=None),
            problems=('branch-name is empty',),
        ),
        PolicyScenario(
            name='scope-is-missing',
            ticket=create_handoff_ticket(scope=None),
            problems=('scope is missing',),
        ),
        PolicyScenario(
            name='plan-first-is-missing',
            ticket=create_handoff_ticket(plan_first=None),
            problems=('plan-first is missing',),
        ),
        PolicyScenario(
            name='handoff-context-is-missing',
            ticket=create_ticket(handoff_context=None),
            problems=('branch-name is empty', 'scope is missing', 'plan-first is missing'),
        ),
    ]
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


def ticket_model_refusal_cases() -> pytest.MarkDecorator:
    scenarios = [
        PolicyScenario(
            name='unknown-worker',
            ticket=create_models_ticket(scout='haiku'),
            problems=("subagent-models has unknown workers ['scout']",),
        ),
        PolicyScenario(
            name='implementer-model-is-missing',
            ticket=create_models_ticket(engineer=None),
            problems=("subagent-models needs a model for ['engineer']",),
        ),
        PolicyScenario(
            name='implementer-model-is-empty',
            ticket=create_models_ticket(architect=''),
            problems=("subagent-models needs a model for ['architect']",),
        ),
        PolicyScenario(
            name='subagent-models-is-missing',
            ticket=create_ticket(subagent_models=None),
            problems=("subagent-models needs a model for ['architect', 'engineer']",),
        ),
        PolicyScenario(
            name='fixed-worker-is-changed',
            ticket=create_models_ticket(**{'code-scout': 'opus'}),
            problems=(
                "subagent-models cannot change a fixed worker: ['code-scout runs on haiku']",
            ),
        ),
    ]
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


def ticket_investigation_refusal_cases() -> pytest.MarkDecorator:
    scenarios = [
        PolicyScenario(
            name='investigation-key-is-not-a-slug',
            ticket=create_ticket(investigations=('not a slug!',)),
            problems=('investigation not a slug! is not a valid id',),
        ),
        PolicyScenario(
            name='investigation-key-is-reserved',
            ticket=create_ticket(investigations=('archives',)),
            problems=('investigation archives is not a valid id',),
        ),
        PolicyScenario(
            name='investigation-has-no-ledger',
            ticket=create_ticket(investigations=(str(UNRECORDED),)),
            unrecorded=(UNRECORDED,),
            problems=('investigation never-added has no ledger',),
        ),
    ]
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


def ticket_accepted_cases() -> pytest.MarkDecorator:
    scenarios = [
        PolicyScenario(name='valid-ticket', ticket=VALID_TICKET, problems=()),
        PolicyScenario(
            name='context-has-six-lines',
            ticket=create_ticket(context=tuple(map(str, range(6)))),
            problems=(),
        ),
        PolicyScenario(
            name='reviewer-runs-on-any-model',
            ticket=create_models_ticket(**{'merge-vader': 'fable'}),
            problems=(),
        ),
        PolicyScenario(
            name='fixed-worker-keeps-its-model',
            ticket=create_models_ticket(**{'code-scout': 'haiku'}),
            problems=(),
        ),
    ]
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


def find_problems(scenario: PolicyScenario) -> tuple[str, ...]:
    policy = TicketPolicy(ticket=scenario.ticket, slug=SLUG, unrecorded=scenario.unrecorded)
    problem = policy.get_ticket_problem()
    if problem is None:
        return ()

    assert isinstance(problem, InvalidTicketError)
    return problem.problems


class TestTicketPolicy:
    @ticket_accepted_cases()
    def test_a_ticket_that_keeps_every_rule_has_no_problem(self, scenario: PolicyScenario) -> None:
        assert find_problems(scenario) == scenario.problems

    @ticket_top_level_refusal_cases()
    def test_task_summary_and_context_rules_are_refused(self, scenario: PolicyScenario) -> None:
        assert find_problems(scenario) == scenario.problems

    @ticket_handoff_refusal_cases()
    def test_branch_name_scope_and_plan_first_rules_are_refused(
        self, scenario: PolicyScenario
    ) -> None:
        assert find_problems(scenario) == scenario.problems

    @ticket_model_refusal_cases()
    def test_subagent_model_rules_are_refused(self, scenario: PolicyScenario) -> None:
        assert find_problems(scenario) == scenario.problems

    @ticket_investigation_refusal_cases()
    def test_investigation_key_and_ledger_rules_are_refused(self, scenario: PolicyScenario) -> None:
        assert find_problems(scenario) == scenario.problems

    @pytest.fixture
    def two_rules(self) -> PolicyScenario:
        return PolicyScenario(
            name='two-rules',
            ticket=create_ticket(summary='', context=()),
            problems=('summary is empty', 'context must be a list of 1 to 6 lines'),
        )

    def test_every_broken_rule_is_reported_together(self, two_rules: PolicyScenario) -> None:
        assert find_problems(two_rules) == two_rules.problems


class TestClosedProblem:
    @pytest.fixture
    def open_record(self) -> TicketRecord:
        return TicketRecord(
            id=1,
            slug=SLUG,
            status='in-progress',
            section=create_section(SLUG, 'main'),
            investigations=(),
        )

    def test_a_closed_record_gives_the_problem(self, open_record: TicketRecord) -> None:
        problem = get_closed_problem(replace_record(open_record, status='closed'))

        assert isinstance(problem, ClosedTicketError)
        assert problem.slug == SLUG

    def test_an_open_record_gives_no_problem(self, open_record: TicketRecord) -> None:
        assert get_closed_problem(open_record) is None

    def test_a_closed_record_gives_no_open_ticket(self, open_record: TicketRecord) -> None:
        result = open_ticket(replace_record(open_record, status='closed'))

        assert isinstance(result, ClosedTicketError)

    def test_an_open_record_gives_an_open_ticket(self, open_record: TicketRecord) -> None:
        assert open_ticket(open_record) == OpenTicket(id=open_record.id, slug=SLUG)
