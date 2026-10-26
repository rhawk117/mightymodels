from datetime import UTC, date, datetime

from mightymodels_core.crashouts import CrashoutRecord, CrashoutStats, FailureLine, Journaled
from mightymodels_core.primitives import redact
from mightymodels_core.similarity.records import Duplicate, Match
from mightymodels_mcp.journal.views import (
    NO_MATCHES,
    NOTHING_JOURNALED,
    OLDER_LEFT_OUT,
    SERENITY,
    render_journaled,
    render_last,
    render_matches,
    render_stats,
)
from mightymodels_mcp.server.views import EXCERPT_LENGTH

AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def create_crashout(
    *,
    ticket: str | None = 'probe-ticket',
    branch: str | None = 'feat/probe',
    rant: str = 'it broke',
    failures: tuple[str, ...] = ('a failure',),
    barked_back: bool = True,
) -> CrashoutRecord:
    return CrashoutRecord(
        at=AT,
        ticket_key=ticket,
        branch=None if branch is None else redact(branch),
        severity='heated',
        verdict='split',
        rant=redact(rant),
        failures=tuple(map(redact, failures)),
        root_cause=redact('a cause'),
        corrective_action=redact('an action'),
        barked_back=barked_back,
    )


def create_match(text: str = 'same words', reference: str = '#1') -> Match:
    return Match(kind='crashout', reference=reference, text=redact(text), overlap=0.9)


def create_stats(*, older_left_out: bool = False) -> CrashoutStats:
    first = create_crashout()
    last = CrashoutRecord(
        at=datetime(2026, 1, 3, tzinfo=UTC),
        ticket_key=None,
        branch=None,
        severity='crashout',
        verdict='deserved',
        rant=redact('again'),
        failures=(redact('f2'),),
        root_cause=redact('c2'),
        corrective_action=redact('act 2'),
        barked_back=False,
    )
    return CrashoutStats(
        entries=2,
        severities=(('heated', 1), ('crashout', 1)),
        verdicts=(('split', 1), ('deserved', 1)),
        barked_back=1,
        first=first,
        last=last,
        failures=(
            FailureLine(
                day=date(2026, 1, 2),
                verdict='split',
                severity='heated',
                failure=redact('a failure'),
            ),
            FailureLine(
                day=date(2026, 1, 3), verdict='deserved', severity='crashout', failure=redact('f2')
            ),
        ),
        corrective_actions=('an action', 'act 2'),
        older_left_out=older_left_out,
    )


class TestJournaled:
    def test_names_the_number(self) -> None:
        view = render_journaled(Journaled(number=3, duplicates=()))

        assert view.text == 'journaled crashout #3\n'
        assert (view.entry, view.matches) == (None, ())

    def test_lists_a_duplicate(self) -> None:
        duplicate = Duplicate(written='#4', earlier=create_match())
        view = render_journaled(Journaled(number=4, duplicates=(duplicate,)))

        first, second = view.text.splitlines()
        assert first == 'journaled crashout #4'
        assert second == 'near-duplicate: #4 resembles crashout #1 (overlap 0.90): same words'


class TestStats:
    def test_empty_journal_is_serenity(self) -> None:
        view = render_stats(None)

        assert view.text == f'{SERENITY}\n'
        assert view.text.startswith(NOTHING_JOURNALED)

    def test_patterns_are_counted_and_listed(self) -> None:
        text = render_stats(create_stats()).text

        assert text.splitlines() == [
            'entries: 2',
            'severity: heated=1 crashout=1',
            'verdicts: split=1 deserved=1',
            'barked_back: 1/2',
            'first: 2026-01-02T03:04:05+00:00  last: 2026-01-03T00:00:00+00:00',
            '',
            'failures:',
            '  [2026-01-02 | split | heated] a failure',
            '  [2026-01-03 | deserved | crashout] f2',
            '',
            'standing corrective actions:',
            '  - an action',
            '  - act 2',
        ]

    def test_older_left_out_adds_the_note(self) -> None:
        view = render_stats(create_stats(older_left_out=True))

        assert view.text.endswith(OLDER_LEFT_OUT)
        assert not render_stats(create_stats()).text.endswith(OLDER_LEFT_OUT)


class TestLast:
    def test_empty_journal_says_so(self) -> None:
        view = render_last(None)

        assert view.text == f'{NOTHING_JOURNALED}\n'
        assert view.entry is None

    def test_entry_reads_a_line_per_field(self) -> None:
        record = create_crashout(rant='line one\nline two', failures=('f1', 'f2'))
        view = render_last(record)

        assert view.text.splitlines() == [
            'at: 2026-01-02T03:04:05+00:00',
            'ticket: probe-ticket',
            'branch: feat/probe',
            'severity: heated',
            'verdict: split',
            'rant:',
            '  line one',
            '  line two',
            'failures:',
            '  - f1',
            '  - f2',
            'root_cause: a cause',
            'corrective_action: an action',
            'barked_back: true',
        ]

    def test_absent_ticket_and_branch_read_none(self) -> None:
        lines = render_last(create_crashout(ticket=None, branch=None, barked_back=False))

        assert 'ticket: none' in lines.text
        assert 'branch: none' in lines.text
        assert lines.text.endswith('barked_back: false\n')

    def test_entry_fields_are_set(self) -> None:
        entry = render_last(create_crashout(failures=('f1', 'f2'))).entry

        assert entry is not None
        assert (entry.at, entry.ticket, entry.branch) == (
            '2026-01-02T03:04:05+00:00',
            'probe-ticket',
            'feat/probe',
        )
        assert (entry.severity, entry.verdict, entry.failures) == ('heated', 'split', ('f1', 'f2'))
        assert (entry.rant, entry.root_cause, entry.corrective_action, entry.barked_back) == (
            'it broke',
            'a cause',
            'an action',
            True,
        )


class TestMatches:
    def test_none_found(self) -> None:
        view = render_matches([])

        assert view.text == NO_MATCHES
        assert view.matches == ()

    def test_a_line_per_match_with_fields(self) -> None:
        view = render_matches([create_match(), create_match('other', '#2')])

        assert view.text.splitlines() == [
            'crashout #1 (overlap 0.90): same words',
            'crashout #2 (overlap 0.90): other',
        ]
        assert [(m.kind, m.reference, m.text, m.overlap) for m in view.matches] == [
            ('crashout', '#1', 'same words', 0.9),
            ('crashout', '#2', 'other', 0.9),
        ]

    def test_long_text_is_cut_by_the_excerpt(self) -> None:
        view = render_matches([create_match('w' * (EXCERPT_LENGTH + 30))])

        assert view.text.endswith(f'{"w" * EXCERPT_LENGTH}...\n')
        assert view.matches[0].text == 'w' * (EXCERPT_LENGTH + 30)
