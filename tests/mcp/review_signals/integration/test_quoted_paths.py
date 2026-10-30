"""Odd file names and pathspec-shaped targets reach the churn report as they are."""

import asyncio
import os
import sys
from pathlib import Path

import pytest
from mightymodels_core.git import GitCommand
from mightymodels_core.process import SubprocessRunner
from mightymodels_mcp.review_signals.history import load_history
from mightymodels_mcp.review_signals.reports import code_churn
from mightymodels_mcp.review_signals.schemas import HistoryWindowRequest

from tests.core.git.git_builders import run_git

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
    options = HistoryWindowRequest()

    history = asyncio.run(
        load_history(
            options, GitCommand(root=tmp_path, executable='git', processes=SubprocessRunner())
        )
    )

    assert [signal.subject for signal in code_churn(history, options).signals] == [NAME]


def commit_names(root: Path, names: list[bytes]) -> None:
    asyncio.run(run_git(root, 'init', '-q'))
    for name in names:
        Path(os.fsdecode(os.fsencode(root) + b'/' + name)).write_bytes(b'a\n')
    asyncio.run(run_git(root, 'add', '-A'))
    asyncio.run(run_git(root, 'commit', '-q', '-m', 'add'))


@pytest.mark.usefixtures('clean_git_environment')
def test_churn_lists_a_file_name_holding_a_double_quote(tmp_path: Path) -> None:
    commit_names(tmp_path, [b'a"b.py', b'tab\tname.py'])
    options = HistoryWindowRequest()

    history = asyncio.run(
        load_history(
            options, GitCommand(root=tmp_path, executable='git', processes=SubprocessRunner())
        )
    )

    assert [signal.subject for signal in code_churn(history, options).signals] == [
        'a"b.py',
        'tab\tname.py',
    ]


@pytest.mark.skipif(sys.platform == 'darwin', reason='APFS rejects non-UTF-8 names')
@pytest.mark.usefixtures('clean_git_environment')
def test_churn_succeeds_and_notes_a_file_name_that_is_not_utf8(tmp_path: Path) -> None:
    commit_names(tmp_path, [b'bad\xff.py', b'ok.py'])
    options = HistoryWindowRequest()

    history = asyncio.run(
        load_history(
            options, GitCommand(root=tmp_path, executable='git', processes=SubprocessRunner())
        )
    )
    report = code_churn(history, options)

    assert [signal.subject for signal in report.signals] == ['ok.py']
    assert any(
        '1 changed paths whose names are not valid UTF-8' in note for note in report.limitations
    )


@pytest.mark.usefixtures('clean_git_environment')
def test_a_pathspec_magic_target_scans_no_commits(tmp_path: Path) -> None:
    commit_names(tmp_path, [b'ok.py'])
    options = HistoryWindowRequest(target=':(exclude)ok.py')

    history = asyncio.run(
        load_history(
            options, GitCommand(root=tmp_path, executable='git', processes=SubprocessRunner())
        )
    )

    assert history.commits == []
