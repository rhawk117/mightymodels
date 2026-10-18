from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import MissingParentError
from mightymodels_core.schemas.similarity import (
    SIMILARITY_CANDIDATES,
    SIMILARITY_OF_REFERENCE,
    UPSERT_SIMILARITY,
    SimilarityCandidatesParams,
    SimilarityKind,
    SimilarityReferenceParams,
    UpsertSimilarityParams,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Database

pytestmark = pytest.mark.integration


def similar(
    repository_id: int, kind: SimilarityKind, reference: str, text: str
) -> UpsertSimilarityParams:
    return UpsertSimilarityParams(
        repository_id=repository_id, kind=kind, reference=reference, text=text
    )


def store(database: Database, *rows: UpsertSimilarityParams) -> None:
    with database.write() as unit:
        unit.run_many(UPSERT_SIMILARITY, rows)


def search(
    database: Database,
    repository_id: int,
    query: str,
    *,
    kind: SimilarityKind | None = None,
    excluding: tuple[SimilarityKind, str] | None = None,
) -> list[tuple[SimilarityKind, str]]:
    params = SimilarityCandidatesParams(
        repository_id=repository_id,
        query=query,
        kind=kind,
        excluded_kind=None if excluding is None else excluding[0],
        excluded_reference=None if excluding is None else excluding[1],
    )
    with database.read() as unit:
        found = unit.all(SIMILARITY_CANDIDATES, params)
    return [(row.kind, row.reference) for row in found]


class TestSimilarityRows:
    def test_a_stored_row_reads_back_by_its_reference(
        self, database: Database, repository_id: int
    ) -> None:
        store(database, similar(repository_id, SimilarityKind.CRASHOUT, '7', 'the cause'))

        with database.read() as unit:
            row = unit.one(
                SIMILARITY_OF_REFERENCE,
                SimilarityReferenceParams(
                    repository_id=repository_id, kind=SimilarityKind.CRASHOUT, reference='7'
                ),
            )

        assert row is not None
        assert row.kind is SimilarityKind.CRASHOUT
        assert row.reference == '7'
        assert row.text == 'the cause'

    def test_a_missing_reference_reads_as_none(
        self, database: Database, repository_id: int
    ) -> None:
        with database.read() as unit:
            row = unit.one(
                SIMILARITY_OF_REFERENCE,
                SimilarityReferenceParams(
                    repository_id=repository_id, kind=SimilarityKind.CRASHOUT, reference='7'
                ),
            )

        assert row is None

    def test_storing_a_reference_again_replaces_its_text_and_its_index_entry(
        self, database: Database, repository_id: int
    ) -> None:
        store(database, similar(repository_id, SimilarityKind.CRASHOUT, '7', 'original wording'))
        store(database, similar(repository_id, SimilarityKind.CRASHOUT, '7', 'revised wording'))

        with database.read() as unit:
            row = unit.one(
                SIMILARITY_OF_REFERENCE,
                SimilarityReferenceParams(
                    repository_id=repository_id, kind=SimilarityKind.CRASHOUT, reference='7'
                ),
            )

        assert row is not None
        assert row.text == 'revised wording'
        assert search(database, repository_id, 'original') == []
        assert search(database, repository_id, 'revised') == [(SimilarityKind.CRASHOUT, '7')]

    def test_a_row_needs_a_repository(self, database: Database) -> None:
        with pytest.raises(MissingParentError):
            store(database, similar(999, SimilarityKind.CRASHOUT, '7', 'text'))


class TestSimilaritySearch:
    def test_a_word_in_the_text_matches(self, database: Database, repository_id: int) -> None:
        store(database, similar(repository_id, SimilarityKind.CRASHOUT, '1', 'flaky retry loop'))

        assert search(database, repository_id, 'retry') == [(SimilarityKind.CRASHOUT, '1')]

    def test_a_word_not_in_the_text_does_not_match(
        self, database: Database, repository_id: int
    ) -> None:
        store(database, similar(repository_id, SimilarityKind.CRASHOUT, '1', 'flaky retry loop'))

        assert search(database, repository_id, 'schema') == []

    def test_another_repository_is_not_searched(
        self, database: Database, repository_id: int
    ) -> None:
        store(database, similar(repository_id, SimilarityKind.CRASHOUT, '1', 'flaky retry loop'))

        assert search(database, repository_id + 1, 'retry') == []

    def test_a_kind_narrows_the_search(self, database: Database, repository_id: int) -> None:
        store(
            database,
            similar(repository_id, SimilarityKind.CRASHOUT, '1', 'flaky retry loop'),
            similar(repository_id, SimilarityKind.LEDGER_ENTRY, 'a:1', 'flaky retry loop'),
        )

        everything = search(database, repository_id, 'retry')
        ledger = search(database, repository_id, 'retry', kind=SimilarityKind.LEDGER_ENTRY)

        assert set(everything) == {
            (SimilarityKind.CRASHOUT, '1'),
            (SimilarityKind.LEDGER_ENTRY, 'a:1'),
        }
        assert ledger == [(SimilarityKind.LEDGER_ENTRY, 'a:1')]

    def test_the_excluded_kind_and_reference_pair_is_left_out(
        self, database: Database, repository_id: int
    ) -> None:
        store(
            database,
            similar(repository_id, SimilarityKind.CRASHOUT, '1', 'flaky retry loop'),
            similar(repository_id, SimilarityKind.CRASHOUT, '2', 'flaky retry loop'),
            similar(repository_id, SimilarityKind.LEDGER_ENTRY, '1', 'flaky retry loop'),
        )

        found = search(database, repository_id, 'retry', excluding=(SimilarityKind.CRASHOUT, '1'))

        assert set(found) == {
            (SimilarityKind.CRASHOUT, '2'),
            (SimilarityKind.LEDGER_ENTRY, '1'),
        }

    def test_the_closest_text_ranks_first(self, database: Database, repository_id: int) -> None:
        store(
            database,
            similar(repository_id, SimilarityKind.CRASHOUT, 'padded', 'retry ' + 'filler ' * 40),
            similar(repository_id, SimilarityKind.CRASHOUT, 'exact', 'retry'),
        )

        found = search(database, repository_id, 'retry')

        assert found == [(SimilarityKind.CRASHOUT, 'exact'), (SimilarityKind.CRASHOUT, 'padded')]

    def test_a_search_returns_at_most_twenty_rows(
        self, database: Database, repository_id: int
    ) -> None:
        store(
            database,
            *(
                similar(repository_id, SimilarityKind.CRASHOUT, str(number), 'flaky retry loop')
                for number in range(25)
            ),
        )

        assert len(search(database, repository_id, 'retry')) == 20
