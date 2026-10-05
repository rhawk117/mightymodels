import pytest

from mightymodels_plugin.database import Database
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.workspace import Workspace


@pytest.fixture
def task_service(repository_workspace: Workspace, repository_database: Database) -> TaskService:
    return TaskService(workspace=repository_workspace, database=repository_database)
