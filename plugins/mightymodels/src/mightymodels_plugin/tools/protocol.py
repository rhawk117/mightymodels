"""What the state tools share: one interface, one dispatch and one way a failure reaches the model.

A tool is an instance holding a handler per action. The server registers the tool's bound method,
the SDK fills that method's `ResolvedCheckouts` parameter from the lifespan state, and the method
hands its handlers and its arguments to `dispatch_action`, which runs the one handler inside one
transaction. The SDK shows the model the text of a `ToolError` and hides everything else as a
crash, so the failures the services anticipate are translated here and nowhere else.

`LifespanState` is what a tool needs from the server's lifespan state. The server's `AppState`
satisfies it, and it is declared here because the server imports the tools.

`ResolvedCheckouts` is a plain assignment because the SDK does not see a `Resolve` marker behind a
PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Callable, Mapping
from typing import Annotated, Protocol, runtime_checkable

from mcp.server.mcpserver import Context, Resolve
from mcp.server.mcpserver.exceptions import ToolError

from mightymodels_plugin.db.checkout import Checkout, Checkouts
from mightymodels_plugin.errors import StateError

type ActionHandler[Call, View] = Callable[[Checkout, Call], View]


class MissingArgumentsError(StateError):
    def __init__(self, action: str, needs: str) -> None:
        super().__init__(f'{action} needs {needs}')
        self.action = action
        self.needs = needs


@runtime_checkable
class ActionTool[Action, Call, View](Protocol):
    @property
    def handlers(self) -> Mapping[Action, ActionHandler[Call, View]]: ...


@runtime_checkable
class LifespanState(Protocol):
    @property
    def checkouts(self) -> Checkouts: ...


def lifespan_checkouts(ctx: Context[LifespanState]) -> Checkouts:
    return ctx.request_context.lifespan_context.checkouts


ResolvedCheckouts = Annotated[Checkouts, Resolve(lifespan_checkouts)]


def dispatch_action[Action, Call, View](
    handlers: Mapping[Action, ActionHandler[Call, View]],
    action: Action,
    call: Call,
    *,
    checkouts: Checkouts,
) -> View:
    try:
        with checkouts.begin() as checkout:
            return handlers[action](checkout, call)
    except StateError as error:
        raise ToolError(str(error)) from error
