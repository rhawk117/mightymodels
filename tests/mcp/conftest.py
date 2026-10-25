"""The fixture every concept's e2e suite builds its server from."""

from typing import TYPE_CHECKING

import pytest

from tests.mcp.server.server_harness import create_server_harness

if TYPE_CHECKING:
    from pathlib import Path

    from tests.mcp.server.server_harness import ServerHarness


@pytest.fixture
def server_harness(tmp_path: Path) -> ServerHarness:
    return create_server_harness(tmp_path)
