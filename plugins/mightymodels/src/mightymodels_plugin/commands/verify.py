"""The `mightymodels verify run` command: the one way an approved contract command executes.

The command is its own edge: it builds its workspace, refuses before it opens anything when git
or the repository is missing, because every receipt records the HEAD it ran at, opens the
database once for the run and disposes its engine before it returns. It loads no MCP module.
"""

import argparse
import os
import sys
from pathlib import Path

from mightymodels_plugin.database import open_database
from mightymodels_plugin.db.checkout import Checkouts
from mightymodels_plugin.errors import StateError
from mightymodels_plugin.models.contract import Phase
from mightymodels_plugin.services.verify import RunRequest, run_approved
from mightymodels_plugin.slug import InvalidSlugError, parsed_slug
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
            result = run_approved(Checkouts(workspace=workspace, database=database), slug, request)
    except StateError as error:
        return rejected(error)
    sys.stdout.write(result.text)
    return 0 if result.passed else EXIT_FAILED
