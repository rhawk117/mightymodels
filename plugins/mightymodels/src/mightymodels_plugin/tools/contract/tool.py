"""The `contract` tool: each handler checks the call's arguments and asks the contract service.

`ResolvedContracts` is a plain assignment because the SDK does not see a `Resolve` marker behind a
PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.slug import Slug
from mightymodels_plugin.tools.contract.schema import ContractAction, ContractCommand, ContractView
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    MissingArgumentsError,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractCall:
    slug: Slug
    commands: list[ContractCommand] | None


def approve_commands(contracts: ContractService, call: ContractCall) -> ContractView:
    if call.commands is None:
        raise MissingArgumentsError(ContractAction.APPROVE, 'the commands the user approved')
    return contracts.approve(call.slug, call.commands)


def report_status(contracts: ContractService, call: ContractCall) -> ContractView:
    return contracts.status(call.slug)


def lifespan_contracts(ctx: Context[ServedState]) -> ContractService:
    return served_services(ctx).contracts


ResolvedContracts = Annotated[ContractService, Resolve(lifespan_contracts)]


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractTool:
    handlers: Mapping[ContractAction, ServiceHandler[ContractService, ContractCall, ContractView]]

    def contract(
        self,
        action: ContractAction,
        slug: Slug,
        commands: list[ContractCommand] | None = None,
        *,
        contracts: ResolvedContracts,
    ) -> ContractView:
        """Approve verification commands, or report the latest result per command."""
        call = ContractCall(slug=slug, commands=commands)
        return dispatch_to_service(self.handlers, action, call, service=contracts)


contract_tool = ContractTool(
    handlers=MappingProxyType(
        {
            ContractAction.APPROVE: approve_commands,
            ContractAction.STATUS: report_status,
        }
    )
)
contract_action_tool: ActionTool[ContractAction, ContractService, ContractCall, ContractView] = (
    contract_tool
)
