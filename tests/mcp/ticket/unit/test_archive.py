from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import Slug, redact
from mightymodels_core.ticket_closing import ArchiveRecord
from mightymodels_core.tickets import Tracker
from mightymodels_core.workspace import workspace_at
from mightymodels_mcp.ticket.archive import free_archive_files, write_archive

from tests.core.ticket_closing.closing_builders import create_closing

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.workspace import RecordFiles, Workspace

SLUG = Slug('closing-subject')
DECISION_LIMIT = 4


def create_record() -> ArchiveRecord:
    return ArchiveRecord(
        slug=SLUG,
        tracker=Tracker(issue=42, jira=None),
        summary=redact('a summary'),
        investigations=(),
        closing=create_closing('Retry queue drains'),
        tasks={},
        verification=(),
        decisions=(),
        review=None,
    )


class TestArchiveFiles:
    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Workspace:
        return workspace_at(tmp_path)

    @pytest.fixture
    def first_slot(self, workspace: Workspace) -> RecordFiles:
        files = workspace.handoffs.archive(SLUG, 1)
        files.markdown.parent.mkdir(parents=True)
        return files

    def test_failed_record_write_leaves_no_markdown(self, first_slot: RecordFiles) -> None:
        first_slot.record.mkdir()

        with pytest.raises(OSError, match='directory'):
            write_archive(first_slot, create_record(), decision_limit=DECISION_LIMIT)

        assert not first_slot.markdown.exists()

    def test_write_creates_both_files(self, first_slot: RecordFiles) -> None:
        write_archive(first_slot, create_record(), decision_limit=DECISION_LIMIT)

        assert first_slot.record.is_file()
        assert first_slot.markdown.is_file()

    @pytest.mark.parametrize('existing', ['markdown', 'record'])
    def test_half_written_slot_is_skipped(
        self, workspace: Workspace, first_slot: RecordFiles, existing: str
    ) -> None:
        getattr(first_slot, existing).write_text('partial', encoding='utf-8')

        free = free_archive_files(workspace, SLUG)

        assert free == workspace.handoffs.archive(SLUG, 2)

    def test_empty_workspace_offers_the_first_slot(
        self, workspace: Workspace, first_slot: RecordFiles
    ) -> None:
        assert free_archive_files(workspace, SLUG) == first_slot
