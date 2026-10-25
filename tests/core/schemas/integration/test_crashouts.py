from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import MissingParentError
from mightymodels_core.schemas.crashouts import (
    CRASHOUT_COUNT,
    JOURNAL_CRASHOUT,
    LATEST_CRASHOUTS,
    CrashoutCountParams,
    JournalCrashoutParams,
    LatestCrashoutsParams,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Database

JOURNALED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def crashout(
    repository_id: int, root_cause: str, *, barked_back: bool = False
) -> JournalCrashoutParams:
    return JournalCrashoutParams(
        repository_id=repository_id,
        at=JOURNALED_AT,
        ticket_key=None,
        branch='main',
        severity='heated',
        verdict='split',
        rant='a rant',
        failures=['one', 'two'],
        root_cause=root_cause,
        corrective_action='fix it',
        barked_back=barked_back,
    )


def journal(database: Database, params: JournalCrashoutParams) -> int:
    with database.write() as unit:
        journaled = unit.one(JOURNAL_CRASHOUT, params)
    assert journaled is not None
    return journaled.id


class TestCrashouts:
    def test_the_latest_crashouts_are_newest_first_and_limited(
        self, database: Database, repository_id: int
    ) -> None:
        for cause in ('first', 'second', 'third'):
            journal(database, crashout(repository_id, cause))

        with database.read() as unit:
            latest = unit.all(
                LATEST_CRASHOUTS, LatestCrashoutsParams(repository_id=repository_id, limit=2)
            )

        assert [row.root_cause for row in latest] == ['third', 'second']

    def test_a_crashout_reads_back_every_column(
        self, database: Database, repository_id: int
    ) -> None:
        journaled = journal(database, crashout(repository_id, 'cause', barked_back=True))

        with database.read() as unit:
            latest = unit.all(
                LATEST_CRASHOUTS, LatestCrashoutsParams(repository_id=repository_id, limit=1)
            )

        assert len(latest) == 1
        row = latest[0]
        assert row.id == journaled
        assert row.at == JOURNALED_AT
        assert row.ticket_key is None
        assert row.branch == 'main'
        assert row.severity == 'heated'
        assert row.verdict == 'split'
        assert row.root_cause == 'cause'
        assert row.rant == 'a rant'
        assert row.failures == ['one', 'two']
        assert row.corrective_action == 'fix it'
        assert row.barked_back is True

    def test_the_count_covers_the_repository_only(
        self, database: Database, repository_id: int
    ) -> None:
        journal(database, crashout(repository_id, 'first'))
        journal(database, crashout(repository_id, 'second'))

        with database.read() as unit:
            count = unit.one(CRASHOUT_COUNT, CrashoutCountParams(repository_id=repository_id))
            other = unit.one(CRASHOUT_COUNT, CrashoutCountParams(repository_id=repository_id + 1))

        assert count is not None
        assert count.count == 2
        assert other is not None
        assert other.count == 0

    def test_a_crashout_needs_a_repository(self, database: Database) -> None:
        with pytest.raises(MissingParentError), database.write() as unit:
            unit.one(JOURNAL_CRASHOUT, crashout(999, 'cause'))
