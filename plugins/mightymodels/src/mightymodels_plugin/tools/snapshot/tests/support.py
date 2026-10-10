import pytest

from mightymodels_plugin.database import Database
from mightymodels_plugin.tools.snapshot.service import SnapshotService
from mightymodels_plugin.workspace import Workspace


@pytest.fixture
def snapshot_service(
    repository_workspace: Workspace, repository_database: Database
) -> SnapshotService:
    return SnapshotService(workspace=repository_workspace, database=repository_database)
