from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mightymodels_core.investigations import (
    Added,
    InvestigationRecord,
    KnownRow,
    Knowns,
    KnownsSelection,
    Ledger,
    LedgerRecord,
    Started,
)
from mightymodels_core.primitives import Latest, Slug, redact
from mightymodels_core.similarity.records import Duplicate, Match
from mightymodels_mcp.investigation.views import (
    NO_INVESTIGATIONS,
    OLDER_LEFT_OUT,
    render_added,
    render_knowns,
    render_ledger,
    render_listing,
    render_started,
)

if TYPE_CHECKING:
    from mightymodels_core.vocabulary.investigations import EntryKind

KEY = Slug('20260101-probe')
AT = datetime(2026, 1, 1, tzinfo=UTC)


def create_record(
    seq: int,
    *,
    kind: EntryKind = 'known',
    text: str = 'a fact',
    round_number: int = 1,
    cite: str | None = 'a.py:1',
    supersedes: tuple[int, ...] = (),
    head: str | None = 'abc',
) -> LedgerRecord:
    return LedgerRecord(
        seq=seq,
        round=round_number,
        kind=kind,
        text=redact(text),
        source='code-scout',
        cite=None if cite is None else redact(cite),
        supersedes=supersedes,
        at=AT,
        head=head,
    )


def create_ledger(*records: LedgerRecord) -> Ledger:
    investigation = InvestigationRecord(key=KEY, target=redact('why it fails'), kind='behavior')
    return Ledger(investigation=investigation, records=records)


def create_duplicate() -> Duplicate:
    earlier = Match(kind='ledger-entry', reference='old e1', text=redact('same'), overlap=0.9)
    return Duplicate(written=f'{KEY} e2', earlier=earlier)


class TestStartedAndAdded:
    def test_started_names_the_investigation(self) -> None:
        view = render_started(Started(investigation=KEY, duplicates=()))

        assert view.text == f'started {KEY}\n'
        assert view.investigation_id == KEY

    def test_started_lists_a_duplicate(self) -> None:
        view = render_started(Started(investigation=KEY, duplicates=(create_duplicate(),)))

        assert view.text.splitlines()[1].startswith(f'near-duplicate: {KEY} e2 resembles')

    def test_added_lists_the_entries_and_redactions(self) -> None:
        added = Added(investigation=KEY, seqs=(2, 3), redactions=1, duplicates=())

        view = render_added(added)

        assert view.text == f'saved e2 e3 to {KEY} (1 redacted)\n'
        assert view.investigation_id == KEY

    def test_added_lists_a_duplicate(self) -> None:
        added = Added(investigation=KEY, seqs=(2,), redactions=0, duplicates=(create_duplicate(),))

        assert 'near-duplicate:' in render_added(added).text


class TestLedger:
    def test_sections_show_live_entries_and_the_latest_next_questions(self) -> None:
        ledger = create_ledger(
            create_record(1, text='old fact'),
            create_record(2, text='new fact', supersedes=(1,), round_number=2),
            create_record(3, kind='open', text='what?', cite=None),
            create_record(4, kind='next', text='stale ask', round_number=1),
            create_record(5, kind='next', text='fresh ask', round_number=2),
        )

        view = render_ledger(ledger)

        assert view.investigation_id == KEY
        assert view.text == (
            '## Ledger, round 2\n'
            'Target: why it fails (behavior)\n'
            '\n'
            '### Knowns\n'
            '- e2: new fact [a.py:1] (code-scout, round 2)\n'
            '\n'
            '### Open\n'
            '- e3: what? (code-scout, round 1)\n'
            '\n'
            '### Decisions\n'
            '\n'
            '### Resources\n'
            '\n'
            '### Next\n'
            '- e5: fresh ask [a.py:1] (code-scout, round 2)\n'
        )


class TestKnowns:
    def test_rows_show_status_and_escape_pipes(self) -> None:
        current = create_record(1, text='a | b', head='abc')
        lead = create_record(2, cite=None, head='def')
        ledger = create_ledger(current, lead)

        view = render_knowns(ledger.knowns(selection(), 'abc'))

        assert view.text == (
            f'## Knowns table, {KEY} at HEAD abc\n'
            '| entry | kind | claim | cite | source | round | status |\n'
            '|---|---|---|---|---|---|---|\n'
            '| e1 | known | a \\| b | a.py:1 | code-scout | 1 | current |\n'
            '| e2 | known | a fact |  | code-scout | 1 | lead |\n'
        )

    def test_a_limit_cuts_the_table_and_says_how_many_are_hidden(self) -> None:
        ledger = create_ledger(*(create_record(seq) for seq in (1, 2, 3)))

        text = render_knowns(ledger.knowns(selection(limit=1), None)).text

        assert text.splitlines()[0] == f'## Knowns table, {KEY} at HEAD unknown'
        assert text.count('| code-scout |') == 1
        assert text.endswith('2 more rows; ask again with a larger limit\n')

    def test_a_row_is_built_from_core_rows(self) -> None:
        record = create_record(1)
        knowns = Knowns(
            investigation=KEY, head='abc', rows=(KnownRow(record=record, status='lead'),), hidden=0
        )

        assert render_knowns(knowns).text.splitlines()[-1].endswith('| lead |')


class TestListing:
    def test_without_investigations_says_so(self) -> None:
        view = render_listing(Latest(rows=(), older_left_out=False))

        assert view.text == NO_INVESTIGATIONS
        assert view.investigation_id is None

    def test_rows_show_the_latest_round(self) -> None:
        view = render_listing(Latest(rows=((KEY, 2), (Slug('b'), 0)), older_left_out=False))

        assert view.text == f'{KEY}\tround 2\nb\tround 0\n'

    def test_older_ones_left_out_are_noted(self) -> None:
        view = render_listing(Latest(rows=((KEY, 1),), older_left_out=True))

        assert view.text == f'{KEY}\tround 1\n{OLDER_LEFT_OUT}'


def selection(limit: int = 40) -> KnownsSelection:
    return KnownsSelection(limit=limit)
