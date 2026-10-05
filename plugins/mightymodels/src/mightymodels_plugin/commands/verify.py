"""The `mightymodels verify run` command: the one way an approved contract command executes.

The command is its own edge: it opens the database once for the run and disposes its engine
before it returns, and it loads no MCP module.
"""

import argparse
import os
import sys
from pathlib import Path

from mightymodels_plugin.database import open_database
from mightymodels_plugin.db.checkout import Checkouts
from mightymodels_plugin.db.repository import exclude_state_in_repository, find_root
from mightymodels_plugin.errors import StateError
from mightymodels_plugin.models.contract import Phase
from mightymodels_plugin.models.slug import InvalidSlugError, parsed_slug
from mightymodels_plugin.services.verify import RunRequest, run_approved

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
    root = find_root(os.environ, Path.cwd())
    exclude_state_in_repository(root)
    try:
        with open_database(root) as database:
            result = run_approved(Checkouts(root=root, database=database), slug, request)
    except StateError as error:
        return rejected(error)
    sys.stdout.write(result.text)
    return 0 if result.passed else EXIT_FAILED
