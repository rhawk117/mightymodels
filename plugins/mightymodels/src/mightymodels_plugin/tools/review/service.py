"""The review service: a review run, its findings, the user's decisions and the fix outcomes.

A run records its scope, depth, persona weights and reviewer models at HEAD. `add` reads a
persona's report from the run directory and records its findings; the reports and the metrics
file are the only files a run keeps, and `report` returns its text for the agent to write.
Every write is validated in full before anything is stored, so a rejected batch stores nothing.
Only the user's dispositions move a finding to remediation.

The service is built once by whoever owns the workspace and the database, the server in its
lifespan, and holds both. Each action opens one transaction through `review_transaction`, which
hands it the review repository and, on that repository, the ticket's row. Rows are read inside
that transaction and mapped to values there, so what the rendering takes and what an action
returns holds no row. Everything above the class reads no service state.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from mightymodels_plugin.clock import now
from mightymodels_plugin.database import Database
from mightymodels_plugin.errors import StateError
from mightymodels_plugin.redaction import redact
from mightymodels_plugin.routing import Depth, Worker, reviewer_model
from mightymodels_plugin.run_id import RunId
from mightymodels_plugin.slug import Slug
from mightymodels_plugin.tools.review.errors import (
    BaseRequiredError,
    CommitRequiredError,
    NotChosenError,
    PersonaChoiceError,
    ReasonRequiredError,
    ReportMissingError,
    ResultReasonError,
    RunExistsError,
    SlugRequiredError,
    UnknownFindingError,
    WeightRangeError,
    WeightsMissingError,
    WeightSumError,
)
from mightymodels_plugin.tools.review.finding_merge import (
    finding_number,
    fold,
    normalized,
    number_of,
)
from mightymodels_plugin.tools.review.rendering import Standing, gate_text, report_text, verdict_of
from mightymodels_plugin.tools.review.report_parser import parse_report
from mightymodels_plugin.tools.review.repository import (
    DecidedFinding,
    ResolvedFinding,
    ReviewRepository,
    review_transaction,
)
from mightymodels_plugin.tools.review.schema import (
    Decision,
    DisposePayload,
    Disposition,
    Emphasis,
    Evidence,
    EvidenceKind,
    Finding,
    FindingInput,
    Kind,
    Persona,
    ResolvePayload,
    Result,
    ReviewRun,
    ReviewScope,
    ReviewView,
    Severity,
    Shape,
    StartPayload,
)
from mightymodels_plugin.tools.review.tables import ReviewFindingRow, ReviewRunRow
from mightymodels_plugin.workspace import Workspace, revision_error

STANDARD_THRESHOLD = 0.25
WEIGHT_TOLERANCE = 0.001
RUN_ID_FORMAT = '%Y%m%d-%H%M%S'
NEEDS_REASON = frozenset({Decision.ACCEPT_RISK, Decision.DISMISS})
NEEDS_BASE = frozenset({ReviewScope.BRANCH, ReviewScope.TICKET})
PRESETS: Mapping[Emphasis, Mapping[Persona, float]] = MappingProxyType(
    {
        Emphasis.RELEASE: MappingProxyType({Persona.MERGE_VADER: 0.7, Persona.UNCLE_BOB: 0.3}),
        Emphasis.MAINTAINABILITY: MappingProxyType(
            {Persona.MERGE_VADER: 0.3, Persona.UNCLE_BOB: 0.7}
        ),
        Emphasis.BALANCED: MappingProxyType({Persona.MERGE_VADER: 0.5, Persona.UNCLE_BOB: 0.5}),
    }
)
REVIEWERS: Mapping[Persona, Worker] = MappingProxyType(
    {
        Persona.MERGE_VADER: Worker.MERGE_VADER_REVIEWER,
        Persona.UNCLE_BOB: Worker.UNCLE_BOB_REVIEWER,
    }
)


def run_of(row: ReviewRunRow) -> ReviewRun:
    return ReviewRun(
        run_id=RunId(row.run_id),
        slug=None if row.slug is None else Slug(row.slug),
        scope=ReviewScope(row.scope),
        base=row.base,
        head=row.head,
        depth=Depth(row.depth),
        emphasis=Emphasis(row.emphasis),
        weights={Persona(persona): weight for persona, weight in row.weights.items()},
        personas=tuple(map(Persona, row.personas)),
        models=dict(row.models),
        created_at=row.created_at,
    )


def evidence_of(row: ReviewFindingRow) -> Evidence | None:
    if row.evidence_kind is None:
        return None
    cite = '' if row.evidence_cite is None else row.evidence_cite
    return Evidence(kind=EvidenceKind(row.evidence_kind), cite=cite)


def finding_of(row: ReviewFindingRow) -> Finding:
    return Finding(
        id=row.finding_id,
        sources=tuple(row.sources),
        severity=Severity(row.severity),
        kind=Kind(row.kind),
        security=row.security,
        title=row.title,
        location=row.location,
        fix=row.fix,
        verify=row.verify,
        evidence=evidence_of(row),
        conflict=row.conflict,
    )


def findings_of(repository: ReviewRepository, run: RunId) -> dict[str, Finding]:
    findings = sorted(map(finding_of, repository.finding_rows(run)), key=number_of)
    return {finding.id: finding for finding in findings}


def dispositions_of(repository: ReviewRepository, run: RunId) -> dict[str, Disposition]:
    return {
        row.finding_id: Disposition(decision=Decision(row.decision), reason=row.reason)
        for row in repository.disposition_rows(run)
    }


def standing_of(repository: ReviewRepository, run: ReviewRun) -> Standing:
    return Standing(
        run=run,
        dispositions=dispositions_of(repository, run.run_id),
        results={row.finding_id: Result(row.result) for row in repository.outcome_rows(run.run_id)},
    )


def target_error(payload: StartPayload) -> StateError | None:
    if payload.scope in NEEDS_BASE and payload.base is None:
        return BaseRequiredError(payload.scope)
    if payload.scope is ReviewScope.TICKET and payload.slug is None:
        return SlugRequiredError()
    if payload.base is None:
        return None
    return revision_error(payload.base)


def weights_for(payload: StartPayload) -> Mapping[Persona, float]:
    if payload.emphasis is not Emphasis.CUSTOM:
        return PRESETS[payload.emphasis]
    weights = payload.weights
    if weights is None:
        raise WeightsMissingError
    if set(weights) != set(Persona) or not all(0 <= value <= 1 for value in weights.values()):
        raise WeightRangeError
    if abs(sum(weights.values()) - 1) > WEIGHT_TOLERANCE:
        raise WeightSumError
    return weights


def personas_for(
    depth: Depth, weights: Mapping[Persona, float], chosen: Persona | None
) -> list[Persona]:
    if depth is Depth.DEEP:
        return list(Persona)
    if depth is Depth.STANDARD:
        return [persona for persona in Persona if weights[persona] >= STANDARD_THRESHOLD]
    if chosen is not None:
        return [chosen]
    heaviest = max(weights.values())
    leaders = [persona for persona in Persona if weights[persona] == heaviest]
    if len(leaders) > 1:
        raise PersonaChoiceError
    return leaders


def pinned_models(repository: ReviewRepository, slug: Slug | None) -> Mapping[str, str | None]:
    ticket = None if slug is None else repository.tickets.row(slug)
    if ticket is None:
        return dict[str, str | None]()
    return ticket.models


def reviewer_models(
    personas: Sequence[Persona], depth: Depth, pinned: Mapping[str, str | None]
) -> dict[str, str]:
    return {
        REVIEWERS[persona].value: reviewer_model(REVIEWERS[persona], depth, pinned)
        for persona in personas
    }


def started_text(started_run: ReviewRun, relative: str) -> str:
    listed = ', '.join(f'{name} on {model}' for name, model in started_run.models.items())
    return f'run {started_run.run_id} at {relative}\n{started_run.depth} review: {listed}\n'


def record_batch(
    repository: ReviewRepository, run: RunId, batch: Sequence[FindingInput]
) -> ReviewView:
    incoming = [normalized(entry, index) for index, entry in enumerate(batch)]
    changed = fold(findings_of(repository, run), incoming)
    repository.record_findings(run, changed)
    ids = ', '.join(finding.id for finding in changed) or 'none'
    text = f'{len(incoming)} findings in, {len(changed)} recorded: {ids}\n'
    return ReviewView(text=text, run_id=run.root)


def decided_finding(finding_id: str, entry: Disposition, *, by: str) -> DecidedFinding:
    if entry.decision in NEEDS_REASON and not entry.reason.strip():
        raise ReasonRequiredError(finding_id, entry.decision)
    return DecidedFinding(
        finding_id=finding_id,
        decision=entry.decision,
        reason=redact(entry.reason.strip()),
        by=redact(by),
        at=now(),
    )


def resolution_error(payload: ResolvePayload) -> StateError | None:
    if payload.commit is not None and (error := revision_error(payload.commit)) is not None:
        return error
    if payload.result is Result.FIXED and payload.commit is None:
        return CommitRequiredError(payload.finding)
    if payload.result is not Result.FIXED and not payload.reason:
        return ResultReasonError(payload.finding, payload.result)
    return None


def listing_line(repository: ReviewRepository, run: ReviewRun) -> str:
    findings = list(findings_of(repository, run.run_id).values())
    verdict = verdict_of(findings, standing_of(repository, run))
    slug = '-' if run.slug is None else run.slug
    return f'{run.run_id}\t{slug}\t{run.depth}\t{len(findings)} findings\t{verdict}\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewService:
    workspace: Workspace
    database: Database

    def start(self, payload: StartPayload, *, started: datetime) -> ReviewView:
        if (error := target_error(payload)) is not None:
            raise error
        weights = weights_for(payload)
        personas = personas_for(payload.depth, weights, payload.persona)
        run = RunId(started.strftime(RUN_ID_FORMAT))
        with review_transaction(self.database) as repository:
            pinned = pinned_models(repository, payload.slug)
            if repository.run_row(run) is not None:
                raise RunExistsError(run)
            started_run = ReviewRun(
                run_id=run,
                slug=payload.slug,
                scope=payload.scope,
                base=payload.base,
                head=self.workspace.git.resolve_head(),
                depth=payload.depth,
                emphasis=payload.emphasis,
                weights=weights,
                personas=tuple(personas),
                models=reviewer_models(personas, payload.depth, pinned),
                created_at=started.isoformat(timespec='seconds'),
            )
            repository.record_run(started_run)
            directory = self.workspace.review_directory(payload.slug, run)
            directory.mkdir(parents=True, exist_ok=True)
        text = started_text(started_run, self.workspace.relative_to_root(directory))
        return ReviewView(text=text, run_id=run.root)

    def add(self, run: RunId, persona: Persona) -> ReviewView:
        with review_transaction(self.database) as repository:
            started_run = run_of(repository.started_run_row(run))
            report = self.workspace.persona_report(started_run.slug, run, persona=persona)
            if report.file is None or not report.file.is_file():
                raise ReportMissingError(persona, report.relative)
            batch = parse_report(report.file.read_text(encoding='utf-8'), persona)
            return record_batch(repository, run, batch)

    def add_findings(self, run: RunId, batch: Sequence[FindingInput]) -> ReviewView:
        with review_transaction(self.database) as repository:
            repository.started_run_row(run)
            return record_batch(repository, run, batch)

    def gate(self, run: RunId) -> ReviewView:
        with review_transaction(self.database) as repository:
            started_run = run_of(repository.started_run_row(run))
            findings = list(findings_of(repository, run).values())
            standing = standing_of(repository, started_run)
        return ReviewView(text=gate_text(findings, standing), run_id=run.root)

    def dispose(self, run: RunId, payload: DisposePayload) -> ReviewView:
        with review_transaction(self.database) as repository:
            repository.started_run_row(run)
            findings = findings_of(repository, run)
            unknown = next(
                (finding_id for finding_id in payload.decisions if finding_id not in findings), None
            )
            if unknown is not None:
                raise UnknownFindingError(unknown)
            decided = [
                decided_finding(finding_id, entry, by=payload.by)
                for finding_id, entry in payload.decisions.items()
            ]
            repository.record_dispositions(run, decided)
            disposed = set(dispositions_of(repository, run)) | set(payload.decisions)
        undecided = sorted(set(findings) - disposed, key=finding_number)
        tail = f'; undecided: {", ".join(undecided)}' if undecided else ''
        return ReviewView(text=f'{len(decided)} dispositions recorded{tail}\n', run_id=run.root)

    def resolve(self, run: RunId, payload: ResolvePayload) -> ReviewView:
        with review_transaction(self.database) as repository:
            repository.started_run_row(run)
            if payload.finding not in findings_of(repository, run):
                raise UnknownFindingError(payload.finding)
            chosen = dispositions_of(repository, run).get(payload.finding)
            if chosen is None or chosen.decision is not Decision.FIX:
                raise NotChosenError(payload.finding)
            if (error := resolution_error(payload)) is not None:
                raise error
            repository.record_outcome(
                run,
                ResolvedFinding(
                    finding_id=payload.finding,
                    result=payload.result,
                    commit='' if payload.commit is None else payload.commit,
                    reason='' if payload.reason is None else redact(payload.reason),
                    at=now(),
                ),
            )
        return ReviewView(text=f'{payload.finding} {payload.result}\n', run_id=run.root)

    def report(self, run: RunId, shape: Shape) -> ReviewView:
        with review_transaction(self.database) as repository:
            started_run = run_of(repository.started_run_row(run))
            findings = list(findings_of(repository, run).values())
            standing = standing_of(repository, started_run)
        text = report_text(shape, findings, standing)
        return ReviewView(text=text, run_id=run.root, verdict=verdict_of(findings, standing))

    def listing(self) -> ReviewView:
        with review_transaction(self.database) as repository:
            lines = [listing_line(repository, run_of(row)) for row in repository.run_rows()]
        return ReviewView(text=''.join(lines) or 'no review runs\n')
