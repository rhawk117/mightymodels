"""Behavioral tests for `mightymodels review-signals` against a real git repository."""

import asyncio
import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Required, TypedDict

import pytest
from mightymodels_cli.main import main

from tests.core.git.git_builders import run_git

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures('clean_git_environment')]

COMMAND = 'review-signals'
REJECTED = 2
CAPPED = 2


class ScannedHistory(TypedDict):
    since: str | None
    baseline_ref: str | None
    max_commits: int | None
    commits_scanned: int
    truncated: bool


class Signal(TypedDict, total=False):
    subject: Required[str]
    commits: int
    lines_added: int
    lines_deleted: int
    shared_commits: int
    degree: float
    loc: int
    indentation: int
    hotspot: int


class Report(TypedDict):
    analysis: str
    target: str
    history: ScannedHistory
    signals: list[Signal]
    limitations: list[str]


@dataclass(frozen=True, slots=True)
class Repo:
    root: Path
    capsys: pytest.CaptureFixture[str]

    def git(self, *args: str) -> str:
        return asyncio.run(run_git(self.root, *args))

    def commit(self, files: dict[str, str]) -> str:
        for name, text in files.items():
            path = self.root.joinpath(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
            self.git('add', name)
        self.git('commit', '-q', '-m', 'change')
        return self.git('rev-parse', 'HEAD')

    def signals(self, *argv: str) -> Report:
        code = main([COMMAND, *argv])
        captured = self.capsys.readouterr()
        assert code == 0, captured.err
        return json.loads(captured.out)

    def refused(self, *argv: str) -> str:
        code = main([COMMAND, *argv])
        assert code == REJECTED
        return self.capsys.readouterr().err


@pytest.fixture
def clean_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [name for name in os.environ if name.startswith('GIT_')]:
        monkeypatch.delenv(name)


@pytest.fixture
def repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Repo:
    monkeypatch.chdir(tmp_path)
    space = Repo(root=tmp_path, capsys=capsys)
    space.git('init', '-q')
    return space


def subjects(report: Report) -> list[str]:
    return [signal['subject'] for signal in report['signals']]


class TestCodeChurn:
    def test_churn_ranks_files_by_commits_then_lines(self, repo: Repo) -> None:
        repo.commit({'src/queue.py': 'a\n', 'src/client.py': 'a\nb\nc\n'})
        repo.commit({'src/queue.py': 'a\nb\n'})
        report = repo.signals('code-churn')
        assert report['signals'][0] == {
            'subject': 'src/queue.py',
            'commits': 2,
            'lines_added': 2,
            'lines_deleted': 0,
        }
        assert subjects(report) == ['src/queue.py', 'src/client.py']

    def test_files_deleted_since_are_left_out(self, repo: Repo) -> None:
        repo.commit({'gone.py': 'a\n', 'kept.py': 'a\n'})
        repo.git('rm', '-q', 'gone.py')
        repo.git('commit', '-q', '-m', 'drop')
        assert subjects(repo.signals('code-churn')) == ['kept.py']

    def test_target_limits_the_files_counted(self, repo: Repo) -> None:
        repo.commit({'src/queue.py': 'a\n', 'docs/readme.md': 'a\n'})
        report = repo.signals('code-churn', '--target', 'src')
        assert (report['target'], subjects(report)) == ('src', ['src/queue.py'])

    def test_baseline_ref_counts_only_later_commits(self, repo: Repo) -> None:
        base = repo.commit({'old.py': 'a\n'})
        repo.commit({'new.py': 'a\n'})
        report = repo.signals('code-churn', '--baseline-ref', base)
        assert subjects(report) == ['new.py']

    def test_a_capped_window_says_it_was_truncated(self, repo: Repo) -> None:
        for text in ('a\n', 'b\n', 'c\n'):
            repo.commit({'queue.py': text})
        report = repo.signals('code-churn', '--max-commits', str(CAPPED))
        assert report['history']['truncated'] is True
        assert report['signals'][0]['commits'] == CAPPED
        assert any('--all-history' in note for note in report['limitations'])


class TestChangeCoupling:
    def test_coupling_finds_files_that_change_together(self, repo: Repo) -> None:
        for text in ('a\n', 'b\n', 'c\n'):
            repo.commit({'queue.py': text, 'retry.py': text})
        repo.commit({'queue.py': 'd\n'})
        report = repo.signals('change-coupling')
        assert report['signals'] == [
            {'subject': 'queue.py <-> retry.py', 'shared_commits': 3, 'degree': 1.0}
        ]

    def test_bulk_commits_do_not_create_coupling(self, repo: Repo) -> None:
        for text in ('a\n', 'b\n', 'c\n'):
            repo.commit({'queue.py': text, 'retry.py': text, 'other.py': text})
        report = repo.signals('change-coupling', '--max-changeset', '2')
        assert report['signals'] == []
        assert any('3 commits touching more than 2' in note for note in report['limitations'])


class TestCodeHotspots:
    def test_hotspots_weigh_churn_by_indentation(self, repo: Repo) -> None:
        nested = 'def f():\n    if x:\n        return 1\n'
        repo.commit({'flat.py': 'a = 1\nb = 2\n', 'nested.py': nested})
        repo.commit({'flat.py': 'a = 1\nb = 3\n', 'nested.py': nested + '    return 2\n'})
        report = repo.signals('code-hotspots')
        assert report['signals'][0] == {
            'subject': 'nested.py',
            'commits': 2,
            'loc': 4,
            'indentation': 4,
            'hotspot': 8,
        }

    def test_deleted_and_binary_files_are_not_hotspots(self, repo: Repo) -> None:
        repo.commit({'gone.py': 'a\n', 'blob.bin': '\0\0\0'})
        repo.git('rm', '-q', 'gone.py')
        repo.git('commit', '-q', '-m', 'drop')
        report = repo.signals('code-hotspots')
        assert report['signals'] == []


class TestRefusals:
    def test_option_shaped_values_are_refused(self, repo: Repo) -> None:
        repo.commit({'queue.py': 'a\n'})
        error = repo.refused('code-churn', '--baseline-ref=--output=/tmp/x')
        assert 'is not a plain value' in error

    def test_a_target_outside_the_repository_is_refused(self, repo: Repo) -> None:
        repo.commit({'queue.py': 'a\n'})
        assert 'outside the repository' in repo.refused('code-churn', '--target', '../..')

    def test_outside_a_repository_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        lone = tmp_path.joinpath('lone')
        lone.mkdir()
        monkeypatch.chdir(lone)
        code = main([COMMAND, 'code-churn'])
        assert code == REJECTED
        assert 'not inside a git repository' in capsys.readouterr().err


class TestHelp:
    WINDOW_OPTIONS = ('--target', '--since', '--baseline-ref', '--max-commits', '--all-history')

    @pytest.mark.parametrize('report', ['code-churn', 'change-coupling', 'code-hotspots'])
    def test_help_shows_the_window_options_of_each_report(
        self, report: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main([COMMAND, report, '--help'])

        shown = capsys.readouterr().out
        assert exit_info.value.code == 0
        assert [option in shown for option in self.WINDOW_OPTIONS] == [True] * 5
