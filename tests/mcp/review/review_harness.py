"""The review tools' shared e2e fixtures: a client harness, a started run and persona reports.

`DisposeAnswerer` answers a dispose page's boxes and a reasons form's fields by position, and
plays one action per round, so a test can decline either round of one call.
"""

from dataclasses import dataclass, field
from textwrap import dedent
from typing import TYPE_CHECKING, Any

import anyio
from mcp import Client
from mcp.types import ElicitRequestFormParams, ElicitResult
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.server.app import create_server
from mightymodels_mcp.server.dependencies import ServerDependencies

from tests.mcp.server.server_harness import view_of
from tests.mcp.task.task_harness import RecordingOpener
from tests.mcp.ticket.ticket_harness import ANSWERED, RecordingAnswerer, TicketHarness

if TYPE_CHECKING:
    from mcp.client.session import ClientRequestContext
    from mcp.types import CallToolResult, ElicitRequestParams
    from mightymodels_core.vocabulary.reviews import Persona

    from tests.mcp.server.server_harness import ServerHarness
    from tests.mcp.ticket.ticket_harness import FormAction

ALL_ANSWERED = {'scope': 'diff', 'depth': 'standard', 'emphasis': 'balanced'}
REPORT_NAMES: dict[Persona, str] = {
    'merge-vader': 'MERGE-VADER-REPORT.md',
    'uncle-bob': 'UNCLE-BOB-REPORT.md',
}
SUBJECTS = (
    'cache key',
    'parser offset',
    'router table',
    'ledger total',
    'socket timeout',
    'schema version',
    'quota counter',
    'mailer header',
    'token expiry',
    'upload size',
    'backup path',
    'locale fallback',
)


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


def finding_block(number: int, subject: str) -> str:
    return (
        f'#### MV-{number} | security | Unchecked {subject}\n'
        f'- Evidence: `src/m{number}.py:{number}` reads the {subject} unchecked\n'
        f'- Fix: validate the {subject} first\n'
        '- Verify: run the tests\n\n'
    )


def merge_vader_findings_report(count: int) -> str:
    blocks = ''.join(map(finding_block, range(1, count + 1), SUBJECTS[:count], strict=True))
    return f'# Review\n\n## Findings\n\n### High\n\n{blocks}## Verdict\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class DisposeAnswerer:
    checked: frozenset[int] = frozenset()
    decision: str = 'defer'
    reason: str = 'after the release'
    actions: tuple[FormAction, ...] = ()
    asked: list[tuple[str, ...]] = field(default_factory=list)

    def answer_field(self, name: str) -> bool | str:
        kind, _, position = name.rpartition('_')
        answers = {
            'finding': int(position) in self.checked,
            'decision': self.decision,
            'reason': self.reason,
        }
        return answers[kind]

    def next_action(self) -> FormAction:
        played = len(self.asked)
        return self.actions[played] if played < len(self.actions) else 'accept'

    async def answer(
        self, context: ClientRequestContext, params: ElicitRequestParams
    ) -> ElicitResult:
        assert context
        assert isinstance(params, ElicitRequestFormParams)
        properties = tuple(params.requested_schema['properties'])
        action = self.next_action()
        self.asked.append(properties)
        if action != 'accept':
            return ElicitResult(action=action)

        return ElicitResult(
            action='accept', content={name: self.answer_field(name) for name in properties}
        )


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
        answerer: RecordingAnswerer | DisposeAnswerer | None = None,
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

    async def start_with_findings(self, count: int) -> StartedRun:
        started = await self.start()
        await self.write_report(started, 'merge-vader', merge_vader_findings_report(count))
        arguments = {'run_id': started.run_id, 'persona': 'merge-vader'}
        view_of(await self.call('review_add', arguments))
        return started


async def create_review_harness(server: ServerHarness) -> ReviewHarness:
    tickets = TicketHarness(server=server)
    view_of(await tickets.call('ticket_write', dict(ANSWERED)))
    view_of(await tickets.call('ticket_validate', {'slug': ANSWERED['slug']}))
    return ReviewHarness(server=server, opener=RecordingOpener(inner=server.dependencies.state))
