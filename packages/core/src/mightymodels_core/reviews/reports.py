"""Reads a persona's Markdown report into the findings the review service records.

The report is the reviewer's output and is untrusted, so only its `## Findings` section is
read and every block must fit the templates: a severity heading, then one block per finding.
The kind of a finding follows from who wrote it and, for merge-vader, its dimension, never
from anything the reviewer labels it, so a reviewer cannot call a preference a defect to
dodge the evidence rule. merge-vader gives the location in its untyped `Evidence` bullet and
uncle-bob after the dash in the heading; the typed evidence of both is the bullet
`Evidence (metric|idiom|convention): <cite>`.

Only the shape of the report is refused here. The fields of each finding are checked when the
review service adds it.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from mightymodels_core.reviews.errors import (
    EvidenceKindError,
    ForeignSourceError,
    NoFindingsSectionError,
    UnknownDimensionError,
    UnknownSeverityHeadingError,
    UnplacedFindingError,
    UnreadableHeadingError,
)
from mightymodels_core.reviews.records import IncomingEvidence, IncomingFinding

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mightymodels_core.reviews.policy.review import Persona, PersonaSpecs
    from mightymodels_core.vocabulary.reviews import (
        Emphasis,
        EvidenceKind,
        FindingKind,
        FindingSeverity,
    )

FINDINGS_HEADING = '## Findings'
SECTION_HEADING = '## '
BLOCK_LEVEL = '####'
SEVERITY_HEADING = re.compile(r'^###\s+(?P<severity>\S+)\s*$')
BLOCK_HEADING = re.compile(r'^####\s+(?P<id>[A-Z]+-\d+)\s*\|\s*(?P<rest>.+?)\s*$')
BULLET = re.compile(
    r'^-\s+(?P<key>[A-Za-z][A-Za-z ]*?)(?:\s+\((?P<kind>[^)]*)\))?:\s*(?P<value>.*)$'
)
BOB_HEADING = re.compile(
    r'^(?:\[[^\]]+\]\s*)?(?P<title>.+)\s+[\u2014\u2013-]+\s+`(?P<location>[^`]+)`$'
)

SEVERITIES: tuple[FindingSeverity, ...] = ('Blocker', 'Critical', 'High', 'Medium', 'Low')
EVIDENCE_KINDS: tuple[EvidenceKind, ...] = ('metric', 'idiom', 'convention')

type BulletKey = tuple[str, str]
type Bullets = Mapping[BulletKey, str]

LOCATION_KEY: BulletKey = ('evidence', '')
FIX_KEY: BulletKey = ('fix', '')
VERIFY_KEY: BulletKey = ('verify', '')


@dataclass(slots=True, kw_only=True, frozen=True)
class Block:
    severity: FindingSeverity
    heading: str
    body: Sequence[str]


@dataclass(slots=True, kw_only=True, frozen=True)
class Heading:
    index: int
    source: str
    rest: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Basis:
    title: str
    location: str
    kind: FindingKind
    security: bool


def findings_section(lines: Sequence[str]) -> Sequence[str]:
    start = next(
        (number for number, line in enumerate(lines) if line.rstrip() == FINDINGS_HEADING), None
    )
    if start is None:
        raise NoFindingsSectionError

    after = lines[start + 1 :]
    end = next(
        (number for number, line in enumerate(after) if line.startswith(SECTION_HEADING)),
        len(after),
    )
    return after[:end]


def severity_of_heading(heading: str) -> FindingSeverity:
    named = SEVERITY_HEADING.match(heading)
    word = '' if named is None else named['severity'].lower()
    severity = next((item for item in SEVERITIES if item.lower() == word), None)
    if severity is None:
        raise UnknownSeverityHeadingError(heading=heading)

    return severity


def blocks_of(lines: Sequence[str]) -> list[Block]:
    starts = [number for number, line in enumerate(lines) if line.startswith('#')]
    ends = [*starts[1:], len(lines)]
    blocks: list[Block] = []
    severity: FindingSeverity | None = None
    for start, end in zip(starts, ends, strict=True):
        heading = lines[start].rstrip()
        if not heading.startswith(BLOCK_LEVEL):
            severity = severity_of_heading(heading)
            continue

        if severity is None:
            raise UnplacedFindingError(heading=heading)

        blocks.append(Block(severity=severity, heading=heading, body=lines[start + 1 : end]))
    return blocks


def bullet_key(named: re.Match[str]) -> BulletKey:
    kind = str(named['kind'] or '')
    return str(named['key']).lower(), kind


def bullets_of(body: Sequence[str]) -> Bullets:
    bullets: dict[BulletKey, str] = {}
    current: BulletKey | None = None
    for line in body:
        named = BULLET.match(line)
        if named:
            current = bullet_key(named)
            bullets[current] = named['value'].strip()

        if not named and current and line.strip():
            bullets[current] = f'{bullets[current]} {line.strip()}'
    return bullets


def pointer_location(pointer: str) -> str:
    return next(iter(pointer.split()), '').strip('`')


def dimension_kind(dimension: str) -> tuple[FindingKind, bool] | None:
    if dimension == 'security':
        return 'defect', True

    if dimension in {'sdlc', 'docs', 'plan'}:
        return 'defect', False

    if dimension == 'quality':
        return 'quality', False

    return None


class BasisParser(Protocol):
    def basis(self, heading: Heading, bullets: Bullets, /) -> Basis: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class PersonaSpec:
    prefix: str
    parser: BasisParser
    weights: Mapping[Emphasis, float]


class MergeVaderBasis:
    def basis(self, heading: Heading, bullets: Bullets, /) -> Basis:
        dimension, separator, title = heading.rest.partition('|')
        if not separator:
            raise UnreadableHeadingError(heading=f'#### {heading.source} | {heading.rest}')

        named = dimension.strip().lower()
        kind_and_security = dimension_kind(named)
        if kind_and_security is None:
            raise UnknownDimensionError(
                index=heading.index, sources=[heading.source], dimension=named
            )

        kind, security = kind_and_security
        location = pointer_location(bullets.get(LOCATION_KEY, ''))
        return Basis(title=title.strip(), location=location, kind=kind, security=security)


class UncleBobBasis:
    def basis(self, heading: Heading, _bullets: Bullets, /) -> Basis:
        named = BOB_HEADING.match(heading.rest)
        if named is None:
            return Basis(title=heading.rest, location='', kind='quality', security=False)

        return Basis(
            title=named['title'].strip(),
            location=named['location'].strip(),
            kind='quality',
            security=False,
        )


def typed_evidence(heading: Heading, bullets: Bullets) -> IncomingEvidence | None:
    typed = next(
        ((kind, cite) for (key, kind), cite in bullets.items() if key == 'evidence' and kind),
        None,
    )
    if typed is None:
        return None

    kind, cite = typed
    named = next((item for item in EVIDENCE_KINDS if item == kind.strip().lower()), None)
    if named is None:
        raise EvidenceKindError(index=heading.index, sources=[heading.source], kind=kind)

    return IncomingEvidence(kind=named, cite=cite)


@dataclass(slots=True, kw_only=True, frozen=True)
class ReportReader:
    persona: Persona
    spec: PersonaSpec

    def finding_of(self, index: int, block: Block) -> IncomingFinding:
        named = BLOCK_HEADING.match(block.heading)
        if named is None:
            raise UnreadableHeadingError(heading=block.heading)

        if not named['id'].startswith(f'{self.spec.prefix}-'):
            raise ForeignSourceError(index=index, sources=[named['id']], persona=self.persona)

        heading = Heading(index=index, source=named['id'], rest=named['rest'])
        bullets = bullets_of(block.body)
        basis = self.spec.parser.basis(heading, bullets)
        return IncomingFinding(
            sources=(heading.source,),
            severity=block.severity,
            kind=basis.kind,
            security=basis.security,
            title=basis.title,
            location=basis.location,
            fix=bullets.get(FIX_KEY, ''),
            verify=bullets.get(VERIFY_KEY, ''),
            evidence=typed_evidence(heading, bullets),
        )


def parse_report(text: str, persona: Persona, specs: PersonaSpecs) -> list[IncomingFinding]:
    reader = ReportReader(persona=persona, spec=specs[persona])
    blocks = blocks_of(findings_section(text.splitlines()))
    return [reader.finding_of(index, block) for index, block in enumerate(blocks)]
