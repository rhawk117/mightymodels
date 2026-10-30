"""The review_signals use cases: the git that reads history.

The git runs in the checkout the server opened its state in, so a call never depends on the
working directory the server was started from.
"""

from typing import TYPE_CHECKING

from mightymodels_core.git import GitCommand
from mightymodels_core.git.process_git import GIT_EXECUTABLE
from mightymodels_core.process import get_process_runner

if TYPE_CHECKING:
    from mightymodels_core.edge import OpenState


def create_git_command(state: OpenState) -> GitCommand:
    return GitCommand(
        root=state.checkout.toplevel, executable=GIT_EXECUTABLE, processes=get_process_runner()
    )
