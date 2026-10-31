"""The contract use cases: sync functions, each opening one `TaskWork` unit for one tool call.

Core's only unit carrying the contract service is the task unit, so the contract tools open it.
A unit holds the database connection synchronously and must never be held across an `await`.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .views import render_approved, render_retired, render_run, render_status

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.contract.records import ApprovedCommand
    from mightymodels_core.contract.runs import RunResult
    from mightymodels_core.contract.services import RetireRequest
    from mightymodels_core.primitives import Slug
    from mightymodels_core.units_of_work import TaskWork

    from .views import ContractRunView, ContractView


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


def retire_contract(work: TaskWork, slug: Slug, request: RetireRequest) -> ContractView:
    with work.write() as unit:
        unit.contracts.retire(slug, request)

    return render_retired(request)


def show_contract_run(work: TaskWork, slug: Slug, result: RunResult) -> ContractRunView:
    head = result.receipts[0].head if result.receipts else None
    with work.read() as unit:
        status = unit.contracts.status(slug, head)

    sources = {item.command.key: item.command.approval_source for item in status.commands}
    return render_run(result, sources)
