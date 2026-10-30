"""The review_signals use cases: the request's values as options, and the git that reads history.

The git runs in the checkout the server opened its state in, so a call never depends on the
working directory the server was started from.
"""

from typing import TYPE_CHECKING

from mightymodels_core.git import GitCommand
from mightymodels_core.git.process_git import GIT_EXECUTABLE
from mightymodels_core.process import get_process_runner

from .options import SignalsOptions

if TYPE_CHECKING:
    from mightymodels_core.edge import OpenState

    from mightymodels_mcp.server.requests import RequestModel


def options_of(request: RequestModel) -> SignalsOptions:
    return SignalsOptions.model_validate(request.model_dump())


def create_git_command(state: OpenState) -> GitCommand:
    return GitCommand(
        root=state.checkout.toplevel, executable=GIT_EXECUTABLE, processes=get_process_runner()
    )
