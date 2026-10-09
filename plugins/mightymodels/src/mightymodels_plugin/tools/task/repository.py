"""A ticket's tasks, their attempts and their transitions, reached only through a repository.

`task_transaction` opens one transaction on the database and hands out the task repository, so the
task service never sees a session. A task action also reads the ticket's row and the ticket's
contract, so the repository carries a `TicketRepository` and a `ContractRepository`, both built
here on that same session and nowhere else: one transaction serves the three. All three hold the
key of the git repository the database was opened for, and every read and write is under it.

A method that changes a task takes the transition the change is part of and stores the
transition's row with it, so no task moves without its record.

A task's base is the HEAD of its first start that had one. A restart keeps it, so what the task
changed is measured from where its first attempt began.
"""

from collections.abc import Collection, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from mightymodels_plugin.database import Database
from mightymodels_plugin.repository_key import RepositoryKey
from mightymodels_plugin.slug import Slug
from mightymodels_plugin.tools.contract.repository import ContractRepository
from mightymodels_plugin.tools.task.schema import ArchitectMode, Implementer, Status
from mightymodels_plugin.tools.task.tables import AttemptRow, TaskRow, TransitionRow
from mightymodels_plugin.tools.ticket.repository import TicketRepository

type AttemptCounts = dict[str, dict[str, int]]


@dataclass(slots=True, kw_only=True, frozen=True)
class Transition:
    task_id: str
    before: Status
    after: Status
    reasons: Sequence[str]
    head: str | None
    at: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Attempt:
    worker: Implementer
    mode: ArchitectMode | None
    owned: Sequence[str]


def transition_row(
    slug: Slug, transition: Transition, *, repository_key: RepositoryKey
) -> TransitionRow:
    return TransitionRow(
        repository_key=repository_key.root,
        slug=slug.root,
        task_id=transition.task_id,
        before=transition.before,
        after=transition.after,
        reasons=list(transition.reasons),
        head=transition.head,
        at=transition.at,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskRepository:
    session: Session
    repository_key: RepositoryKey
    tickets: TicketRepository
    contracts: ContractRepository

    def row(self, slug: Slug, task_id: str) -> TaskRow | None:
        return self.session.get(TaskRow, (self.repository_key.root, slug.root, task_id))

    def rows(self, slug: Slug) -> list[TaskRow]:
        query = select(TaskRow).where(
            TaskRow.repository_key == self.repository_key.root, TaskRow.slug == slug.root
        )
        return list(self.session.scalars(query))

    def attempts_by_worker(self, slug: Slug) -> AttemptCounts:
        query = (
            select(AttemptRow)
            .where(
                AttemptRow.repository_key == self.repository_key.root,
                AttemptRow.slug == slug.root,
            )
            .order_by(AttemptRow.id)
        )
        counts: AttemptCounts = {}
        for attempt in self.session.scalars(query):
            by_worker = counts.setdefault(attempt.task_id, {})
            by_worker[attempt.worker] = by_worker.get(attempt.worker, 0) + 1
        return counts

    def attempts_in_modes(self, slug: Slug, task_id: str, modes: Collection[ArchitectMode]) -> int:
        query = select(AttemptRow).where(
            AttemptRow.repository_key == self.repository_key.root,
            AttemptRow.slug == slug.root,
            AttemptRow.task_id == task_id,
            AttemptRow.mode.in_(sorted(modes)),
        )
        return len(self.session.scalars(query).all())

    def transition_rows(self, slug: Slug) -> list[TransitionRow]:
        query = (
            select(TransitionRow)
            .where(
                TransitionRow.repository_key == self.repository_key.root,
                TransitionRow.slug == slug.root,
            )
            .order_by(TransitionRow.id)
        )
        return list(self.session.scalars(query))

    def record_start(self, slug: Slug, transition: Transition, attempt: Attempt) -> None:
        started = self.row(slug, transition.task_id)
        first_base = None if started is None else started.base
        self.session.merge(
            TaskRow(
                repository_key=self.repository_key.root,
                slug=slug.root,
                task_id=transition.task_id,
                status=transition.after,
                owned=list(attempt.owned),
                base=transition.head if first_base is None else first_base,
                commit=None,
                reasons=[],
                updated_at=transition.at,
            )
        )
        self.session.add(
            AttemptRow(
                repository_key=self.repository_key.root,
                slug=slug.root,
                task_id=transition.task_id,
                worker=attempt.worker,
                mode=attempt.mode,
                at=transition.at,
            )
        )
        self.session.add(transition_row(slug, transition, repository_key=self.repository_key))

    def record_verification(self, slug: Slug, transition: Transition, commit: str) -> None:
        row = self.session.get_one(
            TaskRow, (self.repository_key.root, slug.root, transition.task_id)
        )
        row.status = transition.after
        row.commit = commit
        row.reasons = list(transition.reasons)
        row.updated_at = transition.at
        self.session.add(transition_row(slug, transition, repository_key=self.repository_key))

    def record_mark(self, slug: Slug, transition: Transition) -> None:
        row = self.session.get_one(
            TaskRow, (self.repository_key.root, slug.root, transition.task_id)
        )
        row.status = transition.after
        row.reasons = list(transition.reasons)
        row.updated_at = transition.at
        self.session.add(transition_row(slug, transition, repository_key=self.repository_key))


@contextmanager
def task_transaction(database: Database) -> Generator[TaskRepository]:
    with database.transaction() as session:
        repository_key = database.repository_key
        yield TaskRepository(
            session=session,
            repository_key=repository_key,
            tickets=TicketRepository(session=session, repository_key=repository_key),
            contracts=ContractRepository(session=session, repository_key=repository_key),
        )
