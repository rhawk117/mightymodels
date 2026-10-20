"""One work tree to start in, one plugin data directory and one directory that is no work tree."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import anyio
import pytest

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True, kw_only=True, frozen=True)
class StartHarness:
    toplevel: Path
    subdirectory: Path
    data_directory: Path
    outside: Path


@pytest.fixture
async def start(tmp_path: Path) -> StartHarness:
    toplevel = tmp_path.joinpath('repository').resolve()
    subdirectory = toplevel.joinpath('src', 'deep')
    subdirectory.mkdir(parents=True)
    await anyio.run_process(['git', 'init', '--quiet', str(toplevel)])
    outside = tmp_path.joinpath('outside')
    outside.mkdir()
    return StartHarness(
        toplevel=toplevel,
        subdirectory=subdirectory,
        data_directory=tmp_path.joinpath('data', 'plugin'),
        outside=outside,
    )
