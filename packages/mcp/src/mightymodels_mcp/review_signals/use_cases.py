"""The review_signals use cases: the request's values as options, and the root git runs in.

The root is the checkout the server opened its state in, so a call never depends on the working
directory the server was started from.
"""

from typing import TYPE_CHECKING

from .options import SignalsOptions

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.edge import OpenState

    from mightymodels_mcp.server.requests import RequestModel


def options_of(request: RequestModel) -> SignalsOptions:
    return SignalsOptions.model_validate(request.model_dump())


def root_of(state: OpenState) -> Path:
    return state.checkout.toplevel
