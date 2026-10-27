"""Fixtures shared by the session-start unit and integration tests."""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    return tmp_path.joinpath('claude-env')


@pytest.fixture
def data_directory(tmp_path: Path) -> Path:
    return tmp_path.joinpath('plugin data')
