"""What every tool shares: the checkout it works in and how its failures reach the model.

The SDK shows the model the text of a `ToolError` and hides everything else as a crash, so
the failures the services anticipate are translated here and nowhere else.
"""

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from mcp.server.mcpserver.exceptions import ToolError

from mightymodels_plugin.db.checkout import Checkout, open_checkout
from mightymodels_plugin.db.repository import find_root
from mightymodels_plugin.errors import StateError


class ArgumentsError(StateError):
    def __init__(self, action: str, needs: str) -> None:
        super().__init__(f'{action} needs {needs}')
        self.action = action
        self.needs = needs


@contextmanager
def tool_checkout() -> Generator[Checkout]:
    try:
        with open_checkout(find_root(os.environ, Path.cwd())) as checkout:
            yield checkout
    except StateError as error:
        raise ToolError(str(error)) from error
