"""A locked plugin database fails inside the hook, well before Claude Code would kill it."""

import sqlite3
import time
from contextlib import closing
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.edge import DATABASE_NAME

from tests.hooks.recorder.recorder_builders import ask_payload, two_answers

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from tests.hooks.recorder.recorder_builders import RecorderHarness

HANDLER_BUDGET_SECONDS = 6.0


@pytest.fixture
async def locked(harness: RecorderHarness) -> AsyncIterator[None]:
    await harness.stage_ticket()
    path = harness.data_directory.joinpath(DATABASE_NAME)
    with closing(sqlite3.connect(path, isolation_level=None)) as holder:
        holder.execute('BEGIN IMMEDIATE')
        yield
        holder.execute('ROLLBACK')


@pytest.mark.usefixtures('locked')
class TestLockedDatabase:
    async def test_the_recorder_gives_up_inside_the_hook_timeout(
        self, harness: RecorderHarness
    ) -> None:
        started = time.monotonic()
        output = await harness.record(ask_payload(two_answers()))
        elapsed = time.monotonic() - started
        assert output is None
        assert elapsed < HANDLER_BUDGET_SECONDS
        assert harness.stderr.getvalue() != ''
