"""Fakes, payloads and the seeded state the main-thread gate tests share."""

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import msgspec
from mightymodels_core.contract import Approval, ApprovedCommand, Receipt, SqliteContractRepository
from mightymodels_core.edge import PLUGIN_DATA_VARIABLE, open_state
from mightymodels_core.primitives import Slug, redact
from mightymodels_core.tickets import SqliteTicketRepository
from mightymodels_core.units_of_work import write_entry
from mightymodels_hooks.branch_state import BranchTickets, Landing
from mightymodels_hooks.main_thread import MainThreadHandler, main_thread_ruling
from mightymodels_hooks.payloads import PreToolUsePayload
from mightymodels_hooks.rulings import hook_output

from tests.core.tasks.repository_builders import create_ticket_section
from tests.hooks.dispatch.dispatch_builders import (
    BRANCH,
    SLUG,
    verdict_of,
)

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.vocabulary.contract import Phase
    from mightymodels_hooks.branch_state import BranchTicketsOrUnreadable, LandingOrUnreadable

    from tests.hooks.dispatch.dispatch_builders import DispatchHarness, Verdict

PUSH = 'git push origin main'
OUTSIDE_PATH = 'src/app.py'
OTHER_SLUG = Slug('other-it')
WORKER = 'mightymodels:workers:engineer'
COMMAND_KEY = 'T1.AC-1'
MOMENT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeTicketOnBranch:
    in_directory: bool = False
    tickets: BranchTicketsOrUnreadable = field(default_factory=BranchTickets)
    landing: LandingOrUnreadable = field(default_factory=Landing)
    reads: list[str] = field(default_factory=list)

    def ticket_directory_holds(self, file_path: str) -> bool:
        self.reads.append(f'holds {file_path}')
        return self.in_directory

    async def tickets_on_branch(self) -> BranchTicketsOrUnreadable:
        self.reads.append('tickets')
        return self.tickets

    async def landing_on_branch(self) -> LandingOrUnreadable:
        self.reads.append('landing')
        return self.landing


def edit_payload(tool: str, file_path: str, caller: str | None = None) -> PreToolUsePayload:
    return PreToolUsePayload(tool_name=tool, tool_input={'file_path': file_path}, agent_type=caller)


def bash_payload(command: object, caller: str | None = None) -> PreToolUsePayload:
    return PreToolUsePayload(tool_name='Bash', tool_input={'command': command}, agent_type=caller)


def one_unclosed() -> BranchTickets:
    return BranchTickets(unclosed=(SLUG,))


def several_unclosed() -> BranchTickets:
    return BranchTickets(unclosed=(SLUG, OTHER_SLUG))


async def judge(payload: PreToolUsePayload, fake: FakeTicketOnBranch) -> Verdict:
    ruling = await main_thread_ruling(payload, fake)
    return verdict_of(None if ruling is None else json.dumps(hook_output(ruling)))


@dataclass(slots=True, kw_only=True, frozen=True)
class MainThreadHarness:
    dispatch: DispatchHarness

    @property
    def checkout(self) -> Path:
        return self.dispatch.checkout

    def handler(self) -> MainThreadHandler:
        return MainThreadHandler(environ={PLUGIN_DATA_VARIABLE: str(self.dispatch.data_directory)})

    async def verdict(self, payload: PreToolUsePayload) -> Verdict:
        located = msgspec.structs.replace(payload, cwd=str(self.checkout))
        return verdict_of(await self.handler().handle(located))

    async def stage_other_ticket(self, slug: Slug) -> None:
        section = replace(create_ticket_section(slug), branch=BRANCH)
        async with open_state(self.dispatch.data_directory, self.checkout) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                tickets = SqliteTicketRepository(unit=entry.unit, repository_id=entry.repository_id)
                tickets.stage(slug, section, ())

    async def prove(self, head: str, phase: Phase) -> None:
        async with open_state(self.dispatch.data_directory, self.checkout) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                tickets = SqliteTicketRepository(unit=entry.unit, repository_id=entry.repository_id)
                ticket_id = tickets.staged_ticket(SLUG).id
                contracts = SqliteContractRepository(unit=entry.unit)
                command = ApprovedCommand(
                    key=COMMAND_KEY,
                    argv=('make', 'test'),
                    expect_exit=0,
                    timeout=300,
                    approved_by='planner',
                )
                contracts.approve(ticket_id, [command], Approval(at=MOMENT, head=head))
                contracts.record(ticket_id, [passing_receipt(head, phase)])


def passing_receipt(head: str, phase: Phase) -> Receipt:
    return Receipt(
        key=COMMAND_KEY,
        argv=('make', 'test'),
        outcome='pass',
        exit=0,
        duration_ms=10,
        stdout_tail=redact('ok'),
        stderr_tail=redact(''),
        digest='d1',
        head=head,
        phase=phase,
        at=MOMENT,
    )
