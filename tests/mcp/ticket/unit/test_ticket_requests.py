from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pytest
from mcp.server.elicitation import render_elicitation_schema
from mcp.server.mcpserver.resolve import Elicit
from mightymodels_mcp.forms.needs_input import NEEDS_INPUT
from mightymodels_mcp.server.requests import NAME_LIMIT, PROSE_LIMIT
from mightymodels_mcp.ticket.schemas import (
    TicketContextRequest,
    TicketWriteRequest,
    create_ticket_answers,
    create_write_choices,
)
from mightymodels_mcp.ticket.tools import ask_write_round, describe_unanswered
from pydantic import ValidationError

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

INTERVIEW = MappingProxyType({
    'slug': 'probe-ticket',
    'summary': 'Add the ticket tools',
    'context': ('the first concept package',),
})


def create_write_request(**given: Any) -> TicketWriteRequest:
    return TicketWriteRequest.model_validate({**INTERVIEW, **given})


@dataclass(slots=True, kw_only=True, frozen=True)
class RoundScenario:
    name: str
    request: TicketWriteRequest
    fields: frozenset[str]
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


def write_request_oversized_cases() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param({'summary': 'x' * (PROSE_LIMIT + 1)}, id='summary'),
        pytest.param({'context': ('x' * (PROSE_LIMIT + 1),)}, id='context-line'),
        pytest.param({'branch': 'x' * (NAME_LIMIT + 1)}, id='branch'),
        pytest.param({'jira': 'x' * (NAME_LIMIT + 1)}, id='jira'),
        pytest.param({'investigations': ('x' * 65,)}, id='investigation'),
        pytest.param({'slug': 'Not A Slug'}, id='slug'),
        pytest.param({'scope': 'huge'}, id='scope'),
        pytest.param({'unknown': 'field'}, id='extra-field'),
    ]
    return pytest.mark.parametrize('change', cases)


def write_request_at_limit_cases() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param({'summary': 'x' * PROSE_LIMIT}, id='summary'),
        pytest.param({'branch': 'x' * NAME_LIMIT}, id='branch'),
        pytest.param({'investigations': ('x' * 64,)}, id='investigation'),
    ]
    return pytest.mark.parametrize('change', cases)


def write_round_fields_cases() -> pytest.MarkDecorator:
    all_omitted = RoundScenario(
        name='all-omitted',
        request=create_write_request(),
        fields=frozenset({'scope', 'compaction', 'branch', 'branch_name'}),
    )
    scope_omitted = RoundScenario(
        name='scope-omitted',
        request=create_write_request(compaction=False, branch='main'),
        fields=frozenset({'scope'}),
    )
    branch_omitted = RoundScenario(
        name='branch-omitted',
        request=create_write_request(scope='sm', compaction=True),
        fields=frozenset({'branch', 'branch_name'}),
    )
    scenarios = [all_omitted.param, scope_omitted.param, branch_omitted.param]
    return pytest.mark.parametrize('scenario', scenarios)


class TestTicketWriteRequest:
    @write_request_oversized_cases()
    def test_invalid_field_is_refused(self, change: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            create_write_request(**change)

    @write_request_at_limit_cases()
    def test_field_at_its_limit_is_accepted(self, change: dict[str, Any]) -> None:
        assert create_write_request(**change).slug == INTERVIEW['slug']

    @pytest.mark.parametrize('branch', ['-x', 'my branch'])
    def test_invalid_branch_is_refused(self, branch: str) -> None:
        with pytest.raises(ValidationError):
            create_write_request(branch=branch)

    def test_context_line_over_the_prose_limit_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            TicketContextRequest(slug='probe-ticket', context=('x' * (PROSE_LIMIT + 1),))


class TestWriteRound:
    answered = create_write_request(scope='med', compaction=True, branch='main')
    compaction_given = create_write_request(compaction=True)

    @write_round_fields_cases()
    def test_round_asks_only_the_omitted_fields(self, scenario: RoundScenario) -> None:
        ask = ask_write_round(scenario.request)

        assert isinstance(ask, Elicit)
        assert set(render_elicitation_schema(ask.schema)['properties']) == scenario.fields

    def test_answered_request_asks_nothing(self) -> None:
        assert not isinstance(ask_write_round(self.answered), Elicit)

    def test_needs_input_names_each_omitted_argument(self) -> None:
        text = describe_unanswered(self.compaction_given)

        assert text.startswith(NEEDS_INPUT)
        assert 'choices: sm, med, large\npass: scope\n' in text
        assert 'pass: compaction' not in text
        assert 'pass: branch (the current branch name, or the new branch name)\n' in text


class TestWriteAnswers:
    interview = create_write_request()
    answered = create_write_request(scope='med', compaction=True, branch='main')
    form = MappingProxyType({
        'scope': 'large',
        'compaction': 'false',
        'branch': 'new',
        'branch_name': 'feat/tickets',
    })

    def test_form_answers_fill_the_omitted_choices(self) -> None:
        choices = create_write_choices(self.interview, dict(self.form))

        assert (choices.scope, choices.compaction) == ('large', False)
        assert (choices.branch, choices.branch_name) == ('new', 'feat/tickets')

    def test_named_branch_is_taken_as_a_new_branch_of_that_name(self) -> None:
        choices = create_write_choices(self.answered, {})

        assert (choices.branch, choices.branch_name) == ('new', 'main')

    def test_compaction_becomes_plan_first(self) -> None:
        choices = create_write_choices(self.answered, {})

        answers = create_ticket_answers(self.answered, choices, 'main')

        assert (answers.plan_first, answers.scope, answers.branch) == (True, 'med', 'main')
