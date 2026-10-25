"""What the investigation tools return, and the texts.

Core returns records and no text, so each function takes core's result and returns the text. The
ledger and the knowns show live entries only, and the ledger ends with the next questions of the
latest round, since an earlier round's were either answered or dropped. The knowns table says of
each entry whether it was stored at the HEAD the repository is at now, `current`, or at another,
`lead`: a lead is checked again before anyone relies on it.
"""

from itertools import chain
from typing import TYPE_CHECKING

from mightymodels_core.investigations.records import INVESTIGATIONS_LISTED
from mightymodels_core.primitives import short_head
from pydantic import BaseModel, ConfigDict

from mightymodels_mcp.review.views import duplicates_text

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from mightymodels_core.investigations import (
        Added,
        KnownRow,
        Knowns,
        LatestRound,
        Ledger,
        LedgerRecord,
        Started,
    )
    from mightymodels_core.primitives import Latest
    from mightymodels_core.vocabulary.investigations import EntryKind

SECTION_TITLES: tuple[tuple[EntryKind, str], ...] = (
    ('known', 'Knowns'),
    ('open', 'Open'),
    ('decision', 'Decisions'),
    ('resource', 'Resources'),
)
NEXT_TITLE = 'Next'
TABLE_HEADER = (
    '| entry | kind | claim | cite | source | round | status |',
    '|---|---|---|---|---|---|---|',
)
NO_INVESTIGATIONS = 'no investigations\n'
OLDER_LEFT_OUT = (
    f'older investigations are left out: these are the latest {INVESTIGATIONS_LISTED.rows}\n'
)


class InvestigationView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    investigation_id: str | None = None


def render_started(started: Started) -> InvestigationView:
    text = f'started {started.investigation}\n{duplicates_text(started.duplicates)}'
    return InvestigationView(text=text, investigation_id=started.investigation)


def render_added(added: Added) -> InvestigationView:
    saved = ' '.join(f'e{seq}' for seq in added.seqs)
    text = (
        f'saved {saved} to {added.investigation} ({added.redactions} redacted)\n'
        f'{duplicates_text(added.duplicates)}'
    )
    return InvestigationView(text=text, investigation_id=added.investigation)


def entry_line(record: LedgerRecord) -> str:
    cite = '' if record.cite is None else f' [{record.cite}]'
    return f'- e{record.seq}: {record.text}{cite} ({record.source}, round {record.round})'


def section_lines(title: str, records: Iterable[LedgerRecord]) -> list[str]:
    return [f'### {title}', *map(entry_line, records), '']


def ledger_text(ledger: Ledger) -> str:
    sections = (section_lines(title, ledger.live_of_kind(kind)) for kind, title in SECTION_TITLES)
    lines = [
        f'## Ledger, round {ledger.latest_round}',
        f'Target: {ledger.investigation.target} ({ledger.investigation.kind})',
        '',
        *chain.from_iterable(sections),
        *section_lines(NEXT_TITLE, ledger.next_questions),
    ]
    return '\n'.join(lines).rstrip() + '\n'


def render_ledger(ledger: Ledger) -> InvestigationView:
    return InvestigationView(text=ledger_text(ledger), investigation_id=ledger.key)


def table_cell(text: str | None) -> str:
    return ('' if text is None else text).replace('|', '\\|')


def table_row(row: KnownRow) -> str:
    record = row.record
    cells = (
        f'e{record.seq}',
        record.kind,
        table_cell(record.text),
        table_cell(record.cite),
        record.source,
        str(record.round),
        row.status,
    )
    return '| ' + ' | '.join(cells) + ' |'


def knowns_text(knowns: Knowns) -> str:
    more = f'{knowns.hidden} more rows; ask again with a larger limit'
    lines = [
        f'## Knowns table, {knowns.investigation} at HEAD {short_head(knowns.head)}',
        *TABLE_HEADER,
        *map(table_row, knowns.rows),
        *([more] if knowns.hidden > 0 else []),
    ]
    return '\n'.join(lines) + '\n'


def render_knowns(knowns: Knowns) -> InvestigationView:
    return InvestigationView(text=knowns_text(knowns), investigation_id=knowns.investigation)


def render_listing(listed: Latest[LatestRound]) -> InvestigationView:
    lines: Sequence[str] = [
        f'{investigation}\tround {latest}\n' for investigation, latest in listed.rows
    ]
    note = OLDER_LEFT_OUT if listed.older_left_out else ''
    return InvestigationView(text=(''.join(lines) or NO_INVESTIGATIONS) + note)
