"""How a command refuses: the failure on standard error, and the exit code that says refused."""

import sys

from mightymodels_plugin.errors import StateError

EXIT_REJECTED = 2


def rejected(error: StateError) -> int:
    sys.stderr.write(f'error: {error}\n')
    return EXIT_REJECTED
