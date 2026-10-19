"""Every investigation repository case runs against the sqlite store and the fake."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.investigations import (
    DuplicateEntryError,
    DuplicateInvestigationError,
    InvestigationNotFoundError,
    InvestigationRepository,
)
from mightymodels_core.investigations.records import ENTRIES, INVESTIGATIONS_LISTED
from mightymodels_core.investigations.tests.fakes import (
    FakeInvestigationRepository,
    InvestigationLedger,
)
from mightymodels_core.primitives import Slug, WriteLimitError

from .conftest import FIRST, SECOND, UNADDED, create_entry, create_investigation

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from .conftest import InvestigationHarness


@dataclass(slots=True, kw_only=True, frozen=True)
class DuplicateSeqCase:
    name: str
    batch_seqs: tuple[int, ...]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def duplicate_seq_cases() -> pytest.MarkDecorator:
    cases = [
        DuplicateSeqCase(name='held-seq', batch_seqs=(3, 1)),
        DuplicateSeqCase(name='twice-in-batch', batch_seqs=(3, 3)),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


class TestImplementations:
    def test_fake_satisfies_the_protocol(self) -> None:
        fake = FakeInvestigationRepository(ledger=InvestigationLedger())

        assert isinstance(fake, InvestigationRepository)

    def test_repository_satisfies_the_protocol(self, harness: InvestigationHarness) -> None:
        assert isinstance(harness.investigations, InvestigationRepository)


class TestAddInvestigation:
    @pytest.fixture
    def added(self, harness: InvestigationHarness) -> InvestigationHarness:
        harness.investigations.add_investigation(create_investigation(FIRST))
        return harness

    def test_unadded_key_is_unrecorded(self, harness: InvestigationHarness) -> None:
        assert harness.investigations.unrecorded([FIRST]) == [FIRST]

    def test_added_key_is_recorded_without_entries(self, added: InvestigationHarness) -> None:
        assert added.investigations.unrecorded([FIRST]) == []
        assert not added.investigations.has_entries(FIRST)

    def test_key_the_repository_holds_is_refused(self, added: InvestigationHarness) -> None:
        with pytest.raises(DuplicateInvestigationError):
            added.investigations.add_investigation(create_investigation(FIRST))


class TestUnrecorded:
    @pytest.fixture
    def added(self, harness: InvestigationHarness) -> InvestigationHarness:
        harness.investigations.add_investigation(create_investigation(FIRST))
        harness.investigations.add_investigation(create_investigation(SECOND))
        return harness

    def test_keys_never_added_are_returned_in_the_order_given(
        self, added: InvestigationHarness
    ) -> None:
        asked = [UNADDED, FIRST, Slug('also-never-added'), SECOND]

        assert added.investigations.unrecorded(asked) == [UNADDED, Slug('also-never-added')]

    def test_no_keys_asked_returns_none(self, added: InvestigationHarness) -> None:
        assert added.investigations.unrecorded([]) == []


class TestAppend:
    uncited = replace(create_entry(1), cite=None, head=None)

    @pytest.fixture
    def added(self, harness: InvestigationHarness) -> InvestigationHarness:
        harness.investigations.add_investigation(create_investigation(FIRST))
        harness.investigations.add_investigation(create_investigation(SECOND))
        return harness

    @pytest.fixture
    def stocked(self, added: InvestigationHarness) -> InvestigationHarness:
        added.investigations.append(FIRST, [create_entry(1), create_entry(2)])
        return added

    def test_no_entries_are_held_before_an_append(self, added: InvestigationHarness) -> None:
        assert added.investigations.entries(FIRST) == []

    def test_entries_of_an_unadded_key_are_empty(self, added: InvestigationHarness) -> None:
        assert added.investigations.entries(UNADDED) == []
        assert not added.investigations.has_entries(UNADDED)

    def test_appended_entries_are_read_back_ordered_by_seq(
        self, added: InvestigationHarness
    ) -> None:
        added.investigations.append(FIRST, [create_entry(2), create_entry(1)])

        assert added.investigations.entries(FIRST) == [create_entry(1), create_entry(2)]

    def test_entry_without_a_cite_is_read_back(self, added: InvestigationHarness) -> None:
        added.investigations.append(FIRST, [self.uncited])

        assert added.investigations.entries(FIRST) == [self.uncited]

    def test_an_append_extends_the_entries_held(self, stocked: InvestigationHarness) -> None:
        stocked.investigations.append(FIRST, [create_entry(3)])

        seqs = [entry.seq for entry in stocked.investigations.entries(FIRST)]
        assert seqs == [1, 2, 3]

    def test_entries_exist_after_an_append(self, stocked: InvestigationHarness) -> None:
        assert stocked.investigations.has_entries(FIRST)

    def test_entries_of_another_investigation_are_not_read(
        self, stocked: InvestigationHarness
    ) -> None:
        assert stocked.investigations.entries(SECOND) == []
        assert not stocked.investigations.has_entries(SECOND)

    def test_another_investigation_may_reuse_a_seq(self, stocked: InvestigationHarness) -> None:
        stocked.investigations.append(SECOND, [create_entry(1)])

        assert len(stocked.investigations.entries(SECOND)) == 1


class TestAppendRefusals:
    @pytest.fixture
    def stocked(self, harness: InvestigationHarness) -> InvestigationHarness:
        harness.investigations.add_investigation(create_investigation(FIRST))
        harness.investigations.append(FIRST, [create_entry(1), create_entry(2)])
        return harness

    def test_entry_for_an_unadded_key_is_refused(self, stocked: InvestigationHarness) -> None:
        with pytest.raises(InvestigationNotFoundError):
            stocked.investigations.append(UNADDED, [create_entry(1)])

    @duplicate_seq_cases()
    def test_duplicate_seq_is_refused(
        self, stocked: InvestigationHarness, case: DuplicateSeqCase
    ) -> None:
        batch = [create_entry(seq) for seq in case.batch_seqs]

        with pytest.raises(DuplicateEntryError):
            stocked.investigations.append(FIRST, batch)

    @duplicate_seq_cases()
    def test_refused_batch_stores_none_of_it(
        self, stocked: InvestigationHarness, case: DuplicateSeqCase
    ) -> None:
        batch = [create_entry(seq) for seq in case.batch_seqs]

        with pytest.raises(DuplicateEntryError):
            stocked.investigations.append(FIRST, batch)

        seqs = [entry.seq for entry in stocked.investigations.entries(FIRST)]
        assert seqs == [1, 2]


class TestLatestRounds:
    @pytest.fixture
    def ledgered(self, harness: InvestigationHarness) -> InvestigationHarness:
        for key in (FIRST, SECOND, UNADDED):
            harness.investigations.add_investigation(create_investigation(key))
        harness.investigations.append(FIRST, [create_entry(1), create_entry(2, round_number=3)])
        harness.investigations.append(SECOND, [create_entry(1, round_number=2)])
        return harness

    def test_no_investigation_has_a_round_before_an_append(
        self, harness: InvestigationHarness
    ) -> None:
        harness.investigations.add_investigation(create_investigation(FIRST))

        latest = harness.investigations.latest_rounds()

        assert latest.rows == ()
        assert not latest.older_left_out

    def test_each_investigation_with_entries_reports_its_highest_round(
        self, ledgered: InvestigationHarness
    ) -> None:
        latest = ledgered.investigations.latest_rounds()

        assert latest.rows == ((FIRST, 3), (SECOND, 2))
        assert not latest.older_left_out


class TestListingCap:
    listed = INVESTIGATIONS_LISTED.rows

    @pytest.fixture
    def crowded(self, harness: InvestigationHarness) -> InvestigationHarness:
        for number in range(self.listed + 1):
            key = Slug(f'look-{number:03}')
            harness.investigations.add_investigation(create_investigation(key))
            harness.investigations.append(key, [create_entry(1)])
        return harness

    def test_newest_investigations_are_kept_oldest_first(
        self, crowded: InvestigationHarness
    ) -> None:
        latest = crowded.investigations.latest_rounds()

        keys = [key for key, _ in latest.rows]
        assert keys == [Slug(f'look-{number:03}') for number in range(1, self.listed + 1)]
        assert latest.older_left_out


class TestEntryCap:
    held_entries = ENTRIES.rows

    @pytest.fixture
    def full_harness(self, harness: InvestigationHarness) -> InvestigationHarness:
        harness.investigations.add_investigation(create_investigation(FIRST))
        entries = [create_entry(seq) for seq in range(1, self.held_entries + 1)]
        harness.investigations.append(FIRST, entries)
        return harness

    def test_entries_at_the_cap_are_read_back(self, full_harness: InvestigationHarness) -> None:
        assert len(full_harness.investigations.entries(FIRST)) == self.held_entries

    def test_append_past_the_cap_is_refused(self, full_harness: InvestigationHarness) -> None:
        with pytest.raises(WriteLimitError):
            full_harness.investigations.append(FIRST, [create_entry(self.held_entries + 1)])

    def test_refused_append_stores_none_of_it(self, full_harness: InvestigationHarness) -> None:
        batch = [create_entry(self.held_entries + 1), create_entry(self.held_entries + 2)]

        with pytest.raises(WriteLimitError):
            full_harness.investigations.append(FIRST, batch)

        assert len(full_harness.investigations.entries(FIRST)) == self.held_entries
