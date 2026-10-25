"""The similarity fixtures shared by both tiers: the sqlite database and the stocked harness."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.schemas import DECLARATIONS

from tests.core.similarity.similarity_builders import (
    SQL,
    STORED_REFERENCE,
    STORED_TEXT,
    create_scout_report,
    create_written,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database

    from tests.core.similarity.similarity_builders import SimilarityHarness


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path.joinpath('mightymodels.db')


@pytest.fixture
def database_spec() -> DatabaseSpec:
    return DatabaseSpec(
        schema=SQL.joinpath('schema.sql'),
        statements=SQL.joinpath('statements.sql'),
        declarations=DECLARATIONS,
    )


@pytest.fixture
def database(database_path: Path, database_spec: DatabaseSpec) -> Generator[Database]:
    opened = open_database(database_path, database_spec, ConnectionOptions())
    yield opened
    opened.close()


@pytest.fixture
def stocked(harness: SimilarityHarness) -> SimilarityHarness:
    harness.similarity.record(create_written(STORED_REFERENCE, STORED_TEXT))
    harness.scouts.add_report(create_scout_report())
    return harness
