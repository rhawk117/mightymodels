from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from mightymodels_plugin.database import Database, open_database
from mightymodels_plugin.tools.ticket.service import TicketService
from mightymodels_plugin.workspace import Workspace, workspace_at


@contextmanager
def ticket_service_at(root: Path) -> Generator[TicketService]:
    workspace = workspace_at(root)
    workspace.exclude_state_from_git()
    with open_database(workspace.database_file()) as database:
        yield TicketService(workspace=workspace, database=database)


@pytest.fixture
def ticket_service(repository_workspace: Workspace, repository_database: Database) -> TicketService:
    return TicketService(workspace=repository_workspace, database=repository_database)
