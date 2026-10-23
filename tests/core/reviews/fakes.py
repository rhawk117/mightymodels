"""The review repositories kept in memory."""

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from mightymodels_core.reviews.errors import RunExistsError, RunNotFoundError
from mightymodels_core.reviews.records import (
    FINDINGS,
    RUNS_LISTED,
    finding_write_error,
    undecided_finding_error,
    unknown_finding_error,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence

    from mightymodels_core.primitives import Latest, RunId, Slug
    from mightymodels_core.reviews.records import (
        DecidedFinding,
        FindingRecord,
        ResolvedFinding,
        ReviewRunRecord,
    )


def key_order(key: str) -> tuple[int, str]:
    return len(key), key


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewLedger:
    runs: dict[RunId, ReviewRunRecord] = field(default_factory=dict)
    findings: dict[RunId, dict[str, FindingRecord]] = field(default_factory=dict)
    dispositions: dict[RunId, dict[str, DecidedFinding]] = field(default_factory=dict)
    outcomes: dict[RunId, dict[str, ResolvedFinding]] = field(default_factory=dict)

    def finding_keys_of(self, run: RunId) -> list[str]:
        return list(self.findings.get(run, {}))

    def started(self, run: RunId) -> ReviewRunRecord | RunNotFoundError:
        return self.runs.get(run) or RunNotFoundError(run=run)


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeReviewRepository:
    ledger: ReviewLedger

    def run(self, run: RunId) -> ReviewRunRecord | None:
        return self.ledger.runs.get(run)

    def started_run(self, run: RunId) -> ReviewRunRecord:
        started = self.ledger.started(run)
        if isinstance(started, RunNotFoundError):
            raise started
        return started

    def latest_runs(self) -> Latest[ReviewRunRecord]:
        newest_first = sorted(self.ledger.runs.values(), key=lambda held: held.run_id, reverse=True)
        return RUNS_LISTED.latest(newest_first[: RUNS_LISTED.fetched])

    def latest_run(self, slug: Slug) -> ReviewRunRecord | None:
        held = [run for run in self.ledger.runs.values() if run.slug == slug]
        newest_first = sorted(held, key=lambda run: run.run_id, reverse=True)
        return next(iter(newest_first), None)

    def findings(self, run: RunId) -> list[FindingRecord]:
        held = self.ledger.findings.get(run, {})
        if (error := FINDINGS.error(held, owner=f'run {run}')) is not None:
            raise error
        return [held[key] for key in sorted(held, key=key_order)]

    def record_run(self, run: ReviewRunRecord) -> None:
        if run.run_id in self.ledger.runs:
            raise RunExistsError(run=run.run_id)

        self.ledger.runs[run.run_id] = run

    def record_models(self, run: RunId, models: Mapping[str, str | None]) -> None:
        started = self.ledger.started(run)
        if isinstance(started, RunNotFoundError):
            raise started
        self.ledger.runs[run] = replace(started, models=dict(models))

    def record_findings(self, run: RunId, findings: Sequence[FindingRecord]) -> None:
        started = self.ledger.started(run)
        if isinstance(started, RunNotFoundError):
            raise started

        held_keys = self.ledger.finding_keys_of(run)
        if (error := finding_write_error(run, held_keys, findings)) is not None:
            raise error

        held = self.ledger.findings.setdefault(run, {})
        held.update({finding.key: finding for finding in findings})


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeReviewDecisionRepository:
    ledger: ReviewLedger

    def dispositions(self, run: RunId) -> list[DecidedFinding]:
        held = self.ledger.dispositions.get(run, {})
        return [held[key] for key in sorted(held, key=key_order)]

    def outcomes(self, run: RunId) -> list[ResolvedFinding]:
        held = self.ledger.outcomes.get(run, {})
        return [held[key] for key in sorted(held, key=key_order)]

    def record_dispositions(self, run: RunId, decided: Sequence[DecidedFinding]) -> None:
        started = self.ledger.started(run)
        if isinstance(started, RunNotFoundError):
            raise started

        finding_keys = self.ledger.finding_keys_of(run)
        if (unknown := unknown_finding_error(run, finding_keys, decided)) is not None:
            raise unknown

        held = self.ledger.dispositions.setdefault(run, {})
        held.update({item.finding_key: item for item in decided})

    def record_outcome(self, run: RunId, resolved: ResolvedFinding) -> None:
        started = self.ledger.started(run)
        if isinstance(started, RunNotFoundError):
            raise started

        decided_keys = self.ledger.dispositions.get(run, {})
        if (undecided := undecided_finding_error(run, decided_keys, resolved)) is not None:
            raise undecided

        self.ledger.outcomes.setdefault(run, {})[resolved.finding_key] = resolved

    def reopen(self, run: RunId, finding_keys: Collection[str]) -> None:
        for key in finding_keys:
            self.ledger.dispositions.get(run, {}).pop(key, None)
            self.ledger.outcomes.get(run, {}).pop(key, None)
