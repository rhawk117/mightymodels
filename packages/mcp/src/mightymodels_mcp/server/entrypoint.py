"""The `mightymodels-mcp` console script: validate the environment, then serve over stdio."""

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mightymodels_core.edge import PLUGIN_DATA_VARIABLE, data_directory_from
from mightymodels_core.workspace import find_root

from mightymodels_mcp.contract.tools import register_contract_tools
from mightymodels_mcp.review.tools import register_review_tools
from mightymodels_mcp.task.tools import register_task_tools
from mightymodels_mcp.ticket.tools import register_ticket_tools

from .app import create_server
from .call_log import InvalidLogLevelError, LogSettings, installed_logging, parse_log_level
from .dependencies import ServerDependencies
from .registration import ToolCatalog
from .state import LocalStateOpener

if TYPE_CHECKING:
    from collections.abc import Mapping

REFUSED_START = 2


def create_catalog() -> ToolCatalog:
    tickets = register_ticket_tools(ToolCatalog())
    return register_review_tools(register_contract_tools(register_task_tools(tickets)))


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
        create_server(ServerDependencies(state=state), create_catalog()).run()

    return 0


def main() -> int:
    return run(os.environ, Path.cwd())
