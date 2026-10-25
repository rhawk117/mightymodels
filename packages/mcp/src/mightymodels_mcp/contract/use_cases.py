"""The contract use cases: sync functions, each opening one `TaskWork` unit for one tool call.

Core's only unit carrying the contract service is the task unit, so the contract tools open it.
A unit holds the database connection synchronously and must never be held across an `await`.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.edge import create_clock
from mightymodels_core.units_of_work import TaskWork

from .views import render_approved, render_status

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.contract.records import ApprovedCommand
    from mightymodels_core.edge import OpenState
    from mightymodels_core.primitives import Slug

    from .views import ContractView


def create_contract_work(state: OpenState) -> TaskWork:
    return TaskWork(
        database=state.database,
        repository_key=state.checkout.repository_key(),
        clock=create_clock(),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractApproval:
    slug: Slug
    commands: Sequence[ApprovedCommand]
    head: str | None


def approve_contract(work: TaskWork, approval: ContractApproval) -> ContractView:
    with work.write() as unit:
        result = unit.contracts.approve(approval.slug, approval.commands, approval.head)

    return render_approved(result)


def show_contract_status(work: TaskWork, slug: Slug, head: str | None) -> ContractView:
    with work.read() as unit:
        status = unit.contracts.status(slug, head)

    return render_status(status)
