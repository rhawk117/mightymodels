"""The session-start harness and its fixed moment, shared by the integration tests."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mightymodels_core.edge import PLUGIN_DATA_VARIABLE
from mightymodels_hooks.session_start import ENV_FILE_VARIABLE, SessionStartHandler

if TYPE_CHECKING:
    import io
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
