"""The `crashout` tool: each handler checks the call's arguments and asks the crashout service.

`add` needs the crashout to journal, and `journal_crashout` is the one place that refuses a call
without it. `stats` and `last` take nothing.

`ResolvedCrashouts` is a plain assignment because the SDK does not see a `Resolve` marker behind
a PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.tools.crashout.schema import CrashoutAction, CrashoutEntry, CrashoutView
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    MissingArgumentsError,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutCall:
    entry: CrashoutEntry | None


def journal_crashout(crashouts: CrashoutService, call: CrashoutCall) -> CrashoutView:
    if call.entry is None:
        raise MissingArgumentsError(CrashoutAction.ADD, 'an entry holding the crashout')
    return crashouts.add(call.entry)


def report_patterns(crashouts: CrashoutService, _call: CrashoutCall) -> CrashoutView:
    return crashouts.stats()


def show_last_crashout(crashouts: CrashoutService, _call: CrashoutCall) -> CrashoutView:
    return crashouts.last()


def lifespan_crashouts(ctx: Context[ServedState]) -> CrashoutService:
    return served_services(ctx).crashouts


ResolvedCrashouts = Annotated[CrashoutService, Resolve(lifespan_crashouts)]


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutTool:
    handlers: Mapping[CrashoutAction, ServiceHandler[CrashoutService, CrashoutCall, CrashoutView]]

    def crashout(
        self,
        action: CrashoutAction,
        entry: CrashoutEntry | None = None,
        *,
        crashouts: ResolvedCrashouts,
    ) -> CrashoutView:
        """Journal a crashout, or report recurring patterns."""
        call = CrashoutCall(entry=entry)
        return dispatch_to_service(self.handlers, action, call, service=crashouts)


crashout_tool = CrashoutTool(
    handlers=MappingProxyType(
        {
            CrashoutAction.ADD: journal_crashout,
            CrashoutAction.STATS: report_patterns,
            CrashoutAction.LAST: show_last_crashout,
        }
    )
)
crashout_action_tool: ActionTool[CrashoutAction, CrashoutService, CrashoutCall, CrashoutView] = (
    crashout_tool
)
