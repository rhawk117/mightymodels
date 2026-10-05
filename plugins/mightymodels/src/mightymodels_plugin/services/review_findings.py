"""Findings from persona reports: validated in full, redacted, merged by location, numbered.

Every reported severity is stored on the one ladder (a Blocker is High). An incoming finding
whose location overlaps a recorded one on the same file merges into it: the sources join, the
higher severity wins, and a gap of two levels or more records a conflict for the user to decide.
"""

import re
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from mightymodels_plugin.models.review import (
    Evidence,
    Finding,
    FindingInput,
    Kind,
    ReportedSeverity,
    Severity,
)
from mightymodels_plugin.services.redact import redact
from mightymodels_plugin.services.review_errors import (
    FieldRequiredError,
    LocationShapeError,
    UnsupportedQualityError,
)

LOCATION = re.compile(r'^(?P<path>[^\s:]+):(?P<start>\d+)(?:-(?P<end>\d+))?$')
UNNUMBERED = 'F0'
CONFLICT_GAP = 2

type Span = tuple[str, int, int]

RANK: Mapping[Severity, int] = MappingProxyType(
    {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
)
STORED_SEVERITY: Mapping[ReportedSeverity, Severity] = MappingProxyType(
    {
        ReportedSeverity.BLOCKER: Severity.HIGH,
        ReportedSeverity.CRITICAL: Severity.CRITICAL,
        ReportedSeverity.HIGH: Severity.HIGH,
        ReportedSeverity.MEDIUM: Severity.MEDIUM,
        ReportedSeverity.LOW: Severity.LOW,
    }
)


def finding_number(finding_id: str) -> int:
    return int(finding_id[1:])


def number_of(finding: Finding) -> int:
    return finding_number(finding.id)


def span_of(location: str) -> Span:
    match = LOCATION.match(location)
    if match is None:
        return location, 0, 0
    path = str(match['path'])
    start = int(match['start'])
    return path, start, int(match['end'] or start)


def required(index: int, sources: Sequence[str], field: str, *, value: str) -> str:
    text = value.strip()
    if not text:
        raise FieldRequiredError(index, sources, field)
    return redact(text)


def evidence_of(index: int, sources: Sequence[str], evidence: Evidence | None) -> Evidence | None:
    if evidence is None:
        return None
    return Evidence(
        kind=evidence.kind, cite=required(index, sources, 'evidence cite', value=evidence.cite)
    )


def normalized(entry: FindingInput, index: int) -> Finding:
    sources = sorted(set(entry.sources))
    location = required(index, sources, 'location', value=entry.location)
    if not LOCATION.match(location):
        raise LocationShapeError(index, sources)
    severity = STORED_SEVERITY[entry.severity]
    finding = Finding(
        id=UNNUMBERED,
        sources=tuple(sources),
        severity=severity,
        kind=entry.kind,
        security=entry.security,
        title=required(index, sources, 'title', value=entry.title),
        location=location,
        fix=required(index, sources, 'fix', value=entry.fix),
        verify=required(index, sources, 'verify', value=entry.verify),
        evidence=evidence_of(index, sources, entry.evidence),
    )
    supported = finding.evidence is not None or severity is Severity.LOW
    if finding.kind is Kind.QUALITY and not supported:
        raise UnsupportedQualityError(index, sources)
    return finding


def overlaps(left: Finding, right: Finding) -> bool:
    left_path, left_start, left_end = span_of(left.location)
    right_path, right_start, right_end = span_of(right.location)
    return left_path == right_path and left_start <= right_end and right_start <= left_end


def conflict_between(keep: Finding, other: Finding, current: str | None) -> str | None:
    gap = abs(RANK[keep.severity] - RANK[other.severity])
    if gap < CONFLICT_GAP:
        return current
    return (
        f'{"/".join(other.sources)} rated {other.severity}, '
        f'{"/".join(keep.sources)} rated {keep.severity}: the user decides'
    )


def merged(existing: Finding, incoming: Finding) -> Finding:
    keep, other = (
        (incoming, existing)
        if RANK[incoming.severity] < RANK[existing.severity]
        else (existing, incoming)
    )
    return Finding(
        id=existing.id,
        sources=tuple(sorted(set(existing.sources) | set(incoming.sources))),
        severity=keep.severity,
        kind=keep.kind,
        security=existing.security or incoming.security,
        title=keep.title,
        location=keep.location,
        fix=keep.fix,
        verify=keep.verify,
        evidence=keep.evidence or other.evidence,
        conflict=conflict_between(keep, other, existing.conflict),
    )


def fold(current: Mapping[str, Finding], incoming: Sequence[Finding]) -> list[Finding]:
    working = dict(current)
    changed: dict[str, Finding] = {}
    next_number = max((number_of(finding) for finding in working.values()), default=0) + 1
    for finding in incoming:
        match = next((old for old in working.values() if overlaps(old, finding)), None)
        if match is None:
            result = finding.model_copy(update={'id': f'F{next_number}'})
            next_number += 1
        else:
            result = merged(match, finding)
        working[result.id] = changed[result.id] = result
    return sorted(changed.values(), key=number_of)
