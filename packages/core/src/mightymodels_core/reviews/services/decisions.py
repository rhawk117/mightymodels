"""The review decision service: dispose findings, resolve a fix outcome and read the latest review.

It takes values and returns values. The caller passes the decisions, the commit to check and who
decided in, wraps a call in its unit of work and words the response; the service never touches git,
a process or the filesystem.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.reviews.policy import DecisionOptions, DisposePolicy, ResolvePolicy

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mightymodels_core.primitives import Clock, RunId, Slug
    from mightymodels_core.reviews.policy import IncomingDisposition, ResolveRequest
    from mightymodels_core.reviews.records import (
        DecidedFinding,
        FindingRecord,
        ResolvedFinding,
        ReviewRunRecord,
    )
    from mightymodels_core.reviews.repository import ReviewDecisionRepository, ReviewRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class Disposed:
    recorded: int
    undecided: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class LatestReview:
    run: ReviewRunRecord
    findings: tuple[FindingRecord, ...]
    dispositions: Mapping[str, DecidedFinding]
    outcomes: Mapping[str, ResolvedFinding]
    options: DecisionOptions = field(default_factory=DecisionOptions)

    @property
    def decided(self) -> tuple[DecidedFinding, ...]:
        held = (self.dispositions.get(finding.key) for finding in self.findings)
        return tuple(disposition for disposition in held if disposition is not None)

    @property
    def undecided(self) -> tuple[str, ...]:
        return tuple(
            finding.key for finding in self.findings if finding.key not in self.dispositions
        )

    @property
    def open_remediation(self) -> tuple[str, ...]:
        chosen = self.options.chosen_decision
        return tuple(
            disposition.finding_key
            for disposition in self.decided
            if disposition.decision == chosen and not self.is_fixed(disposition.finding_key)
        )

    def is_fixed(self, finding_key: str) -> bool:
        outcome = self.outcomes.get(finding_key)
        return outcome is not None and outcome.result == self.options.fixed_result


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewDecisionService:
    reviews: ReviewRepository
    decisions: ReviewDecisionRepository
    clock: Clock
    options: DecisionOptions = field(default_factory=DecisionOptions)

    def dispose(
        self, run_id: RunId, decisions: Mapping[str, IncomingDisposition], by: str
    ) -> Disposed:
        self.reviews.started_run(run_id)
        finding_keys = [finding.key for finding in self.reviews.findings(run_id)]
        policy = DisposePolicy(
            run=run_id, finding_keys=finding_keys, decisions=decisions, options=self.options
        )
        if problem := policy.get_dispose_problem():
            raise problem

        decided = policy.decided_records(by, self.clock.now())
        self.decisions.record_dispositions(run_id, decided)
        held = {item.finding_key for item in self.decisions.dispositions(run_id)}
        undecided = tuple(key for key in finding_keys if key not in held)
        return Disposed(recorded=len(decided), undecided=undecided)

    def resolve(self, run_id: RunId, request: ResolveRequest) -> ResolvedFinding:
        self.reviews.started_run(run_id)
        finding_keys = [finding.key for finding in self.reviews.findings(run_id)]
        held = {item.finding_key: item for item in self.decisions.dispositions(run_id)}
        policy = ResolvePolicy(
            run=run_id,
            request=request,
            finding_keys=finding_keys,
            chosen=held.get(request.finding_key),
            options=self.options,
        )
        if problem := policy.get_resolve_problem():
            raise problem

        resolved = policy.resolved_at(self.clock.now())
        self.decisions.record_outcome(run_id, resolved)
        return resolved

    def latest_review(self, slug: Slug) -> LatestReview | None:
        run = self.reviews.latest_run(slug)
        if run is None:
            return None

        return LatestReview(
            run=run,
            findings=tuple(self.reviews.findings(run.run_id)),
            dispositions={
                item.finding_key: item for item in self.decisions.dispositions(run.run_id)
            },
            outcomes={item.finding_key: item for item in self.decisions.outcomes(run.run_id)},
            options=self.options,
        )
