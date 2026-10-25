"""Handoff file naming."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.workspace import workspace_at

from tests.core.workspace.workspace_builders import TICKET

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet
    from mightymodels_core.workspace import Workspace


@dataclass(slots=True, kw_only=True, frozen=True)
class ArchiveRepeat:
    name: str
    repeat: int
    archive_name: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def handoff_archive_repeat_cases() -> pytest.MarkDecorator:
    scenarios = [
        ArchiveRepeat(name='first', repeat=1, archive_name=TICKET),
        ArchiveRepeat(name='second', repeat=2, archive_name=f'{TICKET}-2'),
        ArchiveRepeat(name='eleventh', repeat=11, archive_name=f'{TICKET}-11'),
    ]
    return pytest.mark.parametrize('archived', [scenario.param for scenario in scenarios])


class TestHandoffFiles:
    @pytest.fixture
    def workspace(self, checkout: Path) -> Workspace:
        return workspace_at(checkout)

    @handoff_archive_repeat_cases()
    def test_an_archive_is_named_for_the_ticket_and_numbered_from_its_second(
        self, workspace: Workspace, archived: ArchiveRepeat
    ) -> None:
        files = workspace.handoffs.archive(TICKET, archived.repeat)

        assert [workspace.relative_to_root(files.markdown), files.record.name] == [
            f'.mightymodels/archives/{archived.archive_name}.md',
            f'{archived.archive_name}.json',
        ]

    def test_the_snapshot_and_the_debug_note_sit_in_the_ticket_directory(
        self, workspace: Workspace
    ) -> None:
        snapshot = workspace.handoffs.snapshot(TICKET)
        note = workspace.handoffs.live_debug(TICKET)

        assert [
            workspace.relative_to_root(path) for path in (snapshot.markdown, snapshot.record, note)
        ] == [
            f'.mightymodels/{TICKET}/handoffs/snapshot.md',
            f'.mightymodels/{TICKET}/handoffs/snapshot.json',
            f'.mightymodels/{TICKET}/whats-broken.md',
        ]
