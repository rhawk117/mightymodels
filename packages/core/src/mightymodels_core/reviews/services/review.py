"""The review service: start, override, add findings, gate, report and list.

It takes values and returns values. The caller passes HEAD and the parsed findings in, wraps a call
in its unit of work, makes the review folder and renders the results; the service never touches
git, a process or the filesystem. The text it writes goes to the similarity repository.
"""

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from mightymodels_core.primitives import create_routing_table
from mightymodels_core.reviews.errors import RunExistsError
from mightymodels_core.reviews.findings import fold_findings
from mightymodels_core.reviews.policy import (
    OverridePolicy,
    ReviewOptions,
    StartPolicy,
    create_gate_policy,
    reopened_keys,
)
from mightymodels_core.similarity.records import Written

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.primitives import Clock, RoutingTable, RunId
    from mightymodels_core.reviews.policy import GatePolicy, StartRequest, Verdict
    from mightymodels_core.reviews.records import FindingRecord, IncomingFinding, ReviewRunRecord
    from mightymodels_core.reviews.repository import ReviewDecisionRepository, ReviewRepository
    from mightymodels_core.similarity.records import Duplicate
    from mightymodels_core.similarity.repository import SimilarityRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class AddedFindings:
    received: int
    changed: tuple[FindingRecord, ...]
    reopened: tuple[str, ...]
    duplicates: tuple[Duplicate, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewReport:
    run: ReviewRunRecord
    findings: tuple[FindingRecord, ...]
    gate: GatePolicy
    verdict: Verdict


@dataclass(slots=True, kw_only=True, frozen=True)
class RunSummary:
    run: ReviewRunRecord
    finding_count: int
    verdict: Verdict


@dataclass(slots=True, kw_only=True, frozen=True)
class RunListing:
    runs: tuple[RunSummary, ...]
    older_left_out: bool


def written_finding(run: RunId, finding: FindingRecord) -> Written:
    return Written(kind='review-finding', reference=f'{run} {finding.key}', text=finding.title)


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewService:
    reviews: ReviewRepository
    decisions: ReviewDecisionRepository
    similarity: SimilarityRepository
    clock: Clock
    routing: RoutingTable = field(default_factory=create_routing_table)
    options: ReviewOptions = field(default_factory=ReviewOptions)

    def start(self, request: StartRequest, head: str | None) -> ReviewRunRecord:
        policy = StartPolicy(request=request, routing=self.routing, options=self.options)
        if problem := policy.get_start_problem():
            raise problem

        run = policy.record_for(head, self.clock.now())
        if self.reviews.run(run.run_id) is not None:
            raise RunExistsError(run=run.run_id)

        self.reviews.record_run(run)
        return run

    def override(self, run_id: RunId) -> ReviewRunRecord:
        started = self.reviews.started_run(run_id)
        policy = OverridePolicy(run=started, routing=self.routing)
        if problem := policy.get_override_problem():
            raise problem

        models = policy.overridden_models
        self.reviews.record_models(run_id, models)
        return replace(started, models=models)

    def add_findings(self, run_id: RunId, incoming: Sequence[IncomingFinding]) -> AddedFindings:
        self.reviews.started_run(run_id)
        recorded = self.reviews.findings(run_id)
        changed = fold_findings(recorded, incoming, self.options.findings)
        decided = {item.finding_key for item in self.decisions.dispositions(run_id)}
        reopened = reopened_keys(recorded, changed, decided)
        self.reviews.record_findings(run_id, changed)
        self.decisions.reopen(run_id, reopened)
        written = [written_finding(run_id, finding) for finding in changed]
        duplicates = self.similarity.record_all(written)
        return AddedFindings(
            received=len(incoming),
            changed=tuple(changed),
            reopened=tuple(reopened),
            duplicates=tuple(duplicates),
        )

    def gate_of(self, run: ReviewRunRecord) -> GatePolicy:
        dispositions = self.decisions.dispositions(run.run_id)
        outcomes = self.decisions.outcomes(run.run_id)
        return create_gate_policy(run, dispositions, outcomes)

    def gate(self, run_id: RunId) -> ReviewReport:
        run = self.reviews.started_run(run_id)
        gate = self.gate_of(run)
        findings = self.reviews.findings(run_id)
        return ReviewReport(
            run=run,
            findings=tuple(gate.ordered(findings)),
            gate=gate,
            verdict=gate.verdict_of(findings),
        )

    def report(self, run_id: RunId) -> ReviewReport:
        run = self.reviews.started_run(run_id)
        gate = self.gate_of(run)
        findings = self.reviews.findings(run_id)
        return ReviewReport(
            run=run, findings=tuple(findings), gate=gate, verdict=gate.verdict_of(findings)
        )

    def summary_of(self, run: ReviewRunRecord) -> RunSummary:
        findings = self.reviews.findings(run.run_id)
        verdict = self.gate_of(run).verdict_of(findings)
        return RunSummary(run=run, finding_count=len(findings), verdict=verdict)

    def listing(self) -> RunListing:
        latest = self.reviews.latest_runs()
        runs = tuple(map(self.summary_of, latest.rows))
        return RunListing(runs=runs, older_left_out=latest.older_left_out)
