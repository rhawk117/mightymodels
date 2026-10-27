from datetime import timedelta
from typing import TYPE_CHECKING

from mightymodels_core.edge import export_line, open_state
from mightymodels_core.session_pointers import POINTER_RETENTION, SqliteSessionPointerRepository
from mightymodels_core.units_of_work import write_entry
from mightymodels_hooks.payloads import SessionStartPayload

from tests.core.primitives.clock import create_fake_clock
from tests.hooks.session_start.session_start_builders import NOW

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    from tests.hooks.session_start.session_start_builders import SessionStartHarness


class TestSessionStart:
    stale = NOW - POINTER_RETENTION - timedelta(days=1)
    fresh = NOW - timedelta(days=1)

    async def record_pointer(
        self, harness: SessionStartHarness, session_id: str, written_at: datetime
    ) -> None:
        async with open_state(harness.data_directory, harness.checkout) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                pointers = SqliteSessionPointerRepository(
                    unit=entry.unit,
                    repository_id=entry.repository_id,
                    clock=create_fake_clock(written_at),
                )
                pointers.record(session_id, 'ticket', 'some-slug')

    async def holds_pointer(self, harness: SessionStartHarness, session_id: str) -> bool:
        async with open_state(harness.data_directory, harness.checkout) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                pointers = SqliteSessionPointerRepository(
                    unit=entry.unit, repository_id=entry.repository_id, clock=harness.clock
                )
                return pointers.lookup(session_id) is not None

    async def test_pointers_older_than_the_retention_are_pruned(
        self, harness: SessionStartHarness
    ) -> None:
        await self.record_pointer(harness, 'stale', self.stale)
        await self.record_pointer(harness, 'fresh', self.fresh)
        await harness.handler().handle(SessionStartPayload(cwd=str(harness.checkout)))
        assert not await self.holds_pointer(harness, 'stale')
        assert await self.holds_pointer(harness, 'fresh')

    async def test_second_run_leaves_the_env_file_unchanged(
        self, harness: SessionStartHarness
    ) -> None:
        handler = harness.handler()
        await handler.handle(SessionStartPayload(cwd=str(harness.checkout)))
        await handler.handle(SessionStartPayload(cwd=str(harness.checkout)))
        assert harness.env_file.read_text(encoding='utf-8') == export_line(harness.data_directory)

    async def test_unopenable_database_still_exports_and_notes_it(
        self, harness: SessionStartHarness, tmp_path: Path
    ) -> None:
        blocker = tmp_path.joinpath('regular-file')
        blocker.write_text('', encoding='utf-8')
        data_directory = blocker.joinpath('data')
        output = await harness.handler(data_directory).handle(
            SessionStartPayload(cwd=str(harness.checkout))
        )
        assert output is None
        assert harness.env_file.read_text(encoding='utf-8') == export_line(data_directory)
        assert harness.stderr.getvalue().startswith('mightymodels-hooks: session-start:')
