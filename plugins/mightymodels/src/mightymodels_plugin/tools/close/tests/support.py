import pytest

from mightymodels_plugin.database import Database
from mightymodels_plugin.tools.close.service import CloseService
from mightymodels_plugin.workspace import Workspace


@pytest.fixture
def close_service(repository_workspace: Workspace, repository_database: Database) -> CloseService:
    return CloseService(workspace=repository_workspace, database=repository_database)
