"""The environment a command line run reads: the data directory and the project it starts in."""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def session_data_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_directory = tmp_path.joinpath('data')
    monkeypatch.setenv('MIGHTYMODELS_DATA_DIR', str(data_directory))
    return data_directory


@pytest.fixture
def project_outside_a_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project = tmp_path.joinpath('outside')
    project.mkdir()
    monkeypatch.setenv('CLAUDE_PROJECT_DIR', str(project))
    return project


@pytest.fixture
def no_session_data_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('MIGHTYMODELS_DATA_DIR', raising=False)
