"""Synthesized AskUserQuestion payloads, a handler over a real data directory and what it wrote."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import msgspec
from mightymodels_core.edge import PLUGIN_DATA_VARIABLE, open_state
from mightymodels_core.investigations import StartRequest
from mightymodels_core.primitives import Slug, SystemClock
from mightymodels_core.session_pointers import SqliteSessionPointerRepository
from mightymodels_core.ticket_decisions import SqliteTicketDecisionRepository
from mightymodels_core.tickets import SqliteTicketRepository
from mightymodels_core.tickets.policy import OpenTicket
from mightymodels_core.units_of_work import InvestigationWork, read_entry, write_entry
from mightymodels_hooks.ask_recorder import AskRecorderHandler
from mightymodels_hooks.payloads import PostToolUsePayload

from tests.core.tasks.repository_builders import create_ticket_section

if TYPE_CHECKING:
    import io
    from pathlib import Path

    from mightymodels_core.investigations import LedgerRecord
    from mightymodels_core.ticket_decisions import TicketDecision
    from mightymodels_core.vocabulary.session_pointers import PointerKind

SESSION_ID = 'session-1'
TICKET = Slug('port-it')
FIRST = 'Which store should hold the cache?'
SECOND = 'Which checks run before a merge?'
SECRET = 'sk-' + 'a1B2c3D4' * 4


def ask_payload(
    answers: object, annotations: object = None, **result: object
) -> PostToolUsePayload:
    tool_response: dict[str, object] = {'questions': [], 'answers': answers}
    if annotations is not None:
        tool_response['annotations'] = annotations

    return real_payload(tool_response | result)


def real_payload(result: dict[str, object]) -> PostToolUsePayload:
    return PostToolUsePayload(
        session_id=SESSION_ID,
        tool_name='AskUserQuestion',
        tool_input={'questions': []},
        tool_response=result,
    )


def two_answers() -> dict[str, str]:
    return {FIRST: 'Redis', SECOND: 'Lint, Tests'}


@dataclass(slots=True, kw_only=True, frozen=True)
class RecorderHarness:
    checkout: Path
    data_directory: Path
    stderr: io.StringIO

    def handler(self) -> AskRecorderHandler:
        environ = {PLUGIN_DATA_VARIABLE: str(self.data_directory)}
        return AskRecorderHandler(environ=environ, stderr=self.stderr, clock=SystemClock())

    async def record(self, payload: PostToolUsePayload) -> str | None:
        return await self.handler().handle(msgspec.structs.replace(payload, cwd=str(self.checkout)))

    async def point(self, kind: PointerKind, key: str) -> None:
        async with open_state(self.data_directory, self.checkout) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                pointers = SqliteSessionPointerRepository(
                    unit=entry.unit, repository_id=entry.repository_id, clock=SystemClock()
                )
                pointers.record(SESSION_ID, kind, key)

    async def start_investigation(self) -> Slug:
        async with open_state(self.data_directory, self.checkout) as state:
            work = InvestigationWork(
                database=state.database,
                repository_key=state.checkout.repository_key(),
                clock=SystemClock(),
            )
            with work.write() as unit:
                started = unit.investigations.start(StartRequest(target='cache', kind='change'))
        await self.point('investigation', started.investigation)
        return started.investigation

    async def ledger(self, key: Slug) -> tuple[LedgerRecord, ...]:
        async with open_state(self.data_directory, self.checkout) as state:
            work = InvestigationWork(
                database=state.database,
                repository_key=state.checkout.repository_key(),
                clock=SystemClock(),
            )
            with work.read() as unit:
                return unit.investigations.render(key).records

    async def stage_ticket(self, *, closed: bool = False) -> int:
        async with open_state(self.data_directory, self.checkout) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                tickets = SqliteTicketRepository(unit=entry.unit, repository_id=entry.repository_id)
                ticket_id = tickets.stage(TICKET, create_ticket_section(TICKET), ()).id
                if closed:
                    tickets.mark_closed(OpenTicket(id=ticket_id, slug=TICKET))
        await self.point('ticket', TICKET)
        return ticket_id

    async def ticket_decisions(self, ticket_id: int) -> tuple[TicketDecision, ...]:
        async with open_state(self.data_directory, self.checkout) as state:
            with read_entry(state.database, state.checkout.repository_key()) as entry:
                decisions = SqliteTicketDecisionRepository(unit=entry.unit, clock=SystemClock())
                return decisions.decisions(ticket_id)
