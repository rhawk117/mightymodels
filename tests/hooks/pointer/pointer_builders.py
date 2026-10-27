"""Payloads, a handler over a real data directory and the pointer it leaves."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import msgspec
from mightymodels_core.edge import PLUGIN_DATA_VARIABLE, open_state
from mightymodels_core.primitives import SystemClock
from mightymodels_core.session_pointers import SqliteSessionPointerRepository
from mightymodels_core.units_of_work import read_entry
from mightymodels_hooks.payloads import PostToolUsePayload
from mightymodels_hooks.session_pointer import SessionPointerHandler

if TYPE_CHECKING:
    import io
    from pathlib import Path

    from mightymodels_core.session_pointers import SessionPointer

SESSION_ID = 'session-1'
SERVER_PREFIX = 'mcp__plugin_mightymodels_workflow_state__'


def pointer_payload(tool: str, tool_input: object, **given: object) -> PostToolUsePayload:
    payload: dict[str, object] = {
        'hook_event_name': 'PostToolUse',
        'session_id': SESSION_ID,
        'tool_name': f'{SERVER_PREFIX}{tool}',
        'tool_input': tool_input,
    }
    return msgspec.convert(payload | given, type=PostToolUsePayload)


@dataclass(slots=True, kw_only=True, frozen=True)
class PointerHarness:
    checkout: Path
    data_directory: Path
    stderr: io.StringIO

    def make_ticket_directory(self) -> None:
        self.checkout.joinpath('.mightymodels', 'port-it').mkdir(parents=True)

    def handler(self) -> SessionPointerHandler:
        environ = {PLUGIN_DATA_VARIABLE: str(self.data_directory)}
        return SessionPointerHandler(environ=environ, stderr=self.stderr, clock=SystemClock())

    async def point(self, payload: PostToolUsePayload) -> str | None:
        located = msgspec.structs.replace(payload, cwd=str(self.checkout))
        return await self.handler().handle(located)

    async def pointer(self, session_id: str = SESSION_ID) -> SessionPointer | None:
        if not self.data_directory.is_dir():
            return None

        async with open_state(self.data_directory, self.checkout) as state:
            with read_entry(state.database, state.checkout.repository_key()) as entry:
                pointers = SqliteSessionPointerRepository(
                    unit=entry.unit, repository_id=entry.repository_id, clock=SystemClock()
                )
                return pointers.lookup(session_id)
