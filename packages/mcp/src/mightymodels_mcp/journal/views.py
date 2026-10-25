"""What the journal tools return, and the texts.

Core returns records and no text, so each function takes core's result and returns the text. The
patterns count the journal by severity and by verdict, most frequent first, list every failure
under the day, verdict and severity of its crashout, and end with the corrective actions, each
once. One crashout reads as a line per field in the journal's field order, the rant and the
failures indented under their names.
"""

from typing import TYPE_CHECKING

from mightymodels_core.crashouts.records import JOURNAL_WINDOW
from mightymodels_core.vocabulary.crashouts import CrashoutSeverity, Verdict
from mightymodels_core.vocabulary.similarity import SimilarityKind
from pydantic import BaseModel, ConfigDict

from mightymodels_mcp.review.views import duplicates_text, match_line

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mightymodels_core.crashouts import CrashoutRecord, CrashoutStats, FailureLine, Journaled
    from mightymodels_core.similarity.records import Match

ABSENT = 'none'
NOTHING_JOURNALED = 'no crashouts recorded yet.'
SERENITY = f'{NOTHING_JOURNALED} serenity.'
OLDER_LEFT_OUT = f'older crashouts are left out: these are the latest {JOURNAL_WINDOW.rows}\n'
NO_MATCHES = 'no similar rows\n'


class JournaledCrashout(BaseModel):
    model_config = ConfigDict(frozen=True)

    at: str
    ticket: str | None
    branch: str | None
    severity: CrashoutSeverity
    verdict: Verdict
    rant: str
    failures: tuple[str, ...]
    root_cause: str
    corrective_action: str
    barked_back: bool


class SimilarMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: SimilarityKind
    reference: str
    text: str
    overlap: float


class JournalView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    entry: JournaledCrashout | None = None
    matches: tuple[SimilarMatch, ...] = ()


def timestamp(record: CrashoutRecord) -> str:
    return record.at.isoformat(timespec='seconds')


def journaled_crashout(record: CrashoutRecord) -> JournaledCrashout:
    return JournaledCrashout(
        at=timestamp(record),
        ticket=record.ticket_key,
        branch=record.branch,
        severity=record.severity,
        verdict=record.verdict,
        rant=record.rant,
        failures=record.failures,
        root_cause=record.root_cause,
        corrective_action=record.corrective_action,
        barked_back=record.barked_back,
    )


def counted(pairs: Iterable[tuple[str, int]]) -> str:
    return ' '.join(f'{name}={count}' for name, count in pairs)


def failure_line(line: FailureLine) -> str:
    return f'  [{line.day.isoformat()} | {line.verdict} | {line.severity}] {line.failure}'


def patterns_text(stats: CrashoutStats) -> str:
    lines = [
        f'entries: {stats.entries}',
        f'severity: {counted(stats.severities)}',
        f'verdicts: {counted(stats.verdicts)}',
        f'barked_back: {stats.barked_back}/{stats.entries}',
        f'first: {timestamp(stats.first)}  last: {timestamp(stats.last)}',
        '',
        'failures:',
        *map(failure_line, stats.failures),
        '',
        'standing corrective actions:',
        *(f'  - {action}' for action in stats.corrective_actions),
    ]
    return '\n'.join(lines) + '\n'


def crashout_text(record: CrashoutRecord) -> str:
    lines = [
        f'at: {timestamp(record)}',
        f'ticket: {ABSENT if record.ticket_key is None else record.ticket_key}',
        f'branch: {ABSENT if record.branch is None else record.branch}',
        f'severity: {record.severity}',
        f'verdict: {record.verdict}',
        'rant:',
        *(f'  {line}' for line in record.rant.split('\n')),
        'failures:',
        *(f'  - {failure}' for failure in record.failures),
        f'root_cause: {record.root_cause}',
        f'corrective_action: {record.corrective_action}',
        f'barked_back: {str(record.barked_back).lower()}',
    ]
    return '\n'.join(lines) + '\n'


def render_journaled(journaled: Journaled) -> JournalView:
    text = f'journaled crashout #{journaled.number}\n{duplicates_text(journaled.duplicates)}'
    return JournalView(text=text)


def render_stats(stats: CrashoutStats | None) -> JournalView:
    if stats is None:
        return JournalView(text=f'{SERENITY}\n')

    note = OLDER_LEFT_OUT if stats.older_left_out else ''
    return JournalView(text=patterns_text(stats) + note)


def render_last(record: CrashoutRecord | None) -> JournalView:
    if record is None:
        return JournalView(text=f'{NOTHING_JOURNALED}\n')

    return JournalView(text=crashout_text(record), entry=journaled_crashout(record))


def render_matches(matches: list[Match]) -> JournalView:
    text = ''.join(map(match_line, matches)) or NO_MATCHES
    found = tuple(
        SimilarMatch(kind=m.kind, reference=m.reference, text=m.text, overlap=m.overlap)
        for m in matches
    )
    return JournalView(text=text, matches=found)
