"""The values a ledger computes from its entries, and the ledgers a ticket links."""

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.investigations import (
    KnownsSelection,
    UnknownInvestigationError,
    entry_status,
    ledger_of,
    linked_ledgers,
    recorded_ledger,
)

from tests.core.investigations.investigation_builders import (
    FIRST,
    HEAD,
    SECOND,
    UNADDED,
    Case,
    create_entry,
    create_investigation,
    create_ledger,
)

if TYPE_CHECKING:
    from mightymodels_core.investigations import EntryStatus, LedgerRecord
    from mightymodels_core.schemas.investigations import EntryKind

    from tests.core.investigations.investigation_builders import InvestigationHarness


def create_record(
    seq: int,
    kind: EntryKind = 'known',
    *,
    round_number: int = 1,
    supersedes: tuple[int, ...] = (),
    head: str | None = HEAD,
) -> LedgerRecord:
    entry = create_entry(seq, round_number=round_number)
    return replace(entry, kind=kind, supersedes=supersedes, head=head)


def knowns_selection_cases() -> pytest.MarkDecorator:
    cases = [
        Case(name='default-skips-next', given=KnownsSelection(), expected=[1, 2, 3, 4]),
        Case(
            name='selected-kinds',
            given=KnownsSelection(kinds=('decision', 'next')),
            expected=[3, 5],
        ),
        Case(name='limit-keeps-the-first', given=KnownsSelection(limit=2), expected=[1, 2]),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


MIXED = (
    create_record(1, 'known'),
    create_record(2, 'open'),
    create_record(3, 'decision'),
    create_record(4, 'resource'),
    create_record(5, 'next'),
)


class TestLedger:
    def test_an_empty_ledger_numbers_from_one_and_is_at_round_zero(self) -> None:
        ledger = create_ledger()
        assert (ledger.next_seq, ledger.latest_round) == (1, 0)

    def test_the_next_seq_follows_the_entries(self) -> None:
        assert create_ledger(*MIXED).next_seq == 6

    def test_the_latest_round_is_the_highest_round(self) -> None:
        ledger = create_ledger(create_record(1, round_number=1), create_record(2, round_number=3))
        assert ledger.latest_round == 3

    def test_a_superseded_entry_is_not_live(self) -> None:
        ledger = create_ledger(create_record(1), create_record(2, supersedes=(1,)))
        assert [record.seq for record in ledger.live] == [2]

    def test_a_superseded_entry_stays_supersedable(self) -> None:
        ledger = create_ledger(create_record(1), create_record(2, supersedes=(1,)))
        assert ledger.supersedable == {1, 2}

    def test_the_origin_names_the_investigation_and_the_seq(self) -> None:
        ledger = create_ledger(create_record(1))
        assert ledger.origin_of(ledger.records[0]) == f'{FIRST} e1'

    def test_next_questions_are_the_live_ones_of_the_latest_round(self) -> None:
        ledger = create_ledger(
            create_record(1, 'next', round_number=1),
            create_record(2, 'next', round_number=2),
            create_record(3, 'next', round_number=2, supersedes=(2,)),
            create_record(4, 'next', round_number=2),
            create_record(5, 'known', round_number=2),
        )
        assert [record.seq for record in ledger.next_questions] == [3, 4]

    def test_sections_hold_the_live_entries_per_kind_in_order(self) -> None:
        ledger = create_ledger(*MIXED, create_record(6, 'known', supersedes=(1,)))
        assert [
            (section.kind, [r.seq for r in section.records]) for section in ledger.sections
        ] == [
            ('known', [6]),
            ('open', [2]),
            ('decision', [3]),
            ('resource', [4]),
        ]


class TestKnowns:
    heads = st.sampled_from((HEAD, 'def5678', None))

    @given(stored=heads, asked=heads)
    @example(stored=HEAD, asked=HEAD)
    @example(stored='def5678', asked=HEAD)
    @example(stored=HEAD, asked=None)
    @example(stored=None, asked=HEAD)
    @example(stored=None, asked=None)
    def test_entry_status_at_head(self, stored: str | None, asked: str | None) -> None:
        expected: EntryStatus = 'current' if asked is not None and asked == stored else 'lead'
        assert entry_status(create_record(1, head=stored), asked) == expected

    @knowns_selection_cases()
    def test_knowns_selection(self, case: Case[KnownsSelection, list[int]]) -> None:
        knowns = create_ledger(*MIXED).knowns(case.given, HEAD)
        assert [row.record.seq for row in knowns.rows] == case.expected

    def test_knowns_hides_the_rows_past_the_limit_and_counts_them(self) -> None:
        knowns = create_ledger(*MIXED).knowns(KnownsSelection(limit=3), HEAD)
        assert (len(knowns.rows), knowns.hidden) == (3, 1)

    def test_knowns_within_the_limit_hide_nothing(self) -> None:
        knowns = create_ledger(*MIXED).knowns(KnownsSelection(limit=4), HEAD)
        assert knowns.hidden == 0

    def test_knowns_leave_out_superseded_entries(self) -> None:
        ledger = create_ledger(create_record(1), create_record(2, supersedes=(1,)))
        assert [row.record.seq for row in ledger.knowns(KnownsSelection(), HEAD).rows] == [2]

    def test_knowns_mark_each_row_against_the_head(self) -> None:
        ledger = create_ledger(create_record(1, head=HEAD), create_record(2, head='def5678'))
        assert [row.status for row in ledger.knowns(KnownsSelection(), HEAD).rows] == [
            'current',
            'lead',
        ]

    def test_knowns_with_no_head_make_every_row_a_lead(self) -> None:
        knowns = create_ledger(*MIXED).knowns(KnownsSelection(), None)
        assert {row.status for row in knowns.rows} == {'lead'}


class TestReadLedgers:
    def test_an_unadded_investigation_has_no_ledger(
        self, fake_harness: InvestigationHarness
    ) -> None:
        assert ledger_of(fake_harness.investigations, UNADDED) is None

    def test_an_unknown_investigation_is_refused(self, fake_harness: InvestigationHarness) -> None:
        with pytest.raises(UnknownInvestigationError):
            recorded_ledger(fake_harness.investigations, UNADDED)

    def test_an_investigation_without_entries_has_an_empty_ledger(
        self, fake_harness: InvestigationHarness
    ) -> None:
        fake_harness.investigations.add_investigation(create_investigation(FIRST))
        ledger = recorded_ledger(fake_harness.investigations, FIRST)
        assert (ledger.key, ledger.records) == (FIRST, ())

    def test_a_ledger_holds_the_entries_in_seq_order(
        self, fake_harness: InvestigationHarness
    ) -> None:
        fake_harness.investigations.add_investigation(create_investigation(FIRST))
        fake_harness.investigations.append(FIRST, [create_entry(2), create_entry(1)])
        ledger = recorded_ledger(fake_harness.investigations, FIRST)
        assert [record.seq for record in ledger.records] == [1, 2]

    def test_linked_ledgers_keep_the_link_order_collapse_duplicates_and_name_the_missing(
        self, fake_harness: InvestigationHarness
    ) -> None:
        for key in (FIRST, SECOND):
            fake_harness.investigations.add_investigation(create_investigation(key))
        linked = linked_ledgers(
            fake_harness.investigations, [SECOND, UNADDED, FIRST, SECOND, UNADDED]
        )
        assert [ledger.key for ledger in linked.ledgers] == [SECOND, FIRST]
        assert linked.missing == (UNADDED,)

    def test_no_links_give_no_ledgers(self, fake_harness: InvestigationHarness) -> None:
        linked = linked_ledgers(fake_harness.investigations, [])
        assert (linked.ledgers, linked.missing) == ((), ())
