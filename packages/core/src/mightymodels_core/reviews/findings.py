"""Findings from persona reports: checked in full, redacted, merged by location, numbered.

Every reported severity is stored on the one ladder (a Blocker is High). An incoming finding
whose location overlaps a held one on the same file merges into it: the sources join, the
higher severity wins, and a gap of two levels or more records a conflict for the user to decide.
Findings go in and records come out; nothing here reads a repository, a clock or a file.
"""

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from mightymodels_core.primitives import redact, redact_within
from mightymodels_core.reviews.errors import (
    FieldRequiredError,
    LineBelowOneError,
    LocationShapeError,
    MalformedSourceError,
    ReversedRangeError,
    SourcesRequiredError,
    UnsupportedQualityError,
)
from mightymodels_core.reviews.records import Evidence, FindingRecord

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.primitives import RedactedText
    from mightymodels_core.reviews.records import (
        IncomingEvidence,
        IncomingFinding,
        StoredSeverity,
    )
    from mightymodels_core.schemas.reviews import FindingSeverity

type FindingProblem = (
    SourcesRequiredError
    | MalformedSourceError
    | LocationShapeError
    | LineBelowOneError
    | ReversedRangeError
    | UnsupportedQualityError
)

LOCATION = re.compile(r'^(?P<path>[^\s:]+):(?P<start>\d+)(?:-(?P<end>\d+))?$')
UNNUMBERED = 'F0'


def stored_severity(severity: FindingSeverity) -> StoredSeverity:
    return 'High' if severity == 'Blocker' else severity


@dataclass(slots=True, kw_only=True, frozen=True)
class FindingOptions:
    prose_limit: int = 4000
    conflict_gap: int = 2
    first_line: int = 1
    ladder: tuple[StoredSeverity, ...] = ('Critical', 'High', 'Medium', 'Low')
    source_prefixes: tuple[str, ...]

    @property
    def source_id(self) -> re.Pattern[str]:
        return re.compile(rf'^({"|".join(map(re.escape, self.source_prefixes))})-\d+$')

    @property
    def source_example(self) -> str:
        return ' or '.join(f'{prefix}-1' for prefix in self.source_prefixes)

    def rank(self, severity: StoredSeverity) -> int:
        return self.ladder.index(severity)


@dataclass(slots=True, kw_only=True, frozen=True)
class Span:
    path: str
    start: int
    end: int


def span_of(location: str) -> Span | None:
    match = LOCATION.match(location)
    if match is None:
        return None

    start = int(match['start'])
    end = start if match['end'] is None else int(match['end'])
    return Span(path=str(match['path']), start=start, end=end)


def overlaps(left: FindingRecord, right: FindingRecord) -> bool:
    left_span, right_span = span_of(left.location), span_of(right.location)
    if left_span is None or right_span is None:
        return False

    return (
        left_span.path == right_span.path
        and left_span.start <= right_span.end
        and right_span.start <= left_span.end
    )


def finding_number(key: str) -> int:
    return int(key.removeprefix('F'))


def number_of(finding: FindingRecord) -> int:
    return finding_number(finding.key)


@dataclass(slots=True, kw_only=True, frozen=True)
class FindingCheck:
    index: int
    finding: IncomingFinding
    options: FindingOptions

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.finding.sources)))

    def get_source_problem(self) -> SourcesRequiredError | MalformedSourceError | None:
        if not self.sources:
            return SourcesRequiredError(index=self.index)

        malformed = next(
            (item for item in self.sources if not self.options.source_id.match(item)), None
        )
        if malformed is not None:
            return MalformedSourceError(
                index=self.index, source=malformed, expected=self.options.source_example
            )

        return None

    def get_location_problem(self, location: str) -> FindingProblem | None:
        span = span_of(location)
        if span is None:
            return LocationShapeError(index=self.index, sources=self.sources)

        lowest = min(span.start, span.end)
        if lowest < self.options.first_line:
            return LineBelowOneError(index=self.index, sources=self.sources, line=lowest)

        if span.end < span.start:
            return ReversedRangeError(
                index=self.index, sources=self.sources, lines=(span.start, span.end)
            )

        return None

    def get_quality_problem(self, evidence: Evidence | None) -> UnsupportedQualityError | None:
        severity = stored_severity(self.finding.severity)
        if self.finding.kind != 'quality' or evidence is not None or severity == 'Low':
            return None

        return UnsupportedQualityError(index=self.index, sources=self.sources)

    def required_text(self, field: str, value: str) -> RedactedText:
        text = value.strip()
        if not text:
            raise FieldRequiredError(index=self.index, sources=self.sources, field=field)

        return redact_within(text, field, self.options.prose_limit)

    def evidence_of(self, evidence: IncomingEvidence | None) -> Evidence | None:
        if evidence is None:
            return None

        return Evidence(kind=evidence.kind, cite=self.required_text('evidence cite', evidence.cite))

    def checked_location(self) -> RedactedText:
        if problem := self.get_source_problem():
            raise problem

        location = self.required_text('location', self.finding.location)
        if problem := self.get_location_problem(location):
            raise problem

        return location

    def checked_evidence(self) -> Evidence | None:
        evidence = self.evidence_of(self.finding.evidence)
        if problem := self.get_quality_problem(evidence):
            raise problem

        return evidence

    def record(self) -> FindingRecord:
        location = self.checked_location()
        title = self.required_text('title', self.finding.title)
        fix = self.required_text('fix', self.finding.fix)
        verify = self.required_text('verify', self.finding.verify)
        evidence = self.checked_evidence()
        return FindingRecord(
            key=UNNUMBERED,
            sources=self.sources,
            severity=stored_severity(self.finding.severity),
            kind=self.finding.kind,
            security=self.finding.security,
            title=title,
            location=location,
            fix=fix,
            verify=verify,
            evidence=evidence,
            conflict=None,
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class FindingMerge:
    options: FindingOptions

    def conflict_between(self, keep: FindingRecord, other: FindingRecord) -> RedactedText | None:
        gap = abs(self.options.rank(keep.severity) - self.options.rank(other.severity))
        if gap < self.options.conflict_gap:
            return None

        return redact(
            f'{"/".join(other.sources)} rated {other.severity}, '
            f'{"/".join(keep.sources)} rated {keep.severity}: the user decides'
        )

    def merged(self, existing: FindingRecord, incoming: FindingRecord) -> FindingRecord:
        incoming_rank = self.options.rank(incoming.severity)
        incoming_is_higher = incoming_rank < self.options.rank(existing.severity)
        keep, other = (incoming, existing) if incoming_is_higher else (existing, incoming)
        gap_conflict = self.conflict_between(keep, other)
        return replace(
            keep,
            key=existing.key,
            sources=tuple(sorted(set(existing.sources) | set(incoming.sources))),
            security=existing.security or incoming.security,
            evidence=keep.evidence or other.evidence,
            conflict=gap_conflict or existing.conflict,
        )

    def placed(self, held: dict[str, FindingRecord], incoming: FindingRecord) -> FindingRecord:
        overlapped = next((old for old in held.values() if overlaps(old, incoming)), None)
        if overlapped is not None:
            return self.merged(overlapped, incoming)

        number = max(map(number_of, held.values()), default=0) + 1
        return replace(incoming, key=f'F{number}')

    def fold(
        self, held: Sequence[FindingRecord], incoming: Sequence[FindingRecord]
    ) -> list[FindingRecord]:
        working = {finding.key: finding for finding in held}
        changed: dict[str, FindingRecord] = {}
        for finding in incoming:
            result = self.placed(working, finding)
            working[result.key] = changed[result.key] = result

        return sorted(changed.values(), key=number_of)


def fold_findings(
    held: Sequence[FindingRecord],
    incoming: Sequence[IncomingFinding],
    options: FindingOptions,
) -> list[FindingRecord]:
    checks = [
        FindingCheck(index=index, finding=finding, options=options)
        for index, finding in enumerate(incoming)
    ]
    records = [check.record() for check in checks]
    return FindingMerge(options=options).fold(held, records)
