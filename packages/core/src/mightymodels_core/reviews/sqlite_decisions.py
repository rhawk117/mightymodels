"""The review decision repository over a core unit."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives import redact
from mightymodels_core.reviews.errors import RunNotFoundError
from mightymodels_core.reviews.records import (
    FINDINGS,
    DecidedFinding,
    ResolvedFinding,
    undecided_finding_error,
    unknown_finding_error,
)
from mightymodels_core.reviews.sqlite_runs import finding_rows_of, run_row_of
from mightymodels_core.schemas.reviews import (
    DELETE_REVIEW_DISPOSITIONS,
    DELETE_REVIEW_OUTCOMES,
    REVIEW_DISPOSITIONS_OF_RUN,
    REVIEW_OUTCOMES_OF_RUN,
    UPSERT_REVIEW_DISPOSITION,
    UPSERT_REVIEW_OUTCOME,
    FindingKeysParams,
    RunLimitParams,
    UpsertReviewDispositionParams,
    UpsertReviewOutcomeParams,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from mightymodels_core.database import Unit
    from mightymodels_core.primitives import RunId
    from mightymodels_core.schemas.reviews import ReviewDispositionRow, ReviewOutcomeRow


def decided_of(row: ReviewDispositionRow) -> DecidedFinding:
    return DecidedFinding(
        finding_key=row.finding_key,
        decision=row.decision,
        reason=redact(row.reason),
        by=redact(row.by),
        at=row.at,
    )


def resolved_of(row: ReviewOutcomeRow) -> ResolvedFinding:
    return ResolvedFinding(
        finding_key=row.finding_key,
        result=row.result,
        commit=row.commit,
        reason=redact(row.reason),
        at=row.at,
    )


def disposition_params_of(
    finding_id: int, decided: DecidedFinding
) -> UpsertReviewDispositionParams:
    return UpsertReviewDispositionParams(
        review_finding_id=finding_id,
        decision=decided.decision,
        reason=decided.reason,
        by=decided.by,
        at=decided.at,
    )


def outcome_params_of(disposition_id: int, resolved: ResolvedFinding) -> UpsertReviewOutcomeParams:
    return UpsertReviewOutcomeParams(
        review_disposition_id=disposition_id,
        result=resolved.result,
        commit=resolved.commit,
        reason=resolved.reason,
        at=resolved.at,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteReviewDecisionRepository:
    unit: Unit
    repository_id: int

    def dispositions(self, run: RunId) -> list[DecidedFinding]:
        return [decided_of(row) for row in self.disposition_rows(run)]

    def outcomes(self, run: RunId) -> list[ResolvedFinding]:
        if (run_id := self.run_id_of(run)) is None:
            return []

        params = RunLimitParams(review_run_id=run_id, limit=FINDINGS.fetched)
        rows = self.unit.all(REVIEW_OUTCOMES_OF_RUN, params)
        if (error := FINDINGS.error(rows, owner=f'run {run}')) is not None:
            raise error
        return [resolved_of(row) for row in rows]

    def record_dispositions(self, run: RunId, decided: Sequence[DecidedFinding]) -> None:
        run_id = self.started_run_id(run)
        finding_ids = {row.finding_key: row.id for row in finding_rows_of(self.unit, run_id, run)}
        if (unknown := unknown_finding_error(run, finding_ids.keys(), decided)) is not None:
            raise unknown

        batch = [disposition_params_of(finding_ids[item.finding_key], item) for item in decided]
        self.unit.run_many(UPSERT_REVIEW_DISPOSITION, batch)

    def record_outcome(self, run: RunId, resolved: ResolvedFinding) -> None:
        self.started_run_id(run)
        disposition_ids = {row.finding_key: row.id for row in self.disposition_rows(run)}
        if (
            undecided := undecided_finding_error(run, disposition_ids.keys(), resolved)
        ) is not None:
            raise undecided

        disposition_id = disposition_ids[resolved.finding_key]
        self.unit.run(UPSERT_REVIEW_OUTCOME, outcome_params_of(disposition_id, resolved))

    def reopen(self, run: RunId, finding_keys: Collection[str]) -> None:
        if (run_id := self.run_id_of(run)) is None:
            return

        params = FindingKeysParams(review_run_id=run_id, finding_keys=list(finding_keys))
        self.unit.run(DELETE_REVIEW_OUTCOMES, params)
        self.unit.run(DELETE_REVIEW_DISPOSITIONS, params)

    def disposition_rows(self, run: RunId) -> list[ReviewDispositionRow]:
        if (run_id := self.run_id_of(run)) is None:
            return []

        params = RunLimitParams(review_run_id=run_id, limit=FINDINGS.fetched)
        rows = self.unit.all(REVIEW_DISPOSITIONS_OF_RUN, params)
        if (error := FINDINGS.error(rows, owner=f'run {run}')) is not None:
            raise error
        return rows

    def run_id_of(self, run: RunId) -> int | None:
        row = run_row_of(self.unit, self.repository_id, run)
        return None if row is None else row.id

    def started_run_id(self, run: RunId) -> int:
        if (run_id := self.run_id_of(run)) is None:
            raise RunNotFoundError(run=run)
        return run_id
