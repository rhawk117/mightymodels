"""The `mightymodels verify run` command: the one way an approved contract command executes.

The command is its own edge: it builds its workspace, refuses before it opens anything when git
or the repository is missing, because every receipt records the HEAD it ran at, opens the
database once for the run, builds the contract service over the two as the server's lifespan
does, and disposes the engine before it returns. It loads no MCP module.
"""

import argparse
import os
import sys
from pathlib import Path

from mightymodels_plugin.database import open_database
from mightymodels_plugin.errors import StateError
from mightymodels_plugin.slug import InvalidSlugError, parsed_slug
from mightymodels_plugin.tools.contract.schema import Phase
from mightymodels_plugin.tools.contract.service import ContractService, RunRequest
from mightymodels_plugin.workspace import find_root, workspace_at

EXIT_FAILED = 1
EXIT_REJECTED = 2


def rejected(error: StateError) -> int:
    sys.stderr.write(f'error: {error}\n')
    return EXIT_REJECTED


def verify_run(arguments: argparse.Namespace) -> int:
    slug = parsed_slug(arguments.slug)
    if isinstance(slug, InvalidSlugError):
        return rejected(slug)
    ids = None if arguments.all else tuple(arguments.id)
    request = RunRequest(ids=ids, phase=Phase(arguments.phase))
    workspace = workspace_at(find_root(os.environ, Path.cwd()))
    refusal = workspace.git.refusal()
    if refusal is not None:
        return rejected(refusal)
    workspace.exclude_state_from_git()
    try:
        with open_database(workspace.database_file()) as database:
            contracts = ContractService(workspace=workspace, database=database)
            result = contracts.run_approved(slug, request)
    except StateError as error:
        return rejected(error)
    sys.stdout.write(result.text)
    return 0 if result.passed else EXIT_FAILED
