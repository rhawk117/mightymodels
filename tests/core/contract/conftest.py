"""The contract fixtures: a database over the schema, and the service harnesses."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.schemas.tickets import TICKET_BY_SLUG, TicketSlugParams
from mightymodels_core.tickets import SqliteTicketRepository

from tests.core.contract.contract_builders import (
    APPROVAL,
    FIRST_KEY,
    SECOND_KEY,
    SQL,
    TICKET_SLUGS,
    create_command,
    create_service_harness,
    create_ticket_section,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database

    from tests.core.contract.contract_builders import ServiceHarness


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
def staged_ticket_ids(database: Database) -> tuple[int, int]:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
        tickets = SqliteTicketRepository(unit=unit, repository_id=repository.id)
        ids: list[int] = []
        for slug in TICKET_SLUGS:
            tickets.stage(slug, create_ticket_section(slug), ())
            row = unit.one(TICKET_BY_SLUG, TicketSlugParams(repository_id=repository.id, slug=slug))
            assert row is not None
            ids.append(row.id)
    first, second = ids
    return first, second


@pytest.fixture
def service_harness() -> ServiceHarness:
    return create_service_harness()


@pytest.fixture
def stocked_service_harness(service_harness: ServiceHarness) -> ServiceHarness:
    commands = [create_command(FIRST_KEY), create_command(SECOND_KEY)]
    service_harness.contracts.approve(service_harness.ticket_id, commands, APPROVAL)
    return service_harness
