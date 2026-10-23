"""Every crashout repository case runs against the sqlite store and the fake."""

from typing import TYPE_CHECKING

from mightymodels_core.crashouts import JOURNAL_WINDOW, CrashoutRepository

from tests.core.crashouts.conftest import create_crashout
from tests.core.crashouts.fakes import FakeCrashoutRepository

if TYPE_CHECKING:
    from tests.core.crashouts.conftest import CrashoutHarness


class TestImplementations:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeCrashoutRepository(), CrashoutRepository)

    def test_repository_satisfies_the_protocol(self, harness: CrashoutHarness) -> None:
        assert isinstance(harness.crashouts, CrashoutRepository)


class TestJournal:
    def test_first_crashout_is_number_one(self, harness: CrashoutHarness) -> None:
        assert harness.crashouts.journal(create_crashout(0)) == 1

    def test_numbers_count_the_journal(self, journaled: CrashoutHarness) -> None:
        assert journaled.crashouts.journal(create_crashout(2)) == 3

    def test_number_counts_past_the_read_window(self, overfull: CrashoutHarness) -> None:
        assert overfull.crashouts.journal(create_crashout(0)) == JOURNAL_WINDOW.rows + 2


class TestLatestCrashout:
    def test_empty_journal_has_none(self, harness: CrashoutHarness) -> None:
        assert harness.crashouts.latest_crashout() is None

    def test_newest_crashout_is_read_back(self, journaled: CrashoutHarness) -> None:
        assert journaled.crashouts.latest_crashout() == create_crashout(1)

    def test_absent_branch_reads_back_absent(self, branchless: CrashoutHarness) -> None:
        latest = branchless.crashouts.latest_crashout()

        assert latest is not None
        assert latest.branch is None


class TestLatestCrashouts:
    def test_empty_journal_has_no_rows(self, harness: CrashoutHarness) -> None:
        latest = harness.crashouts.latest_crashouts()

        assert latest.rows == ()
        assert not latest.older_left_out

    def test_rows_are_oldest_first(self, journaled: CrashoutHarness) -> None:
        latest = journaled.crashouts.latest_crashouts()

        assert latest.rows == (create_crashout(0), create_crashout(1))
        assert not latest.older_left_out

    def test_window_keeps_the_newest_rows(self, overfull: CrashoutHarness) -> None:
        latest = overfull.crashouts.latest_crashouts()

        assert len(latest.rows) == JOURNAL_WINDOW.rows
        assert latest.rows[0] == create_crashout(1)
        assert latest.rows[-1] == create_crashout(JOURNAL_WINDOW.rows)
        assert latest.older_left_out
