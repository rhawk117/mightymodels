"""The ticket service: stages a ticket from ticket.yml text, shows it and names those on a branch.

It takes values and returns values. The caller reads the file, writes the text this service
returns and owns the unit of work, so the service never touches the filesystem or git.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.primitives import redact
from mightymodels_core.tickets.policy import TicketOptions, TicketPolicy, declared_slugs
from mightymodels_core.tickets.records import TicketSection, Tracker
from mightymodels_core.workspace import (
    CompanionDocsFile,
    HandoffContextFile,
    TicketFile,
    parse_ticket_file,
)
from mightymodels_core.workspace.ticket_text import with_context

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from mightymodels_core.investigations import InvestigationRepository
    from mightymodels_core.primitives import Clock, Slug
    from mightymodels_core.tickets.records import TicketRecord
    from mightymodels_core.tickets.repository import TicketRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketSource:
    path: str
    text: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ContextUpdate:
    record: TicketRecord
    text: str


def create_section(ticket: TicketFile, *, path: str, validated_at: datetime) -> TicketSection:
    handoff = ticket.handoff_context or HandoffContextFile()
    companions = ticket.companion_docs or CompanionDocsFile()
    return TicketSection(
        ticket=path,
        summary=redact(ticket.summary or ''),
        branch=handoff.branch_name or '',
        scope=handoff.scope or 'med',
        plan_first=bool(handoff.plan_first),
        auto_escalate=bool(handoff.auto_escalate),
        models=dict(ticket.subagent_models or {}),
        tracker=Tracker(issue=companions.issue_number, jira=companions.jira_key),
        context=ticket.context or (),
        validated_at=validated_at,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketService:
    tickets: TicketRepository
    investigations: InvestigationRepository
    clock: Clock
    options: TicketOptions = field(default_factory=TicketOptions)

    def stage(self, slug: Slug, source: TicketSource) -> TicketRecord:
        parsed = parse_ticket_file(source.text)
        if not isinstance(parsed, TicketFile):
            raise parsed

        declared = parsed.investigations or ()
        unrecorded = self.investigations.unrecorded(declared_slugs(declared))
        policy = TicketPolicy(ticket=parsed, slug=slug, unrecorded=unrecorded, options=self.options)
        if problem := policy.get_ticket_problem():
            raise problem

        section = create_section(parsed, path=source.path, validated_at=self.clock.now())
        return self.tickets.stage(slug, section, declared)

    def show(self, slug: Slug) -> TicketRecord:
        return self.tickets.staged_ticket(slug)

    def update_context(
        self, slug: Slug, source: TicketSource, context: Sequence[str]
    ) -> ContextUpdate:
        text = with_context(source.text, context)
        record = self.stage(slug, TicketSource(path=source.path, text=text))
        return ContextUpdate(record=record, text=text)

    def unclosed_on_branch(self, branch: str) -> list[Slug]:
        return self.tickets.all_unclosed_on_branch(branch)
