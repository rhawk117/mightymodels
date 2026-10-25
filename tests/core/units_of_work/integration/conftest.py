"""The unit-of-work harness over a real sqlite database."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, open_database
from mightymodels_core.edge import create_database_spec
from mightymodels_core.workspace import workspace_at

from tests.core.units_of_work.units_of_work_builders import UnitsOfWorkHarness

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


@pytest.fixture
def harness(tmp_path: Path) -> Generator[UnitsOfWorkHarness]:
    database = open_database(
        tmp_path.joinpath('mightymodels.db'), create_database_spec(), ConnectionOptions()
    )
    yield UnitsOfWorkHarness(
        database=database, workspace=workspace_at(tmp_path.joinpath('project'))
    )
    database.close()
