"""The `mightymodels verify run` command: the one way an approved contract command executes."""

import argparse
import os
import sys
from pathlib import Path

from mightymodels_plugin.db.repository import find_root
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
    try:
        result = run_approved(find_root(os.environ, Path.cwd()), slug, request)
    except StateError as error:
        return rejected(error)
    sys.stdout.write(result.text)
    return 0 if result.passed else EXIT_FAILED
