from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, open_database
from mightymodels_core.edge import create_database_spec
from mightymodels_core.primitives import RepositoryKey

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database


@pytest.fixture
def repository_key() -> RepositoryKey:
    return RepositoryKey('owner/repo')


@pytest.fixture
def database(tmp_path: Path) -> Generator[Database]:
    opened = open_database(
        tmp_path.joinpath('mightymodels.db'), create_database_spec(), ConnectionOptions()
    )
    yield opened
    opened.close()
