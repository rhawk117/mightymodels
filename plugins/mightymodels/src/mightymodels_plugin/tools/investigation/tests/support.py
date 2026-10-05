from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from mightymodels_plugin.database import Database, open_database
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.workspace import Workspace, workspace_at


@contextmanager
def investigation_service_at(root: Path) -> Generator[InvestigationService]:
    workspace = workspace_at(root)
    workspace.exclude_state_from_git()
    with open_database(workspace.database_file()) as database:
        yield InvestigationService(workspace=workspace, database=database)


@pytest.fixture
def investigation_service(
    repository_workspace: Workspace, repository_database: Database
) -> InvestigationService:
    return InvestigationService(workspace=repository_workspace, database=repository_database)
