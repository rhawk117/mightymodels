from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import Slug
from mightymodels_core.tickets import InvalidTicketError, NotStagedError, TicketSource
from mightymodels_core.workspace import (
    LoneSurrogateError,
    TicketFileSyntaxError,
    TicketFileTypeError,
)

from .conftest import RECORDED_INVESTIGATIONS, SERVICE_MOMENT

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.tickets import TicketRepository, TicketService

SLUG = Slug('add-widget')
OTHER = Slug('other-widget')
PATH = '.mightymodels/add-widget/ticket.yml'
TICKET_TEXT = """task: "add-widget"
summary: "add the widget"
triaged-at: "2026-01-02T03:04:05Z"
handoff-context:
  scope: "med"
  plan-first: true
  branch-name: "feat/widget"
subagent-models:
  primary-agent: null
  engineer: "sonnet"
  architect: "opus"
companion-docs:
  issue-number: 7
  jira-key: "WID-1"
context:
  - "one line"
  - "two lines"
investigations:
  - "first-look"
"""
SECRET_TEXT = TICKET_TEXT.replace('add the widget', 'add the widget, token ghp_' + 'a' * 36)


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusedSource:
    name: str
    text: str
    error_type: type[Exception]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def ticket_source_refusal_cases() -> pytest.MarkDecorator:
    scenarios = [
        RefusedSource(
            name='syntax-outside-the-subset',
            text=TICKET_TEXT.replace('context:\n', 'context: [a]\n'),
            error_type=TicketFileSyntaxError,
        ),
        RefusedSource(
            name='unknown-key',
            text=TICKET_TEXT + 'extra: 1\n',
            error_type=TicketFileTypeError,
        ),
        RefusedSource(
            name='broken-policy-rule',
            text=TICKET_TEXT.replace('add-widget"\nsummary', 'other"\nsummary'),
            error_type=InvalidTicketError,
        ),
        RefusedSource(
            name='investigation-without-a-ledger',
            text=TICKET_TEXT.replace('first-look', 'never-added'),
            error_type=InvalidTicketError,
        ),
        RefusedSource(
            name='empty-file',
            text='',
            error_type=InvalidTicketError,
        ),
    ]
    return pytest.mark.parametrize('refused', [scenario.param for scenario in scenarios])


def create_source(text: str) -> TicketSource:
    return TicketSource(path=PATH, text=text)


class TestStage:
    def test_a_valid_ticket_is_staged_with_its_section(
        self, service: TicketService, fake_repository: TicketRepository
    ) -> None:
        record = service.stage(SLUG, create_source(TICKET_TEXT))

        section = record.section
        assert fake_repository.staged_ticket(SLUG) == record
        assert (record.status, record.investigations) == ('staged', ('first-look',))
        assert (section.ticket, section.summary, section.branch) == (
            PATH,
            'add the widget',
            'feat/widget',
        )
        assert (section.scope, section.plan_first, section.auto_escalate) == ('med', True, False)
        assert (section.tracker.issue, section.tracker.jira) == (7, 'WID-1')
        assert section.models['engineer'] == 'sonnet'
        assert section.context == ('one line', 'two lines')

    def test_the_section_is_validated_at_the_clock_time(self, service: TicketService) -> None:
        record = service.stage(SLUG, create_source(TICKET_TEXT))

        assert record.section.validated_at == SERVICE_MOMENT

    def test_a_secret_in_the_summary_is_redacted_before_it_is_staged(
        self, service: TicketService
    ) -> None:
        record = service.stage(SLUG, create_source(SECRET_TEXT))

        assert 'ghp_' not in record.section.summary

    def test_staging_again_replaces_the_section_and_keeps_the_status(
        self, service: TicketService, fake_repository: TicketRepository
    ) -> None:
        service.stage(SLUG, create_source(TICKET_TEXT))
        fake_repository.mark_in_progress(SLUG)

        record = service.stage(SLUG, create_source(TICKET_TEXT.replace('add the', 'add one')))

        assert (record.status, record.section.summary) == ('in-progress', 'add one widget')

    @ticket_source_refusal_cases()
    def test_a_refused_source_stages_nothing(
        self, service: TicketService, fake_repository: TicketRepository, refused: RefusedSource
    ) -> None:
        with pytest.raises(refused.error_type):
            service.stage(SLUG, create_source(refused.text))

        assert fake_repository.ticket(SLUG) is None

    def test_a_policy_refusal_lists_the_problem(self, service: TicketService) -> None:
        text = TICKET_TEXT.replace('first-look', 'never-added')

        with pytest.raises(InvalidTicketError) as raised:
            service.stage(SLUG, create_source(text))

        assert raised.value.problems == ('investigation never-added has no ledger',)

    def test_recorded_investigations_are_linked(self, service: TicketService) -> None:
        both = TICKET_TEXT.replace('  - "first-look"', '  - "first-look"\n  - "second-look"')

        record = service.stage(SLUG, create_source(both))

        assert record.investigations == RECORDED_INVESTIGATIONS


class TestShow:
    def test_a_staged_ticket_is_shown(self, service: TicketService) -> None:
        staged = service.stage(SLUG, create_source(TICKET_TEXT))

        assert service.show(SLUG) == staged

    def test_a_ticket_never_staged_is_refused(self, service: TicketService) -> None:
        with pytest.raises(NotStagedError):
            service.show(SLUG)


class TestUpdateContext:
    def test_the_new_text_and_the_staged_record_come_back(
        self, service: TicketService, fake_repository: TicketRepository
    ) -> None:
        service.stage(SLUG, create_source(TICKET_TEXT))

        update = service.update_context(SLUG, create_source(TICKET_TEXT), ('fresh',))

        assert update.record.section.context == ('fresh',)
        assert fake_repository.staged_ticket(SLUG) == update.record
        assert update.text == TICKET_TEXT.replace(
            'context:\n  - "one line"\n  - "two lines"', 'context:\n  - "fresh"'
        )

    def test_a_context_over_the_limit_is_refused_and_the_stage_is_kept(
        self, service: TicketService
    ) -> None:
        staged = service.stage(SLUG, create_source(TICKET_TEXT))

        with pytest.raises(InvalidTicketError):
            service.update_context(SLUG, create_source(TICKET_TEXT), tuple(map(str, range(7))))

        assert service.show(SLUG) == staged

    def test_a_lone_surrogate_is_refused_and_the_stage_is_kept(
        self, service: TicketService
    ) -> None:
        staged = service.stage(SLUG, create_source(TICKET_TEXT))

        with pytest.raises(LoneSurrogateError):
            service.update_context(SLUG, create_source(TICKET_TEXT), ('bad \ud800',))

        assert service.show(SLUG) == staged

    def test_an_empty_context_is_refused(self, service: TicketService) -> None:
        with pytest.raises(InvalidTicketError):
            service.update_context(SLUG, create_source(TICKET_TEXT), ())


class TestUnclosedOnBranch:
    def test_the_unclosed_tickets_on_the_branch_come_back_in_slug_order(
        self, service: TicketService, fake_repository: TicketRepository
    ) -> None:
        service.stage(SLUG, create_source(TICKET_TEXT))
        service.stage(OTHER, create_source(TICKET_TEXT.replace('"add-widget"', '"other-widget"')))
        fake_repository.mark_closed(OTHER)

        assert service.unclosed_on_branch('feat/widget') == [SLUG]
        assert service.unclosed_on_branch('elsewhere') == []
