"""The `subagent-record` and `subagent-handback` subcommands, which keep a scout's report.

When `mightymodels:triage:code-scout` or `mightymodels:triage:web-scout` stops, its final message is
its report, unless it handed the report back with the SubagentHandback tool, in which case the
final message is closing text. `subagent-handback` (PostToolUse on SubagentHandback) keeps
`tool_input.message` and `subagent-record` (SubagentStop) keeps `last_assistant_message`. Each
writes the report straight to the `scout_reports` table through the similarity service, under the
target `<scout> <agent_id>` (the bare scout when the input carries no `agent_id`). A scout and
target already holding a report get no second row, so the closing text of a stop that follows a
handback is dropped.

Any other agent type writes nothing. So does a missing or blank report, a report that redaction
lengthens past its limit, a stop with no data directory or git work tree and an unreadable
database; each says why on standard error. Neither command blocks: both exit 0 and print nothing
on standard output.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, TextIO

from mightymodels_core.edge import open_state
from mightymodels_core.primitives import StateError
from mightymodels_core.similarity import IncomingReport, SimilarityOptions
from mightymodels_core.units_of_work import JournalWork

from mightymodels_hooks.hook_context import STATE_UNREADABLE, create_hook_context
from mightymodels_hooks.workers import plugin_caller, worker_named

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mightymodels_core.primitives import AgentName, Clock
    from mightymodels_core.vocabulary.similarity import Scout

    from mightymodels_hooks.cli import HookPayload
    from mightymodels_hooks.hook_context import HookContext

type Scouts = dict[AgentName, Scout]
LAST_MESSAGE_KEY = 'last_assistant_message'
TOOL_INPUT_KEY = 'tool_input'
MESSAGE_KEY = 'message'
AGENT_ID_KEY = 'agent_id'


class NoReportError(StateError):
    def __init__(self) -> None:
        super().__init__('the scout left no report text, so there is no report to keep')


def create_scouts() -> Scouts:
    return {'code-scout': 'code-scout', 'web-scout': 'web-scout'}


def scout_named(payload: HookPayload, scouts: Scouts) -> Scout | None:
    caller = plugin_caller(payload)
    worker = None if caller is None else worker_named(caller)
    return None if worker is None else scouts.get(worker)


def target_of(scout: Scout, payload: HookPayload) -> str:
    agent_id = payload.get(AGENT_ID_KEY)
    if not isinstance(agent_id, str) or not agent_id:
        return scout

    return f'{scout} {agent_id}'[: SimilarityOptions().name_limit]


def scout_report_of(
    payload: HookPayload, report: object, scouts: Scouts | None = None
) -> IncomingReport | NoReportError | None:
    scout = scout_named(payload, scouts or create_scouts())
    if scout is None:
        return None

    if not isinstance(report, str) or not report.strip():
        return NoReportError()

    return IncomingReport(scout=scout, target=target_of(scout, payload), report=report)


def handback_message_of(payload: HookPayload) -> object:
    tool_input = payload.get(TOOL_INPUT_KEY)
    return tool_input.get(MESSAGE_KEY) if isinstance(tool_input, dict) else None


@dataclass(slots=True, kw_only=True, frozen=True)
class ScoutReportKeeper:
    environ: Mapping[str, str]
    stderr: TextIO
    clock: Clock
    scouts: Scouts

    def note(self, command: str, error: Exception) -> None:
        self.stderr.write(f'mightymodels-hooks: {command}: {error}\n')

    async def store(self, context: HookContext, incoming: IncomingReport) -> None:
        async with open_state(context.data_directory(), context.start()) as state:
            work = JournalWork(
                database=state.database,
                repository_key=state.checkout.repository_key(),
                clock=self.clock,
            )
            with work.write() as unit:
                if not unit.similarity.has_report_of(incoming):
                    unit.similarity.store_report(incoming)

    async def keep(self, command: str, payload: HookPayload, report: object) -> None:
        incoming = scout_report_of(payload, report, self.scouts)
        if incoming is None:
            return

        if isinstance(incoming, NoReportError):
            self.note(command, incoming)
            return

        try:
            await self.store(create_hook_context(self.environ, payload), incoming)
        except STATE_UNREADABLE as error:
            self.note(command, error)


@dataclass(slots=True, kw_only=True, frozen=True)
class SubagentRecordHandler:
    keeper: ScoutReportKeeper

    async def handle(self, payload: HookPayload) -> str | None:
        await self.keeper.keep('subagent-record', payload, payload.get(LAST_MESSAGE_KEY))
        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class SubagentHandbackHandler:
    keeper: ScoutReportKeeper

    async def handle(self, payload: HookPayload) -> str | None:
        await self.keeper.keep('subagent-handback', payload, handback_message_of(payload))
        return None
