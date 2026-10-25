from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.primitives import Slug
from mightymodels_core.tickets import (
    BranchNameRequiredError,
    DetachedHeadError,
    InvalidTicketError,
    TicketExistsError,
    TicketOptions,
    TicketSource,
    branch_of,
)
from mightymodels_core.workspace import LoneSurrogateError, TicketFile, parse_ticket_file

from tests.core.tickets.ticket_builders import (
    SERVICE_MOMENT,
    create_answers,
    create_free_slot,
    create_service,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.tickets import TicketAnswers, TicketService, TicketSlot
    from mightymodels_core.tickets.records import BranchChoice

SLUG = Slug('add-widget')
SOURCE_PATH = '.mightymodels/add-widget/ticket.yml'


@dataclass(slots=True, kw_only=True, frozen=True)
class BranchRequest:
    name: str
    choice: BranchChoice
    typed: str
    current: str | None
    expected: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


@dataclass(slots=True, kw_only=True, frozen=True)
class BranchRefusal:
    name: str
    choice: BranchChoice
    typed: str
    current: str | None
    error_type: type[Exception]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def branch_named_cases() -> pytest.MarkDecorator:
    scenarios = [
        BranchRequest(
            name='new-name-is-stripped',
            choice='new',
            typed='  feat/new  ',
            current='main',
            expected='feat/new',
        ),
        BranchRequest(
            name='new-ignores-a-detached-head',
            choice='new',
            typed='feat/new',
            current=None,
            expected='feat/new',
        ),
        BranchRequest(
            name='current-takes-git-branch',
            choice='current',
            typed='',
            current='main',
            expected='main',
        ),
    ]
    return pytest.mark.parametrize('named', [scenario.param for scenario in scenarios])


def branch_refusal_cases() -> pytest.MarkDecorator:
    scenarios = [
        BranchRefusal(
            name='new-blank-name',
            choice='new',
            typed='   ',
            current='main',
            error_type=BranchNameRequiredError,
        ),
        BranchRefusal(
            name='new-empty-name',
            choice='new',
            typed='',
            current='main',
            error_type=BranchNameRequiredError,
        ),
        BranchRefusal(
            name='current-on-a-detached-head',
            choice='current',
            typed='',
            current=None,
            error_type=DetachedHeadError,
        ),
    ]
    return pytest.mark.parametrize('refused', [scenario.param for scenario in scenarios])


class TestWrite:
    context_lines = st.text(alphabet=st.characters(exclude_categories=['Cs']))
    summaries = st.text(alphabet=st.characters(exclude_categories=['Cs']), min_size=1)
    contexts = st.lists(context_lines, min_size=1, max_size=TicketOptions().context_limit).map(
        tuple
    )

    @given(summary=summaries, context=contexts)
    @example(summary='add the widget', context=('one line', 'two lines'))
    @example(summary='say "hi" to C:\\temp', context=('a \\ "b"',))
    @example(summary='caf\u00e9 \u2603 tab\there', context=('line\nbreak',))
    @example(summary='next\u0085 sep\u2028 para\u2029 del\x7f c1\x9f', context=('\u2028', '\x80'))
    def test_a_written_ticket_parses_back_to_the_same_answers(
        self, summary: str, context: tuple[str, ...]
    ) -> None:
        answers = create_answers(summary=summary, context=context)
        text = create_service().write(SLUG, answers, create_free_slot())

        parsed = parse_ticket_file(text)
        assert isinstance(parsed, TicketFile)
        assert (parsed.task, parsed.summary, parsed.context) == (
            SLUG,
            answers.summary,
            answers.context,
        )
        assert parsed.investigations == answers.investigations
        assert parsed.companion_docs is not None
        assert (
            parsed.companion_docs.issue_number,
            parsed.companion_docs.jira_key,
            parsed.companion_docs.reference_urls,
        ) == (answers.issue, answers.jira, answers.reference_urls)
        assert parsed.handoff_context is not None
        assert (
            parsed.handoff_context.scope,
            parsed.handoff_context.plan_first,
            parsed.handoff_context.branch_name,
        ) == (answers.scope, answers.plan_first, answers.branch)

    def test_a_written_ticket_stages(
        self, service: TicketService, free_slot: TicketSlot, answers: TicketAnswers
    ) -> None:
        text = service.write(SLUG, answers, free_slot)

        record = service.stage(SLUG, TicketSource(path=SOURCE_PATH, text=text))

        assert record.section.branch == 'feat/widget'

    def test_triaged_at_is_the_clock_time(
        self, service: TicketService, free_slot: TicketSlot, answers: TicketAnswers
    ) -> None:
        text = service.write(SLUG, answers, free_slot)

        parsed = parse_ticket_file(text)
        assert isinstance(parsed, TicketFile)
        assert parsed.triaged_at == SERVICE_MOMENT.isoformat()

    def test_the_primary_agent_and_reviewers_have_no_model(
        self, service: TicketService, free_slot: TicketSlot, answers: TicketAnswers
    ) -> None:
        text = service.write(SLUG, answers, free_slot)

        parsed = parse_ticket_file(text)
        assert isinstance(parsed, TicketFile)
        models = parsed.subagent_models or {}
        assert (models['primary-agent'], models['merge-vader'], models['uncle-bob']) == (
            None,
            None,
            None,
        )
        assert (models['engineer'], models['architect']) == ('sonnet', 'opus')

    def test_an_existing_ticket_file_is_refused(
        self, service: TicketService, taken_slot: TicketSlot, answers: TicketAnswers
    ) -> None:
        with pytest.raises(TicketExistsError) as raised:
            service.write(SLUG, answers, taken_slot)

        assert raised.value.path == taken_slot.path

    def test_answers_that_break_the_policy_are_refused(
        self, service: TicketService, free_slot: TicketSlot
    ) -> None:
        with pytest.raises(InvalidTicketError):
            service.write(SLUG, create_answers(summary=''), free_slot)

    def test_a_lone_surrogate_is_refused_with_its_character(
        self, service: TicketService, free_slot: TicketSlot, surrogate_answers: TicketAnswers
    ) -> None:
        with pytest.raises(LoneSurrogateError) as raised:
            service.write(SLUG, surrogate_answers, free_slot)

        assert raised.value.character == '\ud800'
        assert 'U+D800' in str(raised.value)

    def test_an_investigation_without_a_ledger_is_refused(
        self, service: TicketService, free_slot: TicketSlot, unrecorded_answers: TicketAnswers
    ) -> None:
        with pytest.raises(InvalidTicketError):
            service.write(SLUG, unrecorded_answers, free_slot)


class TestBranchOf:
    @branch_named_cases()
    def test_the_branch_is_named(self, named: BranchRequest) -> None:
        assert branch_of(named.choice, named.typed, named.current) == named.expected

    @branch_refusal_cases()
    def test_an_unnameable_branch_is_refused(self, refused: BranchRefusal) -> None:
        problem = branch_of(refused.choice, refused.typed, refused.current)

        assert type(problem) is refused.error_type
