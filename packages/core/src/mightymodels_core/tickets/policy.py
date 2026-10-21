"""What ticket.yml must hold beyond its types: the rules the old ticket service refused.

The parser has already refused unknown keys and values of the wrong type, and it leaves every
field optional, so the policy refuses each required field that is missing. It collects every
problem into one `InvalidTicketError`, and the call site raises it.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.primitives import (
    REVIEWER_AGENTS,
    InvalidSlugError,
    ReservedSlugError,
    parse_slug,
)
from mightymodels_core.primitives.routing import create_routing_table
from mightymodels_core.tickets.errors import (
    BranchNameRequiredError,
    ClosedTicketError,
    DetachedHeadError,
    InvalidTicketError,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable

    from mightymodels_core.primitives import AgentName, RoutingTable, Slug
    from mightymodels_core.tickets.records import BranchChoice, TicketRecord
    from mightymodels_core.workspace import TicketFile

PRIMARY_AGENT = 'primary-agent'
IMPLEMENTERS: frozenset[str] = frozenset({'engineer', 'architect'})


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketOptions:
    context_limit: int = 6
    routing: RoutingTable = field(default_factory=create_routing_table)

    @property
    def known_workers(self) -> frozenset[str]:
        return frozenset({PRIMARY_AGENT, *self.routing.models})

    @property
    def fixed_workers(self) -> frozenset[AgentName]:
        return frozenset(self.routing.models) - REVIEWER_AGENTS


def declared_slugs(declared: Iterable[str]) -> list[Slug]:
    parsed = map(parse_slug, declared)
    return [slug for slug in parsed if not isinstance(slug, InvalidSlugError | ReservedSlugError)]


def get_investigation_problem(key: str, unrecorded: Collection[Slug]) -> str | None:
    slug = parse_slug(key)
    if isinstance(slug, InvalidSlugError | ReservedSlugError):
        return f'investigation {key} is not a valid id'

    if slug in unrecorded:
        return f'investigation {key} has no ledger'

    return None


def get_branch_problem(
    choice: BranchChoice, name: str, current: str | None
) -> BranchNameRequiredError | DetachedHeadError | None:
    if choice == 'new':
        return None if name.strip() else BranchNameRequiredError()

    return None if current is not None else DetachedHeadError()


def get_closed_problem(record: TicketRecord) -> ClosedTicketError | None:
    return ClosedTicketError(slug=record.slug) if record.status == 'closed' else None


def branch_of(choice: BranchChoice, name: str, current: str | None) -> str:
    if choice == 'new':
        return name.strip()

    return current or ''


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketPolicy:
    ticket: TicketFile
    slug: Slug
    unrecorded: Collection[Slug] = ()
    options: TicketOptions = field(default_factory=TicketOptions)

    def top_level_problems(self) -> list[str]:
        problems: list[str] = []
        if self.ticket.task != self.slug:
            problems.append(f'task must be {self.slug!r}')

        if not bool(self.ticket.summary):
            problems.append('summary is empty')

        context = self.ticket.context
        if context is None or not 1 <= len(context) <= self.options.context_limit:
            problems.append(f'context must be a list of 1 to {self.options.context_limit} lines')

        return problems

    def handoff_problems(self) -> list[str]:
        handoff = self.ticket.handoff_context
        problems: list[str] = []
        if handoff is None or not bool(handoff.branch_name):
            problems.append('branch-name is empty')

        if handoff is None or handoff.scope is None:
            problems.append('scope is missing')

        if handoff is None or handoff.plan_first is None:
            problems.append('plan-first is missing')

        return problems

    def model_problems(self) -> list[str]:
        models = self.ticket.subagent_models or {}
        routing = self.options.routing
        unknown = sorted(set(models) - self.options.known_workers)
        missing = sorted(IMPLEMENTERS - {worker for worker, model in models.items() if bool(model)})
        changed = [
            f'{worker} runs on {routing.fixed_model(worker)}'
            for worker in sorted(self.options.fixed_workers)
            if models.get(worker) not in (None, '', routing.fixed_model(worker))
        ]
        problems: list[str] = []
        if unknown:
            problems.append(f'subagent-models has unknown workers {unknown}')

        if missing:
            problems.append(f'subagent-models needs a model for {missing}')

        if changed:
            problems.append(f'subagent-models cannot change a fixed worker: {changed}')

        return problems

    def investigation_problems(self) -> list[str]:
        declared = self.ticket.investigations or ()
        found = (get_investigation_problem(key, self.unrecorded) for key in declared)
        return [problem for problem in found if problem is not None]

    def get_ticket_problem(self) -> InvalidTicketError | None:
        problems = (
            *self.top_level_problems(),
            *self.handoff_problems(),
            *self.model_problems(),
            *self.investigation_problems(),
        )
        if problems:
            return InvalidTicketError(problems=problems)

        return None
