from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import UnitExitedError
from mightymodels_core.schemas.repositories import REPOSITORY_BY_KEY, RepositoryKeyParams
from mightymodels_core.units_of_work import UnknownRepositoryError, read_entry, write_entry

if TYPE_CHECKING:
    from mightymodels_core.database import Database
    from mightymodels_core.primitives import RepositoryKey


def count_repositories(database: Database, repository_key: RepositoryKey) -> int:
    with database.read() as unit:
        row = unit.one(REPOSITORY_BY_KEY, RepositoryKeyParams(repository_key=repository_key))
    return 0 if row is None else 1


@pytest.mark.integration
class TestReadEntry:
    def test_unknown_repository_key_is_refused_naming_the_key(
        self, database: Database, repository_key: RepositoryKey
    ) -> None:
        with pytest.raises(UnknownRepositoryError) as refusal, read_entry(database, repository_key):
            pytest.fail('the read entry handed out a unit for an unknown key')

        assert refusal.value.repository_key == repository_key
        assert repository_key in str(refusal.value)

    def test_unknown_repository_key_is_not_recorded(
        self, database: Database, repository_key: RepositoryKey
    ) -> None:
        with pytest.raises(UnknownRepositoryError), read_entry(database, repository_key):
            pytest.fail('the read entry handed out a unit for an unknown key')

        assert count_repositories(database, repository_key) == 0

    def test_known_repository_key_yields_the_recorded_id(
        self, database: Database, repository_key: RepositoryKey
    ) -> None:
        with write_entry(database, repository_key) as written:
            pass

        with read_entry(database, repository_key) as read:
            assert read.repository_id == written.repository_id


@pytest.mark.integration
class TestWriteEntry:
    def test_ensures_the_repository_row(
        self, database: Database, repository_key: RepositoryKey
    ) -> None:
        with pytest.raises(UnknownRepositoryError), read_entry(database, repository_key):
            pytest.fail('the repository existed before the write entry')

        with write_entry(database, repository_key) as entry:
            assert entry.repository_id > 0

        assert count_repositories(database, repository_key) == 1

    def test_second_entry_resolves_the_same_id(
        self, database: Database, repository_key: RepositoryKey
    ) -> None:
        with write_entry(database, repository_key) as first:
            pass

        with write_entry(database, repository_key) as second:
            assert second.repository_id == first.repository_id

    def test_failure_in_the_scope_rolls_the_row_back(
        self, database: Database, repository_key: RepositoryKey
    ) -> None:
        with pytest.raises(ZeroDivisionError), write_entry(database, repository_key):
            raise ZeroDivisionError

        assert count_repositories(database, repository_key) == 0

    def test_unit_is_unusable_after_the_scope(
        self, database: Database, repository_key: RepositoryKey
    ) -> None:
        with write_entry(database, repository_key) as entry:
            pass

        with pytest.raises(UnitExitedError):
            entry.unit.one(REPOSITORY_BY_KEY, RepositoryKeyParams(repository_key=repository_key))
