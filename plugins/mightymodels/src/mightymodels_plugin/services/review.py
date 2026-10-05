"""The `review` tool's service: a review run, its findings, the user's decisions and outcomes.

A run records its scope, depth, persona weights and reviewer models at HEAD. `add` reads a
persona's report from the run directory and records its findings; the reports and the metrics
file are the only files a run keeps, and `report` returns its text for the agent to write.
Every write is validated in full before anything is stored, so a rejected batch stores nothing.
Only the user's dispositions move a finding to remediation.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from types import MappingProxyType

from sqlalchemy import select

from mightymodels_plugin.db.checkout import Checkout
from mightymodels_plugin.db.tables import (
    ReviewDispositionRow,
    ReviewFindingRow,
    ReviewOutcomeRow,
    ReviewRunRow,
    TicketRow,
)
from mightymodels_plugin.models.review import (
    Decision,
    DisposePayload,
    Disposition,
    Emphasis,
    Evidence,
    EvidenceKind,
    Finding,
    FindingInput,
    Persona,
    ResolvePayload,
    Result,
    ReviewScope,
    ReviewView,
    Severity,
    Shape,
    StartPayload,
)
from mightymodels_plugin.models.run_id import RunId
from mightymodels_plugin.models.slug import Slug
from mightymodels_plugin.routing import Depth, Worker, reviewer_model
from mightymodels_plugin.services.clock import now
from mightymodels_plugin.services.redact import redact
from mightymodels_plugin.services.review_errors import (
    BaseRequiredError,
    CommitRequiredError,
    NotChosenError,
    PersonaChoiceError,
    ReasonRequiredError,
    ReportMissingError,
    ResultReasonError,
    RunExistsError,
    RunNotFoundError,
    SlugRequiredError,
    UnknownFindingError,
    WeightRangeError,
    WeightsMissingError,
    WeightSumError,
)
from mightymodels_plugin.services.review_findings import finding_number, fold, normalized, number_of
from mightymodels_plugin.services.review_render import (
    Standing,
    gate_text,
    report_text,
    verdict_of,
)
from mightymodels_plugin.services.review_report import parse_report
from mightymodels_plugin.workspace import revision_error

STANDARD_THRESHOLD = 0.25
WEIGHT_TOLERANCE = 0.001
NEEDS_REASON = frozenset({Decision.ACCEPT_RISK, Decision.DISMISS})
PRESETS: Mapping[Emphasis, Mapping[Persona, float]] = MappingProxyType(
    {
        Emphasis.RELEASE: {Persona.MERGE_VADER: 0.7, Persona.UNCLE_BOB: 0.3},
        Emphasis.MAINTAINABILITY: {Persona.MERGE_VADER: 0.3, Persona.UNCLE_BOB: 0.7},
        Emphasis.BALANCED: {Persona.MERGE_VADER: 0.5, Persona.UNCLE_BOB: 0.5},
    }
)
REVIEWERS: Mapping[Persona, Worker] = MappingProxyType(
    {
        Persona.MERGE_VADER: Worker.MERGE_VADER_REVIEWER,
        Persona.UNCLE_BOB: Worker.UNCLE_BOB_REVIEWER,
    }
)


def run_row(checkout: Checkout, run: RunId) -> ReviewRunRow:
    row = checkout.session.get(ReviewRunRow, run.root)
    if row is None:
        raise RunNotFoundError(run)
    return row


def slug_of(row: ReviewRunRow) -> Slug | None:
    return Slug(row.slug) if row.slug else None


def finding_of(row: ReviewFindingRow) -> Finding:
    evidence = (
        Evidence(kind=EvidenceKind(row.evidence_kind), cite=row.evidence_cite or '')
        if row.evidence_kind
        else None
    )
    return Finding(
        id=row.finding_id,
        sources=tuple(row.sources),
        severity=Severity(row.severity),
        kind=row.kind,
        security=row.security,
        title=row.title,
        location=row.location,
        fix=row.fix,
        verify=row.verify,
        evidence=evidence,
        conflict=row.conflict,
    )


def row_of_finding(run: RunId, finding: Finding) -> ReviewFindingRow:
    return ReviewFindingRow(
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
        evidence_kind=finding.evidence.kind if finding.evidence else None,
        evidence_cite=finding.evidence.cite if finding.evidence else None,
        conflict=finding.conflict,
    )


def findings_of(checkout: Checkout, run: RunId) -> dict[str, Finding]:
    query = select(ReviewFindingRow).where(ReviewFindingRow.run_id == run.root)
    findings = [finding_of(row) for row in checkout.session.scalars(query)]
    return {finding.id: finding for finding in sorted(findings, key=number_of)}


def standing_of(checkout: Checkout, row: ReviewRunRow) -> Standing:
    dispositions = select(ReviewDispositionRow).where(ReviewDispositionRow.run_id == row.run_id)
    outcomes = select(ReviewOutcomeRow).where(ReviewOutcomeRow.run_id == row.run_id)
    return Standing(
        run=row,
        dispositions={d.finding_id: d for d in checkout.session.scalars(dispositions)},
        outcomes={o.finding_id: o for o in checkout.session.scalars(outcomes)},
    )


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
    if chosen:
        return [chosen]
    heaviest = max(weights.values())
    leaders = [persona for persona in Persona if weights[persona] == heaviest]
    if len(leaders) > 1:
        raise PersonaChoiceError
    return leaders


def reviewed_base(payload: StartPayload) -> str | None:
    if payload.scope in {ReviewScope.BRANCH, ReviewScope.TICKET} and payload.base is None:
        raise BaseRequiredError(payload.scope)
    if payload.scope is ReviewScope.TICKET and payload.slug is None:
        raise SlugRequiredError
    if payload.base is not None and (error := revision_error(payload.base)) is not None:
        raise error
    return payload.base


def ticket_models(checkout: Checkout, slug: Slug | None) -> Mapping[str, str | None]:
    ticket = checkout.session.get(TicketRow, slug.root) if slug else None
    if ticket is None:
        return dict[str, str | None]()
    return ticket.models


def start(checkout: Checkout, payload: StartPayload, *, started: datetime) -> ReviewView:
    base = reviewed_base(payload)
    weights = weights_for(payload)
    personas = personas_for(payload.depth, weights, payload.persona)
    pinned = ticket_models(checkout, payload.slug)
    run = RunId(started.strftime('%Y%m%d-%H%M%S'))
    if checkout.session.get(ReviewRunRow, run.root):
        raise RunExistsError(run)
    models = {
        REVIEWERS[persona].value: reviewer_model(REVIEWERS[persona], payload.depth, pinned)
        for persona in personas
    }
    checkout.session.add(
        ReviewRunRow(
            run_id=run.root,
            slug=payload.slug.root if payload.slug else None,
            scope=payload.scope,
            base=base,
            head=checkout.workspace.git.resolve_head(),
            depth=payload.depth,
            emphasis=payload.emphasis,
            weights={persona.value: weight for persona, weight in weights.items()},
            personas=[persona.value for persona in personas],
            models=models,
            created_at=started.isoformat(timespec='seconds'),
        )
    )
    directory = checkout.workspace.review_directory(payload.slug, run)
    directory.mkdir(parents=True, exist_ok=True)
    listed = ', '.join(f'{name} on {model}' for name, model in models.items())
    relative = checkout.workspace.relative_to_root(directory)
    text = f'run {run} at {relative}\n{payload.depth} review: {listed}\n'
    return ReviewView(text=text, run_id=run.root)


def add(checkout: Checkout, run: RunId, persona: Persona) -> ReviewView:
    row = run_row(checkout, run)
    report = checkout.workspace.persona_report(slug_of(row), run, persona=persona)
    if report.is_symlink() or not report.is_file():
        raise ReportMissingError(persona, checkout.workspace.relative_to_root(report))
    batch = parse_report(report.read_text(encoding='utf-8'), persona)
    return add_findings(checkout, run, batch)


def add_findings(checkout: Checkout, run: RunId, batch: Sequence[FindingInput]) -> ReviewView:
    row = run_row(checkout, run)
    incoming = [normalized(entry, index) for index, entry in enumerate(batch)]
    changed = fold(findings_of(checkout, run), incoming)
    for finding in changed:
        checkout.session.merge(row_of_finding(run, finding))
    ids = ', '.join(finding.id for finding in changed) or 'none'
    text = f'{len(incoming)} findings in, {len(changed)} recorded: {ids}\n'
    return ReviewView(text=text, run_id=row.run_id)


def gate(checkout: Checkout, run: RunId) -> ReviewView:
    row = run_row(checkout, run)
    findings = list(findings_of(checkout, run).values())
    standing = standing_of(checkout, row)
    return ReviewView(text=gate_text(findings, standing), run_id=row.run_id)


def disposition_row(
    run: RunId, finding_id: str, entry: Disposition, *, by: str
) -> ReviewDispositionRow:
    if entry.decision in NEEDS_REASON and not entry.reason.strip():
        raise ReasonRequiredError(finding_id, entry.decision)
    return ReviewDispositionRow(
        run_id=run.root,
        finding_id=finding_id,
        decision=entry.decision,
        reason=redact(entry.reason.strip()),
        by=by,
        at=now(),
    )


def dispose(checkout: Checkout, run: RunId, payload: DisposePayload) -> ReviewView:
    row = run_row(checkout, run)
    findings = findings_of(checkout, run)
    unknown = next(
        (finding_id for finding_id in payload.decisions if finding_id not in findings), None
    )
    if unknown:
        raise UnknownFindingError(unknown)
    recorded = [
        disposition_row(run, finding_id, entry, by=payload.by)
        for finding_id, entry in payload.decisions.items()
    ]
    for disposition in recorded:
        checkout.session.merge(disposition)
    decided = set(standing_of(checkout, row).dispositions) | set(payload.decisions)
    undecided = sorted(set(findings) - decided, key=finding_number)
    tail = f'; undecided: {", ".join(undecided)}' if undecided else ''
    return ReviewView(text=f'{len(recorded)} dispositions recorded{tail}\n', run_id=row.run_id)


def resolve(checkout: Checkout, run: RunId, payload: ResolvePayload) -> ReviewView:
    row = run_row(checkout, run)
    finding_id = payload.finding
    if finding_id not in findings_of(checkout, run):
        raise UnknownFindingError(finding_id)
    chosen = checkout.session.get(ReviewDispositionRow, (run.root, finding_id))
    if chosen is None or chosen.decision != Decision.FIX:
        raise NotChosenError(finding_id)
    commit = payload.commit
    if commit is not None and (error := revision_error(commit)) is not None:
        raise error
    if payload.result is Result.FIXED and commit is None:
        raise CommitRequiredError(finding_id)
    if payload.result is not Result.FIXED and not payload.reason:
        raise ResultReasonError(finding_id, payload.result)
    checkout.session.merge(
        ReviewOutcomeRow(
            run_id=run.root,
            finding_id=finding_id,
            result=payload.result,
            commit=commit or '',
            reason=redact(payload.reason or ''),
            at=now(),
        )
    )
    return ReviewView(text=f'{finding_id} {payload.result}\n', run_id=row.run_id)


def report(checkout: Checkout, run: RunId, shape: Shape) -> ReviewView:
    row = run_row(checkout, run)
    findings = list(findings_of(checkout, run).values())
    standing = standing_of(checkout, row)
    text = report_text(shape, findings, standing)
    return ReviewView(text=text, run_id=row.run_id, verdict=verdict_of(findings, standing))


def listing(checkout: Checkout) -> ReviewView:
    rows = checkout.session.scalars(select(ReviewRunRow).order_by(ReviewRunRow.run_id))
    lines = []
    for row in rows:
        findings = list(findings_of(checkout, RunId(row.run_id)).values())
        verdict = verdict_of(findings, standing_of(checkout, row))
        lines.append(
            f'{row.run_id}\t{row.slug or "-"}\t{row.depth}\t{len(findings)} findings\t{verdict}\n'
        )
    return ReviewView(text=''.join(lines) or 'no review runs\n')
