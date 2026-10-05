"""The `contract` tool."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mightymodels_plugin.db.checkout import Checkout
from mightymodels_plugin.models.contract import ContractAction, ContractCommand, ContractView
from mightymodels_plugin.models.slug import Slug
from mightymodels_plugin.services import contract as service
from mightymodels_plugin.tools.protocol import (
    ActionHandler,
    MissingArgumentsError,
    ResolvedCheckouts,
    dispatch_action,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractCall:
    slug: Slug
    commands: list[ContractCommand] | None


def approve_commands(checkout: Checkout, call: ContractCall) -> ContractView:
    if call.commands is None:
        raise MissingArgumentsError(ContractAction.APPROVE, 'the commands the user approved')
    return service.approve(checkout, call.slug, call.commands)


def report_status(checkout: Checkout, call: ContractCall) -> ContractView:
    return service.status(checkout, call.slug)


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractTool:
    handlers: Mapping[ContractAction, ActionHandler[ContractCall, ContractView]]

    def contract(
        self,
        action: ContractAction,
        slug: Slug,
        commands: list[ContractCommand] | None = None,
        *,
        checkouts: ResolvedCheckouts,
    ) -> ContractView:
        """Approve verification commands, or report the latest result per command."""
        call = ContractCall(slug=slug, commands=commands)
        return dispatch_action(self.handlers, action, call, checkouts=checkouts)


contract_tool = ContractTool(
    handlers=MappingProxyType(
        {
            ContractAction.APPROVE: approve_commands,
            ContractAction.STATUS: report_status,
        }
    )
)
