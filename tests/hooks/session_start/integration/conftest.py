"""A real git checkout, a data directory and the handler over them, with a clock the test sets."""

import io
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.edge import PLUGIN_DATA_VARIABLE
from mightymodels_hooks.session_start import ENV_FILE_VARIABLE, SessionStartHandler

from tests.core.git.git_builders import run_git
from tests.core.primitives.clock import create_fake_clock

if TYPE_CHECKING:
    from pathlib import Path

    from tests.core.primitives.clock import FakeClock

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionStartHarness:
    checkout: Path
    data_directory: Path
    env_file: Path
    clock: FakeClock
    stderr: io.StringIO

    def handler(self, data_directory: Path | None = None) -> SessionStartHandler:
        environ = {
            PLUGIN_DATA_VARIABLE: str(data_directory or self.data_directory),
            ENV_FILE_VARIABLE: str(self.env_file),
        }
        return SessionStartHandler(environ=environ, stderr=self.stderr, clock=self.clock)


@pytest.fixture
async def checkout(tmp_path: Path) -> Path:
    root = tmp_path.joinpath('checkout')
    root.mkdir()
    await run_git(root, 'init')
    return root


@pytest.fixture
def harness(checkout: Path, data_directory: Path, env_file: Path) -> SessionStartHarness:
    return SessionStartHarness(
        checkout=checkout,
        data_directory=data_directory,
        env_file=env_file,
        clock=create_fake_clock(NOW),
        stderr=io.StringIO(),
    )
