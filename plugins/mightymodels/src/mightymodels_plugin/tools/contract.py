"""The `contract` tool."""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from mightymodels_plugin.db.checkout import Checkout
from mightymodels_plugin.models.contract import ContractAction, ContractCommand, ContractView
from mightymodels_plugin.models.slug import Slug
from mightymodels_plugin.services import contract as service
from mightymodels_plugin.tools.edge import ArgumentsError, tool_checkout

type Commands = list[ContractCommand] | None
type ContractHandler = Callable[[Checkout, Slug, Commands], ContractView]


def approve(checkout: Checkout, slug: Slug, commands: Commands) -> ContractView:
    if commands is None:
        raise ArgumentsError(ContractAction.APPROVE, 'the commands the user approved')
    return service.approve(checkout, slug, commands)


def status(checkout: Checkout, slug: Slug, _commands: Commands) -> ContractView:
    return service.status(checkout, slug)


HANDLERS: Mapping[ContractAction, ContractHandler] = MappingProxyType(
    {ContractAction.APPROVE: approve, ContractAction.STATUS: status}
)


def contract(
    action: ContractAction, slug: Slug, commands: list[ContractCommand] | None = None
) -> ContractView:
    """Approve verification commands, or report the latest result per command."""
    with tool_checkout() as checkout:
        return HANDLERS[action](checkout, slug, commands)
