"""The `mightymodels-mcp` console script: validate the environment, then serve over stdio."""

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mightymodels_core.edge import PLUGIN_DATA_VARIABLE, data_directory_from
from mightymodels_core.workspace import find_root

from mightymodels_mcp.contract.tools import register_contract_tools
from mightymodels_mcp.investigation.tools import register_investigation_tools
from mightymodels_mcp.journal.tools import register_journal_tools
from mightymodels_mcp.review.decision_tools import register_decision_tools
from mightymodels_mcp.review.tools import register_review_tools
from mightymodels_mcp.server.app import create_server
from mightymodels_mcp.server.call_log import (
    InvalidLogLevelError,
    LogSettings,
    installed_logging,
    parse_log_level,
)
from mightymodels_mcp.server.dependencies import ServerDependencies
from mightymodels_mcp.server.registration import ToolCatalog
from mightymodels_mcp.server.state import LocalStateOpener, discard_outdated_database
from mightymodels_mcp.snapshot.tools import register_snapshot_tools
from mightymodels_mcp.task.tools import register_task_tools
from mightymodels_mcp.ticket.tools import register_ticket_tools

if TYPE_CHECKING:
    from collections.abc import Mapping

REFUSED_START = 2


REGISTRARS = (
    register_ticket_tools,
    register_task_tools,
    register_contract_tools,
    register_review_tools,
    register_decision_tools,
    register_snapshot_tools,
    register_investigation_tools,
    register_journal_tools,
)


def create_catalog() -> ToolCatalog:
    catalog = ToolCatalog()
    for register in REGISTRARS:
        register(catalog)

    return catalog


def run(environ: Mapping[str, str], cwd: Path) -> int:
    data_directory = data_directory_from(environ, PLUGIN_DATA_VARIABLE)
    if not isinstance(data_directory, Path):
        sys.stderr.write(f'{data_directory}\n')
        return REFUSED_START

    level = parse_log_level(environ)
    if isinstance(level, InvalidLogLevelError):
        sys.stderr.write(f'{level}\n')
        return REFUSED_START

    state = LocalStateOpener(data_directory=data_directory, start=find_root(environ, cwd))
    with installed_logging(
        LogSettings(level=level, data_directory=data_directory, stream=sys.stderr)
    ):
        discard_outdated_database(data_directory)
        create_server(ServerDependencies(state=state), create_catalog()).run()

    return 0


def main() -> int:
    return run(os.environ, Path.cwd())
