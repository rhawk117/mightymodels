"""The `session-pointer` subcommand, which the PostToolUse hook runs on the workflow_state tools.

A call to a tool that names a ticket (`slug`, or `ticket` on `crashout_add`) or an investigation
(`investigation_id`) points the calling session at it, through core's session pointer repository,
so a later hook knows which ledger the session is working in. The latest call wins.
`SLUG_BEARING_TOOLS` lists the tools the hook acts on, which is also the matcher the wiring uses.

A payload with no `session_id`, a tool outside that list or a call whose field is missing, null or
blank writes nothing. So does a repository with no ticket directory or no state. The hook never
blocks and prints nothing on standard output; an unreadable database is said on standard error,
with exit 0.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, TextIO

from mightymodels_core.edge import open_state
from mightymodels_core.session_pointers import SqliteSessionPointerRepository
from mightymodels_core.units_of_work import UnknownRepositoryError, write_entry

from mightymodels_hooks.branch_state import STATE_UNREADABLE
from mightymodels_hooks.hook_context import create_hook_context

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mightymodels_core.primitives import Clock
    from mightymodels_core.schemas.session_pointers import PointerKind

    from mightymodels_hooks.cli import HookPayload
    from mightymodels_hooks.hook_context import HookContext

TOOL_NAME_KEY = 'tool_name'
TOOL_INPUT_KEY = 'tool_input'
SESSION_ID_KEY = 'session_id'
TOOL_SEPARATOR = '__'

FIELD_KINDS: Mapping[str, PointerKind] = MappingProxyType({
    'slug': 'ticket',
    'ticket': 'ticket',
    'investigation_id': 'investigation',
})
TOOL_FIELDS: Mapping[str, str] = MappingProxyType({
    'ticket_write': 'slug',
    'ticket_validate': 'slug',
    'ticket_show': 'slug',
    'ticket_update_context': 'slug',
    'close_check': 'slug',
    'close_ticket': 'slug',
    'task_start': 'slug',
    'task_verify': 'slug',
    'task_mark': 'slug',
    'task_show': 'slug',
    'task_ready': 'slug',
    'failed_fix_record': 'slug',
    'contract_approve': 'slug',
    'contract_status': 'slug',
    'review_start': 'slug',
    'snapshot_take': 'slug',
    'crashout_add': 'ticket',
    'investigation_add': 'investigation_id',
    'investigation_render': 'investigation_id',
    'investigation_knowns': 'investigation_id',
})
SLUG_BEARING_TOOLS: tuple[str, ...] = tuple(TOOL_FIELDS)


@dataclass(slots=True, kw_only=True, frozen=True)
class PointerTarget:
    kind: PointerKind
    key: str


def tool_of(payload: HookPayload) -> str | None:
    name = payload.get(TOOL_NAME_KEY)
    if not isinstance(name, str):
        return None

    return name.rsplit(TOOL_SEPARATOR, 1)[-1]


def session_id_of(payload: HookPayload) -> str | None:
    session_id = payload.get(SESSION_ID_KEY)
    if not isinstance(session_id, str) or not session_id:
        return None

    return session_id


def pointer_target_of(payload: HookPayload) -> PointerTarget | None:
    tool = tool_of(payload)
    field = None if tool is None else TOOL_FIELDS.get(tool)
    tool_input = payload.get(TOOL_INPUT_KEY)
    if field is None or not isinstance(tool_input, dict):
        return None

    key = tool_input.get(field)
    if not isinstance(key, str) or not key.strip():
        return None

    return PointerTarget(kind=FIELD_KINDS[field], key=key)


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionPointerHandler:
    environ: Mapping[str, str]
    stderr: TextIO
    clock: Clock

    async def point(self, context: HookContext, session_id: str, target: PointerTarget) -> None:
        async with open_state(context.data_directory(), context.start()) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                pointers = SqliteSessionPointerRepository(
                    unit=entry.unit, repository_id=entry.repository_id, clock=self.clock
                )
                pointers.record(session_id, target.kind, target.key)

    async def handle(self, payload: HookPayload) -> str | None:
        session_id = session_id_of(payload)
        target = pointer_target_of(payload)
        if session_id is None or target is None:
            return None

        context = create_hook_context(self.environ, payload)
        if not context.has_ticket_directory():
            return None

        try:
            await self.point(context, session_id, target)
        except UnknownRepositoryError:
            return None
        except STATE_UNREADABLE as error:
            self.stderr.write(f'mightymodels-hooks: session-pointer: {error}\n')

        return None
