from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import DuplicateRowError, MissingParentError
from mightymodels_core.schemas.investigations import (
    ADD_INVESTIGATION,
    APPEND_LEDGER_ENTRY,
    INVESTIGATION_BY_KEY,
    LATEST_ROUNDS,
    LEDGER_ENTRIES,
    LEDGER_ENTRY_COUNT,
    RECORDED_INVESTIGATION_KEYS,
    AddInvestigationParams,
    AppendLedgerEntryParams,
    InvestigationIdParams,
    InvestigationKeyParams,
    LatestRoundsParams,
    LedgerEntriesParams,
    RecordedKeysParams,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Database

pytestmark = pytest.mark.integration

RECORDED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def add_investigation(database: Database, repository_id: int, key: str) -> int:
    params = AddInvestigationParams(
        repository_id=repository_id, investigation_key=key, target='find it', kind='known'
    )
    with database.write() as unit:
        added = unit.one(ADD_INVESTIGATION, params)
    assert added is not None
    return added.id


def entry(investigation_id: int, seq: int, round_number: int = 1) -> AppendLedgerEntryParams:
    return AppendLedgerEntryParams(
        investigation_id=investigation_id,
        seq=seq,
        round=round_number,
        kind='known',
        text=f'entry {seq}',
        source='code-scout',
        cite=None if seq == 1 else 'file.py:1',
        supersedes=[] if seq == 1 else [seq - 1],
        at=RECORDED_AT,
        head=None,
    )


class TestInvestigations:
    def test_an_investigation_reads_back_by_key(
        self, database: Database, repository_id: int
    ) -> None:
        investigation_id = add_investigation(database, repository_id, 'probe')

        with database.read() as unit:
            found = unit.one(
                INVESTIGATION_BY_KEY,
                InvestigationKeyParams(repository_id=repository_id, investigation_key='probe'),
            )
            missing = unit.one(
                INVESTIGATION_BY_KEY,
                InvestigationKeyParams(repository_id=repository_id, investigation_key='absent'),
            )

        assert found is not None
        assert (found.id, found.target, found.kind) == (investigation_id, 'find it', 'known')
        assert isinstance(found.created_at, datetime)
        assert missing is None

    def test_a_repeated_key_in_one_repository_is_a_duplicate(
        self, database: Database, repository_id: int
    ) -> None:
        add_investigation(database, repository_id, 'probe')

        with pytest.raises(DuplicateRowError):
            add_investigation(database, repository_id, 'probe')

    def test_recorded_keys_name_only_the_investigations_that_exist(
        self, database: Database, repository_id: int
    ) -> None:
        add_investigation(database, repository_id, 'probe')
        add_investigation(database, repository_id, 'survey')

        with database.read() as unit:
            recorded = unit.all(
                RECORDED_INVESTIGATION_KEYS,
                RecordedKeysParams(
                    repository_id=repository_id, investigation_keys=['probe', 'absent', 'survey']
                ),
            )

        assert sorted(row.investigation_key for row in recorded) == ['probe', 'survey']


class TestLedgerEntries:
    @pytest.fixture
    def investigation_id(self, database: Database, repository_id: int) -> int:
        return add_investigation(database, repository_id, 'probe')

    def test_a_batch_of_entries_reads_back_in_seq_order_up_to_the_limit(
        self, database: Database, investigation_id: int
    ) -> None:
        with database.write() as unit:
            appended = unit.run_many(
                APPEND_LEDGER_ENTRY, [entry(investigation_id, seq) for seq in (3, 1, 2)]
            )

        with database.read() as unit:
            entries = unit.all(
                LEDGER_ENTRIES, LedgerEntriesParams(investigation_id=investigation_id, limit=2)
            )
            count = unit.one(
                LEDGER_ENTRY_COUNT, InvestigationIdParams(investigation_id=investigation_id)
            )

        assert appended == 3
        assert [row.seq for row in entries] == [1, 2]
        assert entries[1].supersedes == [1]
        assert entries[1].cite == 'file.py:1'
        assert entries[0].cite is None
        assert entries[0].kind == 'known'
        assert entries[0].source == 'code-scout'
        assert entries[0].at == RECORDED_AT
        assert count is not None
        assert count.count == 3

    def test_a_repeated_seq_is_a_duplicate(self, database: Database, investigation_id: int) -> None:
        with database.write() as unit:
            unit.run(APPEND_LEDGER_ENTRY, entry(investigation_id, 1))

        with pytest.raises(DuplicateRowError), database.write() as unit:
            unit.run(APPEND_LEDGER_ENTRY, entry(investigation_id, 1))

    def test_an_entry_without_an_investigation_names_a_missing_parent(
        self, database: Database, investigation_id: int
    ) -> None:
        with pytest.raises(MissingParentError), database.write() as unit:
            unit.run(APPEND_LEDGER_ENTRY, entry(investigation_id + 1, 1))

    def test_latest_rounds_list_each_investigation_newest_first(
        self, database: Database, repository_id: int
    ) -> None:
        first = add_investigation(database, repository_id, 'first')
        second = add_investigation(database, repository_id, 'second')
        add_investigation(database, repository_id, 'empty')
        with database.write() as unit:
            unit.run_many(
                APPEND_LEDGER_ENTRY,
                [entry(first, 1, 1), entry(first, 2, 3), entry(second, 1, 2)],
            )

        with database.read() as unit:
            rounds = unit.all(
                LATEST_ROUNDS, LatestRoundsParams(repository_id=repository_id, limit=10)
            )
            capped = unit.all(
                LATEST_ROUNDS, LatestRoundsParams(repository_id=repository_id, limit=1)
            )

        assert [(row.investigation_key, row.round) for row in rounds] == [
            ('second', 2),
            ('first', 3),
        ]
        assert [row.investigation_key for row in capped] == ['second']
