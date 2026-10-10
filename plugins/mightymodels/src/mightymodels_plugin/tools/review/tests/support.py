import pytest

from mightymodels_plugin.database import Database
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.workspace import Workspace


@pytest.fixture
def review_service(repository_workspace: Workspace, repository_database: Database) -> ReviewService:
    return ReviewService(workspace=repository_workspace, database=repository_database)
