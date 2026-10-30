"""A non-ASCII file name reaches the churn report unquoted."""

import asyncio
import os
from typing import TYPE_CHECKING

import pytest
from mightymodels_mcp.review_signals.history import create_git_source, load_history
from mightymodels_mcp.review_signals.options import SignalsOptions
from mightymodels_mcp.review_signals.reports import code_churn

from tests.core.git.git_builders import run_git

if TYPE_CHECKING:
    from pathlib import Path

NAME = 'café.py'


@pytest.fixture
def clean_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [name for name in os.environ if name.startswith('GIT_')]:
        monkeypatch.delenv(name)


@pytest.mark.usefixtures('clean_git_environment')
def test_churn_lists_a_non_ascii_file_under_its_exact_name(tmp_path: Path) -> None:
    asyncio.run(run_git(tmp_path, 'init', '-q'))
    tmp_path.joinpath(NAME).write_text('a\n', encoding='utf-8')
    asyncio.run(run_git(tmp_path, 'add', NAME))
    asyncio.run(run_git(tmp_path, 'commit', '-q', '-m', 'add'))
    options = SignalsOptions()

    history = asyncio.run(load_history(options, create_git_source(tmp_path)))

    assert [signal.subject for signal in code_churn(history, options).signals] == [NAME]
