import pytest

from mightymodels_plugin.database import Database
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.workspace import Workspace


@pytest.fixture
def contract_service(
    repository_workspace: Workspace, repository_database: Database
) -> ContractService:
    return ContractService(workspace=repository_workspace, database=repository_database)
