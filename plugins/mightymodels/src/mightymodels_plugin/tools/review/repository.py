"""Review runs, their findings, the user's decisions and the fix outcomes, behind one repository.

`review_transaction` opens one transaction on the database and hands out the review repository,
so the review service never sees a session. Starting a run also reads the ticket's row, so the
repository carries a `TicketRepository`, built here on that same session and nowhere else: one
transaction serves the two. Each repository here holds the key of the git repository the database
was opened for, and every read, write and delete is under that key.

The user's decisions and the fix outcomes sit on a `DecisionRepository` that the review
repository carries the same way. Its `reopen` is the only delete here: the findings it is given
lose their decision and their outcome and read as undecided again.

A method that writes takes values and builds the rows itself. `DecidedFinding` and
`ResolvedFinding` are what the user decided and what a fix came to, as they are stored.
"""

from collections.abc import Collection, Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mightymodels_plugin.database import Database
from mightymodels_plugin.repository_key import RepositoryKey
from mightymodels_plugin.run_id import RunId
from mightymodels_plugin.slug import Slug
from mightymodels_plugin.tools.review.errors import RunNotFoundError
from mightymodels_plugin.tools.review.schema import Decision, Finding, Result, ReviewRun
from mightymodels_plugin.tools.review.tables import (
    ReviewDispositionRow,
    ReviewFindingRow,
    ReviewOutcomeRow,
    ReviewRunRow,
)
from mightymodels_plugin.tools.ticket.repository import TicketRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class DecidedFinding:
    finding_id: str
    decision: Decision
    reason: str
    by: str
    at: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ResolvedFinding:
    finding_id: str
    result: Result
    commit: str
    reason: str
    at: str


def run_row_of(run: ReviewRun, *, repository_key: RepositoryKey) -> ReviewRunRow:
    return ReviewRunRow(
        repository_key=repository_key.root,
        run_id=run.run_id.root,
        slug=None if run.slug is None else run.slug.root,
        scope=run.scope,
        base=run.base,
        head=run.head,
        depth=run.depth,
        emphasis=run.emphasis,
        weights={persona.value: weight for persona, weight in run.weights.items()},
        personas=[persona.value for persona in run.personas],
        models=dict(run.models),
        created_at=run.created_at,
    )


def finding_row_of(
    run: RunId, finding: Finding, *, repository_key: RepositoryKey
) -> ReviewFindingRow:
    evidence = finding.evidence
    return ReviewFindingRow(
        repository_key=repository_key.root,
        run_id=run.root,
        finding_id=finding.id,
        sources=list(finding.sources),
        severity=finding.severity,
        kind=finding.kind,
        security=finding.security,
        title=finding.title,
        location=finding.location,
        fix=finding.fix,
        verify=finding.verify,
        evidence_kind=None if evidence is None else evidence.kind,
        evidence_cite=None if evidence is None else evidence.cite,
        conflict=finding.conflict,
    )


def disposition_row_of(
    run: RunId, decided: DecidedFinding, *, repository_key: RepositoryKey
) -> ReviewDispositionRow:
    return ReviewDispositionRow(
        repository_key=repository_key.root,
        run_id=run.root,
        finding_id=decided.finding_id,
        decision=decided.decision,
        reason=decided.reason,
        by=decided.by,
        at=decided.at,
    )


def outcome_row_of(
    run: RunId, resolved: ResolvedFinding, *, repository_key: RepositoryKey
) -> ReviewOutcomeRow:
    return ReviewOutcomeRow(
        repository_key=repository_key.root,
        run_id=run.root,
        finding_id=resolved.finding_id,
        result=resolved.result,
        commit=resolved.commit,
        reason=resolved.reason,
        at=resolved.at,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class DecisionRepository:
    session: Session
    repository_key: RepositoryKey

    def disposition_rows(self, run: RunId) -> list[ReviewDispositionRow]:
        query = select(ReviewDispositionRow).where(
            ReviewDispositionRow.repository_key == self.repository_key.root,
            ReviewDispositionRow.run_id == run.root,
        )
        return list(self.session.scalars(query))

    def outcome_rows(self, run: RunId) -> list[ReviewOutcomeRow]:
        query = select(ReviewOutcomeRow).where(
            ReviewOutcomeRow.repository_key == self.repository_key.root,
            ReviewOutcomeRow.run_id == run.root,
        )
        return list(self.session.scalars(query))

    def record_dispositions(self, run: RunId, decided: Iterable[DecidedFinding]) -> None:
        for decision in decided:
            self.session.merge(
                disposition_row_of(run, decision, repository_key=self.repository_key)
            )

    def record_outcome(self, run: RunId, resolved: ResolvedFinding) -> None:
        self.session.merge(outcome_row_of(run, resolved, repository_key=self.repository_key))

    def reopen(self, run: RunId, finding_ids: Collection[str]) -> None:
        for row_type in (ReviewDispositionRow, ReviewOutcomeRow):
            reopened = delete(row_type).where(
                row_type.repository_key == self.repository_key.root,
                row_type.run_id == run.root,
                row_type.finding_id.in_(finding_ids),
            )
            self.session.execute(reopened)


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewRepository:
    session: Session
    repository_key: RepositoryKey
    tickets: TicketRepository
    decisions: DecisionRepository

    def run_row(self, run: RunId) -> ReviewRunRow | None:
        return self.session.get(ReviewRunRow, (self.repository_key.root, run.root))

    def started_run_row(self, run: RunId) -> ReviewRunRow:
        row = self.run_row(run)
        if row is None:
            raise RunNotFoundError(run)
        return row

    def run_rows(self) -> list[ReviewRunRow]:
        query = (
            select(ReviewRunRow)
            .where(ReviewRunRow.repository_key == self.repository_key.root)
            .order_by(ReviewRunRow.run_id)
        )
        return list(self.session.scalars(query))

    def latest_run_row(self, slug: Slug) -> ReviewRunRow | None:
        query = (
            select(ReviewRunRow)
            .where(
                ReviewRunRow.repository_key == self.repository_key.root,
                ReviewRunRow.slug == slug.root,
            )
            .order_by(ReviewRunRow.run_id.desc())
        )
        return self.session.scalars(query).first()

    def finding_rows(self, run: RunId) -> list[ReviewFindingRow]:
        query = select(ReviewFindingRow).where(
            ReviewFindingRow.repository_key == self.repository_key.root,
            ReviewFindingRow.run_id == run.root,
        )
        return list(self.session.scalars(query))

    def record_run(self, run: ReviewRun) -> None:
        self.session.add(run_row_of(run, repository_key=self.repository_key))

    def record_findings(self, run: RunId, findings: Iterable[Finding]) -> None:
        for finding in findings:
            self.session.merge(finding_row_of(run, finding, repository_key=self.repository_key))


@contextmanager
def review_transaction(database: Database) -> Generator[ReviewRepository]:
    with database.transaction() as session:
        repository_key = database.repository_key
        yield ReviewRepository(
            session=session,
            repository_key=repository_key,
            tickets=TicketRepository(session=session, repository_key=repository_key),
            decisions=DecisionRepository(session=session, repository_key=repository_key),
        )
