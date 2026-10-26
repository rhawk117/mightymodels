"""The session pointer repository over a real sqlite unit, with a clock the test sets."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.session_pointers import SqliteSessionPointerRepository

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

    from mightymodels_core.database import Database, Unit

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


@dataclass(slots=True, kw_only=True, frozen=True)
class FixedClock:
    moment: datetime

    def now(self) -> datetime:
        return self.moment


type PointersAt = Callable[[str, datetime], SqliteSessionPointerRepository]


@pytest.fixture
def database_spec() -> DatabaseSpec:
    sql = files('mightymodels_core.sql')
    return DatabaseSpec(
        schema=sql.joinpath('schema.sql'),
        statements=sql.joinpath('statements.sql'),
        declarations=DECLARATIONS,
    )


@pytest.fixture
def database(tmp_path: Path, database_spec: DatabaseSpec) -> Generator[Database]:
    opened = open_database(tmp_path.joinpath('mightymodels.db'), database_spec, ConnectionOptions())
    yield opened
    opened.close()


@pytest.fixture
def unit(database: Database) -> Generator[Unit]:
    with database.write() as opened:
        yield opened


@pytest.fixture
def pointers_at(unit: Unit) -> PointersAt:
    def build(repository_key: str, moment: datetime) -> SqliteSessionPointerRepository:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key=repository_key))
        assert repository is not None
        return SqliteSessionPointerRepository(
            unit=unit, repository_id=repository.id, clock=FixedClock(moment=moment)
        )

    return build
