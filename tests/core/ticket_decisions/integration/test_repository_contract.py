"""The ticket decision repository contract against the sqlite store."""

import sqlite3
from typing import TYPE_CHECKING

from mightymodels_core.schemas.ticket_decisions import (
    ADD_TICKET_DECISION,
    AddTicketDecisionParams,
)
from mightymodels_core.ticket_decisions import IncomingDecision

from tests.core.ticket_decisions.integration.conftest import DATABASE_FILE, NOW, stage_decisions

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.database import Database, Unit

    from tests.core.ticket_decisions.ticket_decisions_builders import DecisionsFor

GITHUB_TOKEN = 'ghp_' + 'a' * 36
SCRUBBED = '[REDACTED:github-token]'


class TestSqliteTicketDecisionRepository:
    def test_add_then_list_returns_every_field(self, decisions_for: DecisionsFor) -> None:
        decisions = decisions_for('one')
        decisions.add(
            IncomingDecision(
                question='Which store?', answer='sqlite, wal', response='go', note='fast enough'
            )
        )

        (decision,) = decisions.decisions()

        assert decision.question == 'Which store?'
        assert decision.answer == 'sqlite, wal'
        assert decision.response == 'go'
        assert decision.note == 'fast enough'
        assert decision.decided_at == NOW

    def test_response_and_note_are_optional(self, decisions_for: DecisionsFor) -> None:
        decisions = decisions_for('one')
        decisions.add(IncomingDecision(question='Q?', answer='A'))

        (decision,) = decisions.decisions()

        assert (decision.response, decision.note) == (None, None)

    def test_decisions_list_in_the_order_they_were_added(self, decisions_for: DecisionsFor) -> None:
        decisions = decisions_for('one')
        decisions.add(IncomingDecision(question='first', answer='a'))
        decisions.add(IncomingDecision(question='second', answer='b'))

        assert [decision.question for decision in decisions.decisions()] == ['first', 'second']

    def test_decisions_are_kept_per_ticket(self, decisions_for: DecisionsFor) -> None:
        one = decisions_for('one')
        other = decisions_for('other')
        one.add(IncomingDecision(question='mine', answer='a'))

        assert other.decisions() == ()
        assert len(one.decisions()) == 1

    def test_secrets_in_every_text_field_are_stored_redacted(
        self, decisions_for: DecisionsFor
    ) -> None:
        decisions = decisions_for('one')
        decisions.add(
            IncomingDecision(
                question=f'use {GITHUB_TOKEN}?',
                answer=f'yes {GITHUB_TOKEN}',
                response=f'ok {GITHUB_TOKEN}',
                note=f'see {GITHUB_TOKEN}',
            )
        )

        (decision,) = decisions.decisions()

        assert decision.question == f'use {SCRUBBED}?'
        assert decision.answer == f'yes {SCRUBBED}'
        assert decision.response == f'ok {SCRUBBED}'
        assert decision.note == f'see {SCRUBBED}'

    def test_a_raw_row_holding_a_secret_is_redacted_on_read(self, unit: Unit) -> None:
        staged = stage_decisions(unit, 'one')
        unit.run(
            ADD_TICKET_DECISION,
            AddTicketDecisionParams(
                ticket_id=staged.ticket_id,
                question=f'use {GITHUB_TOKEN}?',
                answer=f'yes {GITHUB_TOKEN}',
                response=f'ok {GITHUB_TOKEN}',
                note=f'see {GITHUB_TOKEN}',
                decided_at=int(NOW.timestamp()),
            ),
        )

        (decision,) = staged.decisions()

        assert decision.question == f'use {SCRUBBED}?'
        assert decision.answer == f'yes {SCRUBBED}'
        assert decision.response == f'ok {SCRUBBED}'
        assert decision.note == f'see {SCRUBBED}'

    def test_stored_columns_hold_no_secret(self, database: Database, tmp_path: Path) -> None:
        with database.write() as unit:
            stage_decisions(unit, 'one').add(
                IncomingDecision(question=GITHUB_TOKEN, answer=GITHUB_TOKEN, note=GITHUB_TOKEN)
            )
        stored = sqlite3.connect(tmp_path.joinpath(DATABASE_FILE))
        row = stored.execute('SELECT question, answer, note FROM ticket_decisions').fetchone()
        stored.close()

        assert row == (SCRUBBED, SCRUBBED, SCRUBBED)

    def test_fresh_schema_has_both_new_tables(self, database: Database, tmp_path: Path) -> None:
        assert database
        stored = sqlite3.connect(tmp_path.joinpath(DATABASE_FILE))
        rows = stored.execute("SELECT name FROM sqlite_schema WHERE type = 'table'").fetchall()
        stored.close()

        assert {'session_pointers', 'ticket_decisions'} <= {name for (name,) in rows}
