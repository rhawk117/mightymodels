"""What the completion gate reads: the tasks the stopping worker started and the facts they need.

The ticket is the one unclosed ticket whose branch is checked out. A plan task is read as its
brief's text, which is `None` when the brief is missing. A residual is read as the task record,
its own contract commands, the latest receipts and what git says of its base and of HEAD. An
`R` task is a residual; a `C` task and any other id is not read. A repository the database has
not recorded, a missing ticket directory and no ticket on the branch read as nothing started.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.contract import SqliteContractRepository
from mightymodels_core.edge import open_state
from mightymodels_core.tasks import SqliteTaskRepository
from mightymodels_core.tasks.gates import GitFacts, is_plan_task
from mightymodels_core.units_of_work import UnknownRepositoryError, read_entry
from mightymodels_core.workspace import workspace_of

from mightymodels_hooks.branch_state import branch_ticket

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mightymodels_core.contract import Receipt, RecordedCommand
    from mightymodels_core.git import Git
    from mightymodels_core.primitives import Slug, TaskId
    from mightymodels_core.tasks import TaskRecord
    from mightymodels_core.units_of_work import Entry
    from mightymodels_core.vocabulary.tasks import Worker
    from mightymodels_core.workspace import Workspace

    from mightymodels_hooks.hook_context import HookContext

RESIDUAL_PREFIX = 'R'


@dataclass(slots=True, kw_only=True, frozen=True)
class PlanTask:
    id: str
    brief: str
    text: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ResidualFacts:
    task: TaskRecord
    commands: Sequence[RecordedCommand]
    receipts: Mapping[str, Receipt]
    base_commit: str | None
    git: GitFacts


@dataclass(slots=True, kw_only=True, frozen=True)
class Unfinished:
    slug: str
    plan_tasks: Sequence[PlanTask]
    residuals: Sequence[ResidualFacts]


@dataclass(slots=True, kw_only=True, frozen=True)
class StartedRows:
    slug: Slug
    plan_ids: Sequence[TaskId]
    residuals: Sequence[TaskRecord]
    commands: Sequence[RecordedCommand]
    receipts: Mapping[str, Receipt]


def started_rows(entry: Entry, branch: str | None, worker: Worker) -> StartedRows | None:
    ticket = branch_ticket(entry, branch).ticket
    if ticket is None:
        return None

    slug = ticket.slug
    ticket_id = ticket.id
    tasks = SqliteTaskRepository(unit=entry.unit)
    contracts = SqliteContractRepository(unit=entry.unit)
    started = tasks.in_progress_started_by(ticket_id, worker)
    residuals = (tasks.task(ticket_id, key) for key in started if key.startswith(RESIDUAL_PREFIX))
    return StartedRows(
        slug=slug,
        plan_ids=[key for key in started if is_plan_task(key)],
        residuals=[record for record in residuals if record is not None],
        commands=contracts.commands(ticket_id),
        receipts=contracts.latest_receipts(ticket_id),
    )


def plan_task_of(workspace: Workspace, slug: Slug, task_id: TaskId) -> PlanTask:
    brief = workspace.task_brief(slug, int(task_id[1:]))
    text = brief.read_text(encoding='utf-8') if brief.is_file() else None
    return PlanTask(id=task_id, brief=workspace.relative_to_root(brief), text=text)


async def git_facts_of(git: Git, task: TaskRecord, head: str | None) -> tuple[str | None, GitFacts]:
    base = None if task.base is None else await git.resolve_commit(task.base)
    if base is None or head is None:
        return base, GitFacts(
            head=head,
            base_resolves=base is not None,
            base_is_ancestor=False,
            changed_files=frozenset(),
            named_commit=None,
        )

    return base, GitFacts(
        head=head,
        base_resolves=True,
        base_is_ancestor=await git.is_ancestor(base, head),
        changed_files=frozenset(await git.changed_files(base, head)),
        named_commit=None,
    )


async def residual_facts_of(git: Git, rows: StartedRows, residual: TaskRecord) -> ResidualFacts:
    head = await git.resolve_head()
    base_commit, facts = await git_facts_of(git, residual, head)
    return ResidualFacts(
        task=residual,
        commands=[command for command in rows.commands if command.task_key == residual.key],
        receipts=rows.receipts,
        base_commit=base_commit,
        git=facts,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class CompletionState:
    context: HookContext

    async def read(self, worker: Worker) -> Unfinished | None:
        async with open_state(self.context.data_directory(), self.context.start()) as state:
            branch = await state.git.current_branch()
            with read_entry(state.database, state.checkout.repository_key()) as entry:
                rows = started_rows(entry, branch, worker)

            if rows is None:
                return None

            workspace = workspace_of(state.checkout.toplevel)
            return Unfinished(
                slug=rows.slug,
                plan_tasks=[plan_task_of(workspace, rows.slug, key) for key in rows.plan_ids],
                residuals=[
                    await residual_facts_of(state.git, rows, residual)
                    for residual in rows.residuals
                ],
            )

    async def unfinished(self, worker: Worker) -> Unfinished | None:
        if not self.context.has_ticket_directory():
            return None

        try:
            return await self.read(worker)
        except UnknownRepositoryError:
            return None
