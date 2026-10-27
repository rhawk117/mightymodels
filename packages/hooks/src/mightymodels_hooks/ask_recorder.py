"""The `ask-recorder` subcommand, which the PostToolUse hook runs on AskUserQuestion.

Each answered question of a dialog becomes a Decision in the ledger the session pointer names:
a `decision` entry from the user when it names an investigation, a ticket decision row when it
names an open ticket. The decision holds the question, the answer verbatim (a multi-select answer
is one string), the dialog's `response` text and that question's annotation note, all redacted.

A payload with no `session_id`, with `answers` missing or not an object, or from a dialog that
timed out (`afkTimeoutMs`) writes nothing. So does a session with no pointer, a closed ticket or a
repository the database has not recorded. The hook never blocks and prints nothing on standard
output; an unreadable database is said on standard error, with exit 0.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, TextIO

from mightymodels_core.edge import open_state
from mightymodels_core.primitives import Slug
from mightymodels_core.session_pointers import SqliteSessionPointerRepository
from mightymodels_core.tickets import SqliteTicketRepository
from mightymodels_core.units_of_work import (
    InvestigationWork,
    UnknownRepositoryError,
    read_entry,
    write_entry,
)

from mightymodels_hooks.hook_context import (
    STATE_UNREADABLE,
    LookupOnlyBackends,
    create_hook_context,
)
from mightymodels_hooks.recorder_state import Answered, DecisionRecorder
from mightymodels_hooks.session_pointer import session_id_of

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mightymodels_core.edge import OpenState
    from mightymodels_core.primitives import Clock
    from mightymodels_core.session_pointers import SessionPointer

    from mightymodels_hooks.cli import HookPayload
    from mightymodels_hooks.hook_context import HookContext

TOOL_RESPONSE_KEY = 'tool_response'
ANSWERS_KEY = 'answers'
ANNOTATIONS_KEY = 'annotations'
RESPONSE_KEY = 'response'
NOTES_KEY = 'notes'
AFK_KEY = 'afkTimeoutMs'


def text_of(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def note_of(annotations: object, question: str) -> str | None:
    if not isinstance(annotations, dict):
        return None

    annotation = annotations.get(question)
    return text_of(annotation.get(NOTES_KEY)) if isinstance(annotation, dict) else None


def answers_of(payload: HookPayload) -> list[Answered]:
    result = payload.get(TOOL_RESPONSE_KEY)
    if not isinstance(result, dict) or AFK_KEY in result:
        return []

    answers = result.get(ANSWERS_KEY)
    if not isinstance(answers, dict):
        return []

    response = text_of(result.get(RESPONSE_KEY))
    annotations = result.get(ANNOTATIONS_KEY)
    return [
        Answered(
            question=question,
            answer=answer,
            response=response,
            note=note_of(annotations, question),
        )
        for question, answer in answers.items()
        if isinstance(question, str) and isinstance(answer, str) and answer
    ]


@dataclass(slots=True, kw_only=True, frozen=True)
class AskRecorderHandler:
    environ: Mapping[str, str]
    stderr: TextIO
    clock: Clock

    async def record(
        self, context: HookContext, session_id: str, answers: Sequence[Answered]
    ) -> None:
        async with open_state(
            context.data_directory(), context.start(), backends=LookupOnlyBackends()
        ) as state:
            pointer = self.pointer_of(state, session_id)
            if pointer is None:
                return

            recorder = DecisionRecorder(stderr=self.stderr, clock=self.clock, answers=answers)
            if pointer.kind == 'ticket':
                self.record_ticket(state, Slug(pointer.key), recorder)
                return

            await self.record_investigation(state, Slug(pointer.key), recorder)

    def pointer_of(self, state: OpenState, session_id: str) -> SessionPointer | None:
        with read_entry(state.database, state.checkout.repository_key()) as entry:
            pointers = SqliteSessionPointerRepository(
                unit=entry.unit, repository_id=entry.repository_id, clock=self.clock
            )
            return pointers.lookup(session_id)

    def record_ticket(self, state: OpenState, slug: Slug, recorder: DecisionRecorder) -> None:
        with write_entry(state.database, state.checkout.repository_key()) as entry:
            tickets = SqliteTicketRepository(unit=entry.unit, repository_id=entry.repository_id)
            ticket = tickets.ticket(slug)
            if ticket is None or ticket.status == 'closed':
                return

            recorder.record_ticket(entry.unit, ticket.id)

    async def record_investigation(
        self, state: OpenState, key: Slug, recorder: DecisionRecorder
    ) -> None:
        head = await state.git.resolve_head()
        work = InvestigationWork(
            database=state.database,
            repository_key=state.checkout.repository_key(),
            clock=self.clock,
        )
        with work.write() as unit:
            recorder.record_ledger(unit.investigations, key, head)

    async def handle(self, payload: HookPayload) -> str | None:
        session_id = session_id_of(payload)
        answers = answers_of(payload)
        if session_id is None or not answers:
            return None

        context = create_hook_context(self.environ, payload)
        try:
            await self.record(context, session_id, answers)
        except UnknownRepositoryError:
            return None
        except STATE_UNREADABLE as error:
            self.stderr.write(f'mightymodels-hooks: ask-recorder: {error}\n')

        return None
