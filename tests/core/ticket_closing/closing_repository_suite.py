"""The closing repository contract, written once for every tier to subclass."""

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.ticket_closing import ClosingRepository

from tests.core.ticket_closing.closing_builders import create_closing

if TYPE_CHECKING:
    from tests.core.ticket_closing.closing_builders import ClosingHarness


class ClosingRepositoryContract:
    class TestImplementations:
        def test_repository_satisfies_the_protocol(self, harness: ClosingHarness) -> None:
            assert isinstance(harness.repository, ClosingRepository)

    class TestRecordClosing:
        closing = create_closing('shipped the port')

        @pytest.fixture
        def recorded(self, harness: ClosingHarness) -> ClosingHarness:
            harness.repository.record_closing(harness.ticket_id, self.closing)
            return harness

        def test_closing_is_none_before_recording(self, harness: ClosingHarness) -> None:
            assert harness.repository.closing(harness.ticket_id) is None

        def test_recorded_closing_is_read_back(self, recorded: ClosingHarness) -> None:
            assert recorded.repository.closing(recorded.ticket_id) == self.closing

        def test_recording_again_replaces_the_closing(self, recorded: ClosingHarness) -> None:
            later = create_closing('shipped the follow-up', closed_day=9)

            recorded.repository.record_closing(recorded.ticket_id, later)

            assert recorded.repository.closing(recorded.ticket_id) == later

        def test_closing_without_head_or_gotchas_is_read_back(
            self, harness: ClosingHarness
        ) -> None:
            bare = replace(self.closing, head=None, pr=None, gotchas=())

            harness.repository.record_closing(harness.ticket_id, bare)

            assert harness.repository.closing(harness.ticket_id) == bare
