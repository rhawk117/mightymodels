"""The review repository over a core unit."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives import RunId, Slug, redact
from mightymodels_core.reviews.errors import RunExistsError, RunNotFoundError
from mightymodels_core.reviews.findings import stored_severity
from mightymodels_core.reviews.records import (
    FINDINGS,
    RUNS_LISTED,
    Evidence,
    FindingRecord,
    ReviewRunRecord,
    finding_write_error,
)
from mightymodels_core.schemas.reviews import (
    LATEST_REVIEW_RUN_OF_TICKET,
    LATEST_REVIEW_RUNS,
    RECORD_REVIEW_MODELS,
    RECORD_REVIEW_RUN,
    REVIEW_FINDINGS_OF_RUN,
    REVIEW_RUN,
    UPSERT_REVIEW_FINDING,
    LatestReviewRunsParams,
    RecordReviewModelsParams,
    RecordReviewRunParams,
    ReviewRunParams,
    RunLimitParams,
    TicketReviewRunParams,
    UpsertReviewFindingParams,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mightymodels_core.database import Unit
    from mightymodels_core.primitives import Latest
    from mightymodels_core.schemas.reviews import ReviewFindingRow, ReviewRunRow


def run_of(row: ReviewRunRow) -> ReviewRunRecord:
    return ReviewRunRecord(
        run_id=RunId(row.run_key),
        slug=None if row.ticket_key is None else Slug(row.ticket_key),
        scope=row.scope,
        base=row.base,
        head=row.head,
        depth=row.depth,
        emphasis=row.emphasis,
        weights=row.weights,
        personas=tuple(row.personas),
        models=row.models,
        created_at=row.created_at,
    )


def evidence_of(row: ReviewFindingRow) -> Evidence | None:
    if row.evidence_kind is None:
        return None

    cite = '' if row.evidence_cite is None else row.evidence_cite
    return Evidence(kind=row.evidence_kind, cite=redact(cite))


def finding_of(row: ReviewFindingRow) -> FindingRecord:
    return FindingRecord(
        key=row.finding_key,
        sources=tuple(row.sources),
        severity=stored_severity(row.severity),
        kind=row.kind,
        security=row.security,
        title=redact(row.title),
        location=redact(row.location),
        fix=redact(row.fix),
        verify=redact(row.verify),
        evidence=evidence_of(row),
        conflict=None if row.conflict is None else redact(row.conflict),
    )


def run_params_of(repository_id: int, run: ReviewRunRecord) -> RecordReviewRunParams:
    return RecordReviewRunParams(
        repository_id=repository_id,
        run_key=run.run_id,
        ticket_key=run.slug,
        scope=run.scope,
        base=run.base,
        head=run.head,
        depth=run.depth,
        emphasis=run.emphasis,
        weights=dict(run.weights),
        personas=list(run.personas),
        models=dict(run.models),
        created_at=run.created_at,
    )


def finding_params_of(review_run_id: int, finding: FindingRecord) -> UpsertReviewFindingParams:
    evidence = finding.evidence
    return UpsertReviewFindingParams(
        review_run_id=review_run_id,
        finding_key=finding.key,
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


def run_row_of(unit: Unit, repository_id: int, run: RunId) -> ReviewRunRow | None:
    return unit.one(REVIEW_RUN, ReviewRunParams(repository_id=repository_id, run_key=run))


def finding_rows_of(unit: Unit, review_run_id: int, run: RunId) -> list[ReviewFindingRow]:
    params = RunLimitParams(review_run_id=review_run_id, limit=FINDINGS.fetched)
    rows = unit.all(REVIEW_FINDINGS_OF_RUN, params)
    if (error := FINDINGS.error(rows, owner=f'run {run}')) is not None:
        raise error
    return rows


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteReviewRepository:
    unit: Unit
    repository_id: int

    def run(self, run: RunId) -> ReviewRunRecord | None:
        row = run_row_of(self.unit, self.repository_id, run)
        return None if row is None else run_of(row)

    def started_run(self, run: RunId) -> ReviewRunRecord:
        if (started := self.run(run)) is None:
            raise RunNotFoundError(run=run)
        return started

    def latest_runs(self) -> Latest[ReviewRunRecord]:
        params = LatestReviewRunsParams(repository_id=self.repository_id, limit=RUNS_LISTED.fetched)
        newest_first = [run_of(row) for row in self.unit.all(LATEST_REVIEW_RUNS, params)]
        return RUNS_LISTED.latest(newest_first)

    def latest_run(self, slug: Slug) -> ReviewRunRecord | None:
        params = TicketReviewRunParams(repository_id=self.repository_id, ticket_key=slug)
        row = self.unit.one(LATEST_REVIEW_RUN_OF_TICKET, params)
        return None if row is None else run_of(row)

    def findings(self, run: RunId) -> list[FindingRecord]:
        if (run_row := run_row_of(self.unit, self.repository_id, run)) is None:
            return []

        return [finding_of(row) for row in finding_rows_of(self.unit, run_row.id, run)]

    def record_run(self, run: ReviewRunRecord) -> None:
        if self.run(run.run_id) is not None:
            raise RunExistsError(run=run.run_id)

        self.unit.all(RECORD_REVIEW_RUN, run_params_of(self.repository_id, run))

    def record_models(self, run: RunId, models: Mapping[str, str | None]) -> None:
        params = RecordReviewModelsParams(
            repository_id=self.repository_id, run_key=run, models=dict(models)
        )
        if self.unit.run(RECORD_REVIEW_MODELS, params) == 0:
            raise RunNotFoundError(run=run)

    def record_findings(self, run: RunId, findings: Sequence[FindingRecord]) -> None:
        if (run_row := run_row_of(self.unit, self.repository_id, run)) is None:
            raise RunNotFoundError(run=run)

        held_keys = [row.finding_key for row in finding_rows_of(self.unit, run_row.id, run)]
        if (error := finding_write_error(run, held_keys, findings)) is not None:
            raise error

        batch = [finding_params_of(run_row.id, finding) for finding in findings]
        self.unit.run_many(UPSERT_REVIEW_FINDING, batch)
