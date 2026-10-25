"""The files a ticket leaves for whoever picks it up.

The snapshot, a closing's archive, and the debug note whose presence says a debug is still live.
`HandoffFiles` holds the resolved state directory and hands out contained paths only.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives.value_types import ARCHIVES_DIRECTORY

from .paths import contained_in

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.primitives import Slug

HANDOFFS_DIRECTORY = 'handoffs'
SNAPSHOT_NAME = 'snapshot'
LIVE_DEBUG_FILE = 'whats-broken.md'


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordFiles:
    markdown: Path
    record: Path


@dataclass(slots=True, kw_only=True, frozen=True)
class HandoffFiles:
    state_directory: Path

    def snapshot(self, slug: Slug) -> RecordFiles:
        parts = (slug, HANDOFFS_DIRECTORY)
        return RecordFiles(
            markdown=contained_in(self.state_directory, *parts, f'{SNAPSHOT_NAME}.md'),
            record=contained_in(self.state_directory, *parts, f'{SNAPSHOT_NAME}.json'),
        )

    def archive(self, slug: Slug, repeat: int) -> RecordFiles:
        name = slug if repeat == 1 else f'{slug}-{repeat}'
        return RecordFiles(
            markdown=contained_in(self.state_directory, ARCHIVES_DIRECTORY, f'{name}.md'),
            record=contained_in(self.state_directory, ARCHIVES_DIRECTORY, f'{name}.json'),
        )

    def live_debug(self, slug: Slug) -> Path:
        return contained_in(self.state_directory, slug, LIVE_DEBUG_FILE)
