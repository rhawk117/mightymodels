"""The `session-pointer` subcommand, which the PostToolUse hook runs on the workflow_state tools.

A call to a tool that names a ticket (`slug`, or `ticket` on `crashout_add`) or an investigation
(`investigation_id`) points the calling session at it, through core's session pointer repository,
so a later hook knows which ledger the session is working in. The latest call wins.
`PointerFields.tool_names` lists the tools the hook acts on, which is also the matcher the wiring
uses.

A payload with no `session_id`, a tool outside that list or a call whose field is missing, null or
blank writes nothing. So does a repository the database has not recorded. The hook never blocks
and prints nothing on standard output; an unreadable database is said on standard error, with
exit 0.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self, TextIO

from mightymodels_core.edge import open_state
from mightymodels_core.session_pointers import SqliteSessionPointerRepository
from mightymodels_core.units_of_work import UnknownRepositoryError, write_entry

from mightymodels_hooks.hook_context import STATE_UNREADABLE, create_hook_context_at

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mightymodels_core.primitives import Clock
    from mightymodels_core.vocabulary.session_pointers import PointerKind

    from mightymodels_hooks.hook_context import HookContext
    from mightymodels_hooks.payloads import PostToolUsePayload

TOOL_SEPARATOR = '__'


@dataclass(slots=True, kw_only=True, frozen=True)
class PointerTarget:
    kind: PointerKind
    key: str


def tool_of(tool_name: str | None) -> str | None:
    return None if tool_name is None else tool_name.rsplit(TOOL_SEPARATOR, 1)[-1]


@dataclass(slots=True, kw_only=True, frozen=True)
class PointerFields:
    kinds: dict[str, PointerKind] = field(default_factory=dict)
    tools: dict[str, str] = field(default_factory=dict)

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(self.tools)

    def mount(self, *, kinds: dict[str, PointerKind], tools: dict[str, str]) -> Self:
        self.kinds.update(kinds)
        self.tools.update(tools)
        return self

    def target_of(self, payload: PostToolUsePayload) -> PointerTarget | None:
        tool = tool_of(payload.tool_name)
        name = None if tool is None else self.tools.get(tool)
        tool_input = payload.tool_input
        if name is None or tool_input is None:
            return None

        key = tool_input.get(name)
        if not isinstance(key, str) or not key.strip():
            return None

        return PointerTarget(kind=self.kinds[name], key=key)


def create_pointer_fields() -> PointerFields:
    return PointerFields().mount(
        kinds={'slug': 'ticket', 'ticket': 'ticket', 'investigation_id': 'investigation'},
        tools={
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
        },
    )


def pointer_target_of(payload: PostToolUsePayload) -> PointerTarget | None:
    return create_pointer_fields().target_of(payload)


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionPointerHandler:
    environ: Mapping[str, str]
    stderr: TextIO
    clock: Clock
    fields: PointerFields = field(default_factory=create_pointer_fields)

    async def point(self, context: HookContext, session_id: str, target: PointerTarget) -> None:
        async with open_state(context.data_directory(), context.start()) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                pointers = SqliteSessionPointerRepository(
                    unit=entry.unit, repository_id=entry.repository_id, clock=self.clock
                )
                pointers.record(session_id, target.kind, target.key)

    async def handle(self, payload: PostToolUsePayload) -> str | None:
        session_id = payload.session_id or None
        target = self.fields.target_of(payload)
        if session_id is None or target is None:
            return None

        context = create_hook_context_at(self.environ, payload.cwd)
        try:
            await self.point(context, session_id, target)
        except UnknownRepositoryError:
            return None
        except STATE_UNREADABLE as error:
            self.stderr.write(f'mightymodels-hooks: session-pointer: {error}\n')

        return None
