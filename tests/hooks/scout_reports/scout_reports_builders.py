"""Payloads, a keeper over a real data directory and the rows it leaves."""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from typing import TYPE_CHECKING

import msgspec
from mightymodels_core.edge import DATABASE_NAME, PLUGIN_DATA_VARIABLE
from mightymodels_core.primitives import SystemClock
from mightymodels_hooks.payloads import PostToolUsePayload, SubagentStopPayload
from mightymodels_hooks.scout_reports import (
    ScoutReportKeeper,
    SubagentHandbackHandler,
    SubagentRecordHandler,
    create_scouts,
)

if TYPE_CHECKING:
    import io
    from pathlib import Path

CODE_SCOUT = 'mightymodels:triage:code-scout'
WEB_SCOUT = 'mightymodels:triage:web-scout'
AGENT_ID = 'a1b2'
REPORT = 'The queue drains in src/queue.py:12.'
CLOSING_TEXT = 'Done.'


@dataclass(slots=True, kw_only=True, frozen=True)
class StoredRow:
    scout: str
    target: str
    report: str


def stop_payload(agent_type: str, **given: object) -> dict[str, object]:
    stop: dict[str, object] = {
        'hook_event_name': 'SubagentStop',
        'agent_type': agent_type,
        'agent_id': AGENT_ID,
        'last_assistant_message': REPORT,
    }
    return stop | given


def handback_payload(
    agent_type: str, message: object = REPORT, **given: object
) -> dict[str, object]:
    handback: dict[str, object] = {
        'hook_event_name': 'PostToolUse',
        'tool_name': 'SubagentHandback',
        'agent_type': agent_type,
        'agent_id': AGENT_ID,
        'tool_input': {'message': message},
    }
    return handback | given


def stop_event(agent_type: str, **given: object) -> SubagentStopPayload:
    return msgspec.convert(stop_payload(agent_type, **given), type=SubagentStopPayload)


def handback_event(
    agent_type: str, message: object = REPORT, **given: object
) -> PostToolUsePayload:
    payload = handback_payload(agent_type, message, **given)
    return msgspec.convert(payload, type=PostToolUsePayload)


@dataclass(slots=True, kw_only=True, frozen=True)
class ScoutHarness:
    checkout: Path
    data_directory: Path
    stderr: io.StringIO

    @property
    def keeper(self) -> ScoutReportKeeper:
        environ = {PLUGIN_DATA_VARIABLE: str(self.data_directory)}
        return ScoutReportKeeper(
            environ=environ, stderr=self.stderr, clock=SystemClock(), scouts=create_scouts()
        )

    async def stop(self, payload: dict[str, object]) -> str | None:
        handler = SubagentRecordHandler(keeper=self.keeper)
        located = {**payload, 'cwd': str(self.checkout)}
        return await handler.handle(msgspec.convert(located, type=SubagentStopPayload))

    async def hand_back(self, payload: dict[str, object]) -> str | None:
        handler = SubagentHandbackHandler(keeper=self.keeper)
        located = {**payload, 'cwd': str(self.checkout)}
        return await handler.handle(msgspec.convert(located, type=PostToolUsePayload))

    def rows(self) -> list[StoredRow]:
        database = self.data_directory.joinpath(DATABASE_NAME)
        if not database.is_file():
            return []

        with closing(sqlite3.connect(database)) as connection:
            found = connection.execute('SELECT scout, target, report FROM scout_reports')
            return [StoredRow(scout=s, target=t, report=r) for s, t, r in found]
