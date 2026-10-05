"""Review-run state for review-circus: the run, its findings, and the user's decisions.

A run records its scope, depth, persona weights, and reviewer models at HEAD. Findings
from the persona reports are normalized into one severity vocabulary, deduplicated by
overlapping location, redacted, and given stable ids (F1, F2, ...). Only the user's
dispositions move a finding to remediation. Weights order findings inside a severity;
they never filter or downgrade one. Every write is validated in full before anything
lands, and the run file is replaced atomically.

Usage:
    python3 review_state.py start --scope SCOPE --depth DEPTH --emphasis EMPHASIS
        [--slug SLUG] [--base REF] [--weights merge-vader=0.6,uncle-bob=0.4]
        [--persona merge-vader|uncle-bob]
    python3 review_state.py add --run RUN  < findings.json
    python3 review_state.py gate --run RUN
    python3 review_state.py dispose --run RUN  < dispositions.json
    python3 review_state.py resolve --run RUN --finding F1 --result RESULT
        [--commit SHA] [--reason TEXT]
    python3 review_state.py report --run RUN [--shape full|comment]
    python3 review_state.py list
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

SCHEMA_VERSION = 1
EXIT_REJECTED = 2
EXCLUDE_LINE = '.mightymodels/'
RUN_ID = re.compile(r'^\d{8}-\d{6}$')
FINDING_ID = re.compile(r'^F(\d+)$')
SOURCE_ID = re.compile(r'^(MV|UB)-\d+$')
LOCATION = re.compile(r'^(?P<path>[^\s:]+):(?P<start>\d+)(?:-(?P<end>\d+))?$')
SAFE_REVISION = re.compile(r'^[0-9A-Za-z][0-9A-Za-z._/-]*$')
SAFE_SLUG = re.compile(r'^[a-z0-9][a-z0-9-]*$')
STANDARD_THRESHOLD = 0.25
WEIGHT_TOLERANCE = 0.001
CONFLICT_GAP = 2
COMMENT_LIMIT = 10
SHORT_SHA = 12
SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    'private-key': re.compile(
        r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----',
        re.DOTALL,
    ),
    'aws-key': re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b'),
    'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_\w{20,})'),
    'slack-token': re.compile(r'\bxox[abposr]-[A-Za-z0-9-]{10,}'),
    'stripe-key': re.compile(r'\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b'),
    'api-key': re.compile(r'\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}'),
    'jwt': re.compile(r'\beyJ[\w-]+\.[\w-]+\.[\w-]+'),
    'bearer': re.compile(r'\bBearer [A-Za-z0-9._~+/-]{12,}=*'),
    'url-credentials': re.compile(r'(?<=://)[^/\s:@]+:[^@\s]+(?=@)'),
    'assignment': re.compile(
        r'(?i)[A-Z0-9_]*(?:password|passwd|secret|token|api[_-]?key)[A-Z0-9_]*'
        r'["\']?\s*[:=]\s*["\']?[^\s,;"\']+'
    ),
}


class Command(StrEnum):
    START = 'start'
    ADD = 'add'
    GATE = 'gate'
    DISPOSE = 'dispose'
    RESOLVE = 'resolve'
    REPORT = 'report'
    LIST = 'list'


class Scope(StrEnum):
    DIFF = 'diff'
    BRANCH = 'branch'
    TICKET = 'ticket'
    CODEBASE = 'codebase'


class Depth(StrEnum):
    QUICK = 'quick'
    STANDARD = 'standard'
    DEEP = 'deep'


class Emphasis(StrEnum):
    RELEASE = 'release-readiness'
    MAINTAINABILITY = 'maintainability'
    BALANCED = 'balanced'
    CUSTOM = 'custom'


class Persona(StrEnum):
    MERGE_VADER = 'merge-vader'
    UNCLE_BOB = 'uncle-bob'


class Severity(StrEnum):
    CRITICAL = 'Critical'
    HIGH = 'High'
    MEDIUM = 'Medium'
    LOW = 'Low'


class Kind(StrEnum):
    DEFECT = 'defect'
    QUALITY = 'quality'


class EvidenceKind(StrEnum):
    METRIC = 'metric'
    IDIOM = 'idiom'
    CONVENTION = 'convention'


class Decision(StrEnum):
    FIX = 'fix'
    DEFER = 'defer'
    ACCEPT_RISK = 'accept-risk'
    DISMISS = 'dismiss'


class Result(StrEnum):
    FIXED = 'fixed'
    FAILED = 'failed'
    BLOCKED = 'blocked'


class Shape(StrEnum):
    FULL = 'full'
    COMMENT = 'comment'


class Verdict(StrEnum):
    BLOCK = 'BLOCK'
    CONDITIONS = 'MERGE WITH CONDITIONS'
    CLEAR = 'CLEAR'


RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}
NATIVE_SEVERITY: dict[str, Severity] = {
    'blocker': Severity.CRITICAL,
    'critical': Severity.CRITICAL,
    'high': Severity.HIGH,
    'medium': Severity.MEDIUM,
    'low': Severity.LOW,
}
PRESETS: dict[Emphasis, dict[Persona, float]] = {
    Emphasis.RELEASE: {Persona.MERGE_VADER: 0.7, Persona.UNCLE_BOB: 0.3},
    Emphasis.MAINTAINABILITY: {Persona.MERGE_VADER: 0.3, Persona.UNCLE_BOB: 0.7},
    Emphasis.BALANCED: {Persona.MERGE_VADER: 0.5, Persona.UNCLE_BOB: 0.5},
}
SOURCE_PERSONA: dict[str, Persona] = {
    'MV': Persona.MERGE_VADER,
    'UB': Persona.UNCLE_BOB,
}
DEPTH_MODELS: dict[Depth, str] = {
    Depth.QUICK: 'gpt-5.6-luna',
    Depth.STANDARD: 'gpt-5.6-terra',
}
TICKET_MODELS: dict[Persona, str] = {
    Persona.MERGE_VADER: 'gpt-5.6-sol',
    Persona.UNCLE_BOB: 'claude-sonnet-5',
}
NEEDS_REASON = frozenset({Decision.ACCEPT_RISK, Decision.DISMISS})
CLOSED_BY_DECISION = frozenset({Decision.DISMISS})


class Problem(StrEnum):
    WEIGHT_ITEM = '{detail} is not persona=weight'
    WEIGHT_RANGE = 'give both personas a weight between 0 and 1'
    WEIGHT_SUM = 'the weights must sum to 1'
    WEIGHT_MISSING = 'custom emphasis needs --weights'
    REQUIRED = '{detail} is required'
    SOURCES = 'sources must list report ids like MV-3 or UB-2'
    SEVERITY = 'severity must be Critical, High, Medium, Low, or Blocker'
    EVIDENCE_SHAPE = 'evidence needs a kind and a cite'
    EVIDENCE_KIND = 'evidence kind is metric, idiom, or convention'
    KIND = 'kind is defect or quality'
    OBJECT = 'each finding is a JSON object'
    LOCATION = 'location must be path:line or path:start-end'
    UNSUPPORTED = (
        'a quality finding at Medium or above needs structured evidence '
        '(metric, idiom, or convention); lower it to Low or cite the evidence'
    )
    FINDINGS_INPUT = 'a JSON array of findings'
    DECISIONS_INPUT = '{{"by": "user", "decisions": {{"F1": {{"decision": "fix"}}}}}}'
    NO_FINDING = 'no such finding'
    DECISION = 'decision is fix, defer, accept-risk, or dismiss'
    NEEDS_REASON = '{detail} needs a reason'
    NOT_CHOSEN = 'only a finding the user chose to fix is resolved'
    NEEDS_COMMIT = 'fixed needs --commit'
    RESULT_REASON = '{detail} needs --reason'

    def text(self, detail: str = '') -> str:
        return self.value.format(detail=detail)


class ReviewError(Exception):
    pass


class NoRepositoryError(ReviewError):
    def __init__(self, cwd: Path) -> None:
        super().__init__(f'{cwd} is not inside a git repository')


class InvalidValueError(ReviewError):
    def __init__(self, what: str, value: object) -> None:
        super().__init__(f'{what} {value!r} is not valid')


class WeightsError(ReviewError):
    def __init__(self, problem: Problem, detail: str = '') -> None:
        super().__init__(f'--weights: {problem.text(detail)}')


class PersonaChoiceError(ReviewError):
    def __init__(self) -> None:
        super().__init__('quick depth runs one persona and the weights tie; pass --persona')


class BaseRequiredError(ReviewError):
    def __init__(self, scope: Scope) -> None:
        super().__init__(f'{scope} scope needs --base, the ref it is reviewed against')


class SlugRequiredError(ReviewError):
    def __init__(self) -> None:
        super().__init__('ticket scope needs --slug')


class RunNotFoundError(ReviewError):
    def __init__(self, run: str) -> None:
        super().__init__(f'no review run {run!r}; start one first')


class RunExistsError(ReviewError):
    def __init__(self, run: str) -> None:
        super().__init__(f'review run {run} already exists; start again in a second')


class FindingError(ReviewError):
    def __init__(self, index: int, problem: Problem, detail: str = '') -> None:
        super().__init__(f'finding {index}: {problem.text(detail)}; nothing was written')


class DispositionError(ReviewError):
    def __init__(self, finding: str, problem: Problem, detail: str = '') -> None:
        super().__init__(f'{finding}: {problem.text(detail)}; nothing was written')


class ResolveError(ReviewError):
    def __init__(self, finding: str, problem: Problem, detail: str = '') -> None:
        super().__init__(f'{finding}: {problem.text(detail)}')


class InputError(ReviewError):
    def __init__(self, expected: Problem) -> None:
        super().__init__(f'stdin must be {expected.text()}')


@dataclass(frozen=True, slots=True)
class Evidence:
    kind: EvidenceKind
    cite: str


@dataclass(slots=True)
class Finding:
    id: str
    sources: list[str]
    severity: Severity
    kind: Kind
    security: bool
    title: str
    location: str
    fix: str
    verify: str
    evidence: Evidence | None = None
    conflict: str | None = None

    @property
    def number(self) -> int:
        return int(self.id[1:])

    @property
    def span(self) -> tuple[str, int, int]:
        match = LOCATION.match(self.location)
        if match is None:
            return self.location, 0, 0
        start = int(match['start'])
        return match['path'], start, int(match['end'] or start)

    def record(self) -> dict[str, object]:
        record = asdict(self)
        record['schema'] = SCHEMA_VERSION
        return record


@dataclass(slots=True)
class Run:
    run: str
    slug: str | None
    scope: Scope
    base: str | None
    head: str | None
    depth: Depth
    emphasis: Emphasis
    weights: dict[str, float]
    personas: list[str]
    models: dict[str, str]
    created_at: str
    dispositions: dict[str, dict[str, str]] = field(default_factory=dict)
    outcomes: dict[str, dict[str, str]] = field(default_factory=dict)
    schema: int = SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class Location:
    root: Path
    directory: Path

    @property
    def run_file(self) -> Path:
        return self.directory / 'review-run.json'

    @property
    def findings_file(self) -> Path:
        return self.directory / 'findings.jsonl'


def now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec='seconds')


def repository_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / '.git').exists():
            return candidate
    raise NoRepositoryError(start)


def read_text(path: Path) -> str | None:
    return path.read_text(encoding='utf-8').strip() if path.is_file() else None


def git_dir(root: Path) -> Path:
    dot_git = root / '.git'
    if dot_git.is_file():
        pointer = read_text(dot_git) or ''
        return (root / pointer.removeprefix('gitdir:').strip()).resolve()
    return dot_git


def common_dir(directory: Path) -> Path:
    pointer = read_text(directory / 'commondir')
    return (directory / pointer).resolve() if pointer else directory


def packed_ref(directory: Path, ref: str) -> str | None:
    packed = read_text(directory / 'packed-refs') or ''
    matches = (
        line.split(' ', 1)[0]
        for line in packed.splitlines()
        if line.endswith(f' {ref}') and not line.startswith(('#', '^'))
    )
    return next(matches, None)


def resolve_head(root: Path) -> str | None:
    directory = git_dir(root)
    head = read_text(directory / 'HEAD')
    if head is None or not head.startswith('ref:'):
        return head
    ref = head.removeprefix('ref:').strip()
    shared = common_dir(directory)
    return read_text(directory / ref) or read_text(shared / ref) or packed_ref(shared, ref)


def ensure_excluded(root: Path) -> None:
    exclude = common_dir(git_dir(root)) / 'info' / 'exclude'
    current = exclude.read_text(encoding='utf-8') if exclude.is_file() else ''
    if EXCLUDE_LINE in current.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    separator = '' if not current or current.endswith('\n') else '\n'
    exclude.write_text(f'{current}{separator}{EXCLUDE_LINE}\n', encoding='utf-8')


def redact(text: str) -> str:
    for name, pattern in SECRET_PATTERNS.items():
        text = pattern.sub(f'[REDACTED:{name}]', text)
    return text


def checked(what: str, value: str | None, pattern: re.Pattern[str]) -> str | None:
    if value is not None and not pattern.match(value):
        raise InvalidValueError(what, value)
    return value


def run_directory(root: Path, slug: str | None, run: str) -> Path:
    if slug:
        return root / '.mightymodels' / slug / 'review' / run
    return root / '.mightymodels' / '.runtime' / 'reviews' / run


def locate(root: Path, run: str) -> Location:
    checked('--run', run, RUN_ID)
    candidates = [
        run_directory(root, None, run),
        *(root / '.mightymodels').glob(f'*/review/{run}'),
    ]
    for directory in candidates:
        if (directory / 'review-run.json').is_file():
            return Location(root, directory)
    raise RunNotFoundError(run)


def load_run(location: Location) -> Run:
    raw = json.loads(location.run_file.read_text(encoding='utf-8'))
    return Run(
        **{
            **raw,
            'scope': Scope(raw['scope']),
            'depth': Depth(raw['depth']),
            'emphasis': Emphasis(raw['emphasis']),
        }
    )


def save_run(location: Location, run: Run) -> None:
    location.directory.mkdir(parents=True, exist_ok=True)
    temporary = location.run_file.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(asdict(run), indent=2) + '\n', encoding='utf-8')
    temporary.replace(location.run_file)


def finding_from(record: dict[str, object]) -> Finding:
    evidence = record.get('evidence')
    fields = {key: value for key, value in record.items() if key != 'schema'}
    return Finding(
        **{
            **fields,
            'severity': Severity(str(record['severity'])),
            'kind': Kind(str(record['kind'])),
            'evidence': Evidence(EvidenceKind(evidence['kind']), evidence['cite'])
            if isinstance(evidence, dict)
            else None,
        }
    )


def load_findings(location: Location) -> dict[str, Finding]:
    if not location.findings_file.is_file():
        return {}
    lines = location.findings_file.read_text(encoding='utf-8').splitlines()
    latest = [finding_from(json.loads(line)) for line in lines if line.strip()]
    return {finding.id: finding for finding in latest}


def append_findings(location: Location, findings: list[Finding]) -> None:
    with location.findings_file.open('a', encoding='utf-8') as handle:
        for finding in findings:
            handle.write(json.dumps(finding.record()) + '\n')


def parse_weights(text: str) -> dict[Persona, float]:
    weights: dict[Persona, float] = {}
    for item in text.split(','):
        name, _, value = item.partition('=')
        try:
            weights[Persona(name.strip())] = float(value)
        except ValueError as error:
            raise WeightsError(Problem.WEIGHT_ITEM, repr(item)) from error
    if set(weights) != set(Persona) or not all(0 <= v <= 1 for v in weights.values()):
        raise WeightsError(Problem.WEIGHT_RANGE)
    if abs(sum(weights.values()) - 1) > WEIGHT_TOLERANCE:
        raise WeightsError(Problem.WEIGHT_SUM)
    return weights


def weights_for(options: argparse.Namespace) -> dict[Persona, float]:
    emphasis = Emphasis(options.emphasis)
    if emphasis is Emphasis.CUSTOM:
        if not options.weights:
            raise WeightsError(Problem.WEIGHT_MISSING)
        return parse_weights(options.weights)
    return PRESETS[emphasis]


def personas_for(depth: Depth, weights: dict[Persona, float], chosen: str | None) -> list[Persona]:
    if depth is Depth.DEEP:
        return list(Persona)
    if depth is Depth.STANDARD:
        return [persona for persona in Persona if weights[persona] >= STANDARD_THRESHOLD]
    if chosen:
        return [Persona(chosen)]
    heaviest = max(weights.values())
    leaders = [persona for persona in Persona if weights[persona] == heaviest]
    if len(leaders) > 1:
        raise PersonaChoiceError
    return leaders


def ticket_models(root: Path, slug: str | None) -> dict[str, object]:
    if not slug:
        return {}
    unit = root / '.mightymodels' / slug / 'work-unit.json'
    if not unit.is_file():
        return {}
    ticket = json.loads(unit.read_text(encoding='utf-8')).get('ticket', {})
    models = ticket.get('models') if isinstance(ticket, dict) else None
    return models if isinstance(models, dict) else {}


def model_for(persona: Persona, depth: Depth, pinned: dict[str, object]) -> str:
    if depth in DEPTH_MODELS:
        return DEPTH_MODELS[depth]
    configured = pinned.get(f'{persona}-reviewer')
    return str(configured) if configured else TICKET_MODELS[persona]


@dataclass(frozen=True, slots=True)
class Target:
    scope: Scope
    slug: str | None
    base: str | None


def target_of(options: argparse.Namespace) -> Target:
    scope = Scope(options.scope)
    slug = checked('--slug', options.slug, SAFE_SLUG)
    base = checked('--base', options.base, SAFE_REVISION)
    if scope in {Scope.BRANCH, Scope.TICKET} and base is None:
        raise BaseRequiredError(scope)
    if scope is Scope.TICKET and slug is None:
        raise SlugRequiredError
    return Target(scope, slug, base)


def new_run(options: argparse.Namespace, root: Path, target: Target) -> Run:
    depth = Depth(options.depth)
    weights = weights_for(options)
    personas = personas_for(depth, weights, options.persona)
    pinned = ticket_models(root, target.slug)
    started = datetime.now(tz=UTC)
    return Run(
        run=started.strftime('%Y%m%d-%H%M%S'),
        slug=target.slug,
        scope=target.scope,
        base=target.base,
        head=resolve_head(root),
        depth=depth,
        emphasis=Emphasis(options.emphasis),
        weights={str(persona): weight for persona, weight in weights.items()},
        personas=[str(persona) for persona in personas],
        models={f'{persona}-reviewer': model_for(persona, depth, pinned) for persona in personas},
        created_at=started.isoformat(timespec='seconds'),
    )


def run_start(options: argparse.Namespace, root: Path) -> str:
    target = target_of(options)
    run = new_run(options, root, target)
    ensure_excluded(root)
    location = Location(root, run_directory(root, target.slug, run.run))
    if location.run_file.exists():
        raise RunExistsError(run.run)
    save_run(location, run)
    models = ', '.join(f'{name} on {model}' for name, model in run.models.items())
    relative = location.directory.relative_to(root)
    return f'run {run.run} at {relative}\n{run.depth} review: {models}\n'


def text_field(entry: dict[str, object], key: str, index: int) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FindingError(index, Problem.REQUIRED, key)
    return redact(value.strip())


def sources_of(entry: dict[str, object], index: int) -> list[str]:
    raw = entry.get('sources')
    sources = [raw] if isinstance(raw, str) else raw
    if (
        not isinstance(sources, list)
        or not sources
        or not all(isinstance(source, str) and SOURCE_ID.match(source) for source in sources)
    ):
        raise FindingError(index, Problem.SOURCES)
    return sorted(set(sources))


def severity_of(entry: dict[str, object], index: int) -> Severity:
    severity = NATIVE_SEVERITY.get(str(entry.get('severity', '')).lower())
    if severity is None:
        raise FindingError(index, Problem.SEVERITY)
    return severity


def evidence_of(entry: dict[str, object], index: int) -> Evidence | None:
    raw = entry.get('evidence')
    if raw is None:
        return None
    if not isinstance(raw, dict) or not str(raw.get('cite', '')).strip():
        raise FindingError(index, Problem.EVIDENCE_SHAPE)
    try:
        kind = EvidenceKind(str(raw.get('kind')))
    except ValueError as error:
        raise FindingError(index, Problem.EVIDENCE_KIND) from error
    return Evidence(kind, redact(str(raw['cite']).strip()))


def kind_of(entry: dict[str, object], index: int) -> Kind:
    try:
        return Kind(str(entry.get('kind', Kind.DEFECT)))
    except ValueError as error:
        raise FindingError(index, Problem.KIND) from error


def normalized(entry: object, index: int) -> Finding:
    if not isinstance(entry, dict):
        raise FindingError(index, Problem.OBJECT)
    severity = severity_of(entry, index)
    location = text_field(entry, 'location', index)
    if not LOCATION.match(location):
        raise FindingError(index, Problem.LOCATION)
    finding = Finding(
        id='',
        sources=sources_of(entry, index),
        severity=severity,
        kind=kind_of(entry, index),
        security=entry.get('security') is True,
        title=text_field(entry, 'title', index),
        location=location,
        fix=text_field(entry, 'fix', index),
        verify=text_field(entry, 'verify', index),
        evidence=evidence_of(entry, index),
    )
    raised = RANK[severity] <= RANK[Severity.MEDIUM]
    if finding.kind is Kind.QUALITY and raised and finding.evidence is None:
        raise FindingError(index, Problem.UNSUPPORTED)
    return finding


def overlaps(left: Finding, right: Finding) -> bool:
    left_path, left_start, left_end = left.span
    right_path, right_start, right_end = right.span
    return left_path == right_path and left_start <= right_end and right_start <= left_end


def merged(existing: Finding, incoming: Finding) -> Finding:
    keep, other = (
        (incoming, existing)
        if RANK[incoming.severity] < RANK[existing.severity]
        else (existing, incoming)
    )
    gap = abs(RANK[existing.severity] - RANK[incoming.severity])
    conflict = existing.conflict
    if gap >= CONFLICT_GAP:
        conflict = (
            f'{"/".join(other.sources)} rated {other.severity}, '
            f'{"/".join(keep.sources)} rated {keep.severity}: the user decides'
        )
    return Finding(
        id=existing.id,
        sources=sorted(set(existing.sources) | set(incoming.sources)),
        severity=keep.severity,
        kind=keep.kind,
        security=existing.security or incoming.security,
        title=keep.title,
        location=keep.location,
        fix=keep.fix,
        verify=keep.verify,
        evidence=keep.evidence or other.evidence,
        conflict=conflict,
    )


def fold(current: dict[str, Finding], incoming: list[Finding]) -> list[Finding]:
    working = dict(current)
    changed: dict[str, Finding] = {}
    next_number = max((finding.number for finding in working.values()), default=0) + 1
    for finding in incoming:
        match = next((old for old in working.values() if overlaps(old, finding)), None)
        if match is None:
            finding.id = f'F{next_number}'
            next_number += 1
            result = finding
        else:
            result = merged(match, finding)
        working[result.id] = changed[result.id] = result
    return sorted(changed.values(), key=by_number)


def by_number(finding: Finding) -> int:
    return finding.number


def run_add(options: argparse.Namespace, root: Path) -> str:
    location = locate(root, options.run)
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as error:
        raise InputError(Problem.FINDINGS_INPUT) from error
    if not isinstance(payload, list):
        raise InputError(Problem.FINDINGS_INPUT)
    incoming = [normalized(entry, index) for index, entry in enumerate(payload)]
    changed = fold(load_findings(location), incoming)
    append_findings(location, changed)
    ids = ', '.join(finding.id for finding in changed) or 'none'
    return f'{len(incoming)} findings in, {len(changed)} recorded: {ids}\n'


def heaviest_weight(finding: Finding, run: Run) -> float:
    return max(run.weights.get(SOURCE_PERSONA[s.split('-')[0]], 0) for s in finding.sources)


def ordered(findings: dict[str, Finding], run: Run) -> list[Finding]:
    return sorted(findings.values(), key=GateOrder(run))


@dataclass(frozen=True, slots=True)
class GateOrder:
    run: Run

    def __call__(self, finding: Finding) -> tuple[int, bool, float, int]:
        return (
            RANK[finding.severity],
            not finding.security,
            -heaviest_weight(finding, self.run),
            finding.number,
        )


def label(finding: Finding) -> str:
    tags = [str(finding.severity)]
    if finding.security:
        tags.append('security')
    if finding.kind is Kind.QUALITY:
        tags.append('quality')
    return ' '.join(tags)


def gate_line(finding: Finding, run: Run) -> str:
    decision = run.dispositions.get(finding.id, {}).get('decision', 'undecided')
    sources = '/'.join(finding.sources)
    line = (
        f'{finding.id}\t{label(finding)}\t[{sources}]\t{finding.location}\t'
        f'{finding.title}\t{decision}\n'
    )
    if finding.conflict:
        line += f'\tconflict: {finding.conflict}\n'
    return line


def run_gate(options: argparse.Namespace, root: Path) -> str:
    location = locate(root, options.run)
    run = load_run(location)
    findings = ordered(load_findings(location), run)
    if not findings:
        return 'no findings recorded\n'
    return ''.join(gate_line(finding, run) for finding in findings)


@dataclass(frozen=True, slots=True)
class Decisions:
    by: str
    entries: dict[str, object]


def read_decisions() -> Decisions:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as error:
        raise InputError(Problem.DECISIONS_INPUT) from error
    by = str(payload.get('by', '')).strip() if isinstance(payload, dict) else ''
    entries = payload.get('decisions') if isinstance(payload, dict) else None
    if not by or not isinstance(entries, dict):
        raise InputError(Problem.DECISIONS_INPUT)
    return Decisions(by, entries)


def run_dispose(options: argparse.Namespace, root: Path) -> str:
    location = locate(root, options.run)
    run = load_run(location)
    findings = load_findings(location)
    decisions = read_decisions()
    recorded = {
        finding_id: disposition(finding_id, entry, findings, by=decisions.by)
        for finding_id, entry in decisions.entries.items()
    }
    run.dispositions.update(recorded)
    save_run(location, run)
    undecided = sorted(set(findings) - set(run.dispositions), key=finding_number)
    tail = f'; undecided: {", ".join(undecided)}' if undecided else ''
    return f'{len(recorded)} dispositions recorded{tail}\n'


def finding_number(finding_id: str) -> int:
    return int(finding_id[1:])


def disposition(
    finding_id: str, entry: object, findings: dict[str, Finding], *, by: str
) -> dict[str, str]:
    if finding_id not in findings:
        raise DispositionError(finding_id, Problem.NO_FINDING)
    raw = entry.get('decision') if isinstance(entry, dict) else entry
    try:
        decision = Decision(str(raw))
    except ValueError as error:
        raise DispositionError(finding_id, Problem.DECISION) from error
    reason = str(entry.get('reason', '')).strip() if isinstance(entry, dict) else ''
    if decision in NEEDS_REASON and not reason:
        raise DispositionError(finding_id, Problem.NEEDS_REASON, decision)
    return {'decision': str(decision), 'reason': redact(reason), 'by': by, 'at': now()}


def run_resolve(options: argparse.Namespace, root: Path) -> str:
    location = locate(root, options.run)
    run = load_run(location)
    finding_id = checked('--finding', options.finding, FINDING_ID) or ''
    if finding_id not in load_findings(location):
        raise ResolveError(finding_id, Problem.NO_FINDING)
    if run.dispositions.get(finding_id, {}).get('decision') != Decision.FIX:
        raise ResolveError(finding_id, Problem.NOT_CHOSEN)
    result = Result(options.result)
    commit = checked('--commit', options.commit, SAFE_REVISION)
    if result is Result.FIXED and commit is None:
        raise ResolveError(finding_id, Problem.NEEDS_COMMIT)
    if result is not Result.FIXED and not options.reason:
        raise ResolveError(finding_id, Problem.RESULT_REASON, result)
    run.outcomes[finding_id] = {
        'result': str(result),
        'commit': commit or '',
        'reason': redact(options.reason or ''),
        'at': now(),
    }
    save_run(location, run)
    return f'{finding_id} {result}\n'


def is_open(finding: Finding, run: Run) -> bool:
    decision = run.dispositions.get(finding.id, {}).get('decision')
    fixed = run.outcomes.get(finding.id, {}).get('result') == Result.FIXED
    return not fixed and decision not in CLOSED_BY_DECISION


def verdict_of(findings: list[Finding], run: Run) -> Verdict:
    remaining = [finding for finding in findings if is_open(finding, run)]
    accepted = {
        finding_id
        for finding_id, entry in run.dispositions.items()
        if entry.get('decision') == Decision.ACCEPT_RISK
    }
    blocking = [
        finding
        for finding in remaining
        if finding.severity is Severity.CRITICAL
        or (finding.severity is Severity.HIGH and finding.id not in accepted)
    ]
    if blocking:
        return Verdict.BLOCK
    if any(RANK[finding.severity] <= RANK[Severity.MEDIUM] for finding in remaining):
        return Verdict.CONDITIONS
    return Verdict.CLEAR


def status_of(finding: Finding, run: Run) -> str:
    outcome = run.outcomes.get(finding.id)
    if outcome:
        return outcome['result']
    return run.dispositions.get(finding.id, {}).get('decision', 'undecided')


def counts(findings: list[Finding]) -> str:
    tally = [
        f'{sum(1 for finding in findings if finding.severity is severity)} {severity}'
        for severity in Severity
    ]
    return ', '.join(tally)


def header_lines(run: Run, findings: list[Finding]) -> list[str]:
    scope = f'{run.scope} against {run.base}' if run.base else str(run.scope)
    models = ', '.join(f'{name} ({model})' for name, model in run.models.items())
    return [
        f'**Verdict: {verdict_of(findings, run)}**',
        '',
        (
            f'Review run `{run.run}` at `{(run.head or "unknown")[:SHORT_SHA]}`: '
            f'{scope}, {run.depth} depth, {run.emphasis} emphasis. Reviewers: {models}.'
        ),
        '',
        f'Findings: {counts(findings)}.',
    ]


def finding_block(finding: Finding, run: Run) -> list[str]:
    lines = [
        f'### {finding.id} | {label(finding)} | {finding.title}',
        '',
        f'- Location: `{finding.location}`',
        f'- Sources: {", ".join(finding.sources)}',
        f'- Status: {status_of(finding, run)}',
        f'- Fix: {finding.fix}',
        f'- Verify: {finding.verify}',
    ]
    if finding.evidence:
        lines.append(f'- Evidence ({finding.evidence.kind}): {finding.evidence.cite}')
    if finding.conflict:
        lines.append(f'- Severity conflict: {finding.conflict}')
    reason = run.dispositions.get(finding.id, {}).get('reason')
    if reason:
        lines.append(f'- Decision reason: {reason}')
    return [*lines, '']


def severity_section(severity: Severity, findings: list[Finding], run: Run) -> list[str]:
    group = [finding for finding in findings if finding.severity is severity]
    if not group:
        return []
    blocks = (line for finding in group for line in finding_block(finding, run))
    return [f'## {severity}', '', *blocks]


def full_report(run: Run, findings: list[Finding]) -> str:
    lines = ['# Review report', '', *header_lines(run, findings), '']
    for severity in Severity:
        lines.extend(severity_section(severity, findings, run))
    return '\n'.join(lines).rstrip() + '\n'


def comment_line(finding: Finding, run: Run) -> str:
    return (
        f'- {finding.id} ({label(finding)}, {status_of(finding, run)}): {finding.title}. '
        f'`{finding.location}`'
    )


def comment_report(run: Run, findings: list[Finding]) -> str:
    shown = [finding for finding in findings if finding.severity is not Severity.LOW]
    lines = ['## Review', '', *header_lines(run, findings), '']
    lines.extend(comment_line(finding, run) for finding in shown[:COMMENT_LIMIT])
    hidden = len(shown) - COMMENT_LIMIT
    if hidden > 0:
        lines.append(f'- {hidden} more at Medium or above in the full report.')
    if not shown:
        lines.append('Nothing at Medium or above.')
    return '\n'.join(lines).rstrip() + '\n'


RENDERERS: dict[Shape, tuple[str, Callable[[Run, list[Finding]], str]]] = {
    Shape.FULL: ('report.md', full_report),
    Shape.COMMENT: ('pr-comment.md', comment_report),
}


def run_report(options: argparse.Namespace, root: Path) -> str:
    location = locate(root, options.run)
    run = load_run(location)
    findings = ordered(load_findings(location), run)
    name, render = RENDERERS[Shape(options.shape)]
    target = location.directory / name
    temporary = target.with_suffix('.md.tmp')
    temporary.write_text(render(run, findings), encoding='utf-8')
    temporary.replace(target)
    return f'{target.relative_to(root)} ({verdict_of(findings, run)})\n'


def run_list(_options: argparse.Namespace, root: Path) -> str:
    directory = root / '.mightymodels'
    files = sorted(
        [
            *directory.glob('.runtime/reviews/*/review-run.json'),
            *directory.glob('*/review/*/review-run.json'),
        ],
        key=run_file_order,
    )
    rows = []
    for run_file in files:
        location = Location(root, run_file.parent)
        run = load_run(location)
        findings = ordered(load_findings(location), run)
        rows.append(
            f'{run.run}\t{run.slug or "-"}\t{run.depth}\t{len(findings)} findings\t'
            f'{verdict_of(findings, run)}\n'
        )
    return ''.join(rows) or 'no review runs\n'


def run_file_order(path: Path) -> str:
    return path.parent.name


HANDLERS: dict[Command, Callable[[argparse.Namespace, Path], str]] = {
    Command.START: run_start,
    Command.ADD: run_add,
    Command.GATE: run_gate,
    Command.DISPOSE: run_dispose,
    Command.RESOLVE: run_resolve,
    Command.REPORT: run_report,
    Command.LIST: run_list,
}


def add_start(start: argparse.ArgumentParser) -> None:
    start.add_argument('--scope', required=True, choices=[s.value for s in Scope])
    start.add_argument('--depth', required=True, choices=[d.value for d in Depth])
    start.add_argument('--emphasis', required=True, choices=[e.value for e in Emphasis])
    start.add_argument('--slug')
    start.add_argument('--base')
    start.add_argument('--weights')
    start.add_argument('--persona', choices=[p.value for p in Persona])


def add_resolve(resolve: argparse.ArgumentParser) -> None:
    resolve.add_argument('--finding', required=True)
    resolve.add_argument('--result', required=True, choices=[r.value for r in Result])
    resolve.add_argument('--commit')
    resolve.add_argument('--reason')


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog='review_state.py', description=__doc__.splitlines()[0])
    commands = root.add_subparsers(dest='command', required=True)
    add_start(commands.add_parser(Command.START, help='record a new review run'))
    add = commands.add_parser(Command.ADD, help='normalize findings from stdin')
    gate = commands.add_parser(Command.GATE, help='findings in decision order')
    dispose = commands.add_parser(Command.DISPOSE, help="record the user's decisions")
    resolve = commands.add_parser(Command.RESOLVE, help='record a remediation outcome')
    add_resolve(resolve)
    report = commands.add_parser(Command.REPORT, help='render report.md or pr-comment.md')
    report.add_argument('--shape', choices=[s.value for s in Shape], default='full')
    commands.add_parser(Command.LIST, help='every review run in this repository')
    for sub in (add, gate, dispose, resolve, report):
        sub.add_argument('--run', required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    options = parser().parse_args(argv)
    try:
        root = repository_root(Path.cwd())
        output = HANDLERS[Command(options.command)](options, root)
    except ReviewError as error:
        sys.stderr.write(f'error: {error}\n')
        return EXIT_REJECTED
    sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
