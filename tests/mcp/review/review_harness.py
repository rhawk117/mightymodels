"""The review tools' shared e2e fixtures: a client harness, a started run and a persona report."""

from dataclasses import dataclass
from textwrap import dedent
from typing import TYPE_CHECKING, Any

import anyio
from mcp import Client
from mightymodels_mcp.server.app import create_server
from mightymodels_mcp.server.dependencies import ServerDependencies
from mightymodels_mcp.server.entrypoint import create_catalog

from tests.mcp.server.server_harness import view_of
from tests.mcp.task.task_harness import RecordingOpener
from tests.mcp.ticket.ticket_harness import ANSWERED, RecordingAnswerer, TicketHarness

if TYPE_CHECKING:
    from mcp.types import CallToolResult
    from mightymodels_core.vocabulary.reviews import Persona

    from tests.mcp.server.server_harness import ServerHarness

ALL_ANSWERED = {'scope': 'diff', 'depth': 'standard', 'emphasis': 'balanced'}
REPORT_NAMES: dict[Persona, str] = {
    'merge-vader': 'MERGE-VADER-REPORT.md',
    'uncle-bob': 'UNCLE-BOB-REPORT.md',
}


@dataclass(slots=True, kw_only=True, frozen=True)
class StartedRun:
    run_id: str
    directory: str


def merge_vader_report(title: str = 'Unchecked input') -> str:
    return dedent(f"""\
        # Review

        ## Findings

        ### High

        #### MV-1 | security | {title}
        - Evidence: `src/a.py:10` unchecked
        - Fix: check it before use
        - Verify: run the tests

        ## Verdict
        """)


def uncle_bob_report(title: str = 'Mixed duties') -> str:
    return dedent(f"""\
        # Review

        ## Findings

        ### Medium

        #### UB-1 | [SRP] {title} — `src/b.py:5-9`
        - Evidence (metric): fan-out 14
        - Fix: split it
        - Verify: run the tests

        ## Verdict
        """)


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewHarness:
    server: ServerHarness
    opener: RecordingOpener

    @property
    def git_calls(self) -> list[str]:
        return self.opener.git_calls

    async def call(
        self,
        name: str,
        arguments: dict[str, Any],
        answerer: RecordingAnswerer | None = None,
    ) -> CallToolResult:
        self.git_calls.clear()
        answerer = answerer or RecordingAnswerer(answers={})
        server = create_server(ServerDependencies(state=self.opener), create_catalog())
        async with Client(server, elicitation_callback=answerer.answer) as client:
            return await client.call_tool(name, arguments)

    async def start(self, **arguments: Any) -> StartedRun:
        view = view_of(await self.call('review_start', {**ALL_ANSWERED, **arguments}))
        first_line = view['text'].splitlines()[0]
        run_id, _, directory = first_line.removeprefix('run ').partition(' at ')
        return StartedRun(run_id=run_id, directory=directory)

    async def write_report(self, started: StartedRun, persona: Persona, text: str) -> None:
        directory = anyio.Path(self.server.repository, started.directory)
        await directory.joinpath(REPORT_NAMES[persona]).write_text(text, encoding='utf-8')


async def create_review_harness(server: ServerHarness) -> ReviewHarness:
    tickets = TicketHarness(server=server)
    view_of(await tickets.call('ticket_write', dict(ANSWERED)))
    view_of(await tickets.call('ticket_validate', {'slug': ANSWERED['slug']}))
    return ReviewHarness(server=server, opener=RecordingOpener(inner=server.dependencies.state))
