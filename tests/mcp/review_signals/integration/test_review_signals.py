"""Behavioral tests for the review signals domain against a real git repository."""

import asyncio
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_mcp.review_signals.history import (
    Analysis,
    NoRepositoryError,
    TargetOutsideError,
    create_git_source,
    load_history,
)
from mightymodels_mcp.review_signals.options import SignalsOptions
from mightymodels_mcp.review_signals.reports import (
    ChurnSignal,
    CouplingSignal,
    HotspotSignal,
    change_coupling,
    code_churn,
    code_hotspots,
)

from tests.core.git.git_builders import run_git

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_mcp.review_signals.history import History, Report

CAPPED = 2


@dataclass(frozen=True, slots=True)
class Repo:
    root: Path

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

    def load(self, options: SignalsOptions) -> History:
        return asyncio.run(load_history(options, create_git_source(self.root)))

    def churn(self, options: SignalsOptions | None = None) -> Report[ChurnSignal]:
        options = options or SignalsOptions()
        return code_churn(self.load(options), options)

    def coupling(self, options: SignalsOptions | None = None) -> Report[CouplingSignal]:
        options = options or SignalsOptions()
        return change_coupling(self.load(options), options)

    def hotspots(self, options: SignalsOptions | None = None) -> Report[HotspotSignal]:
        options = options or SignalsOptions()
        return code_hotspots(self.load(options), options)


@pytest.fixture
def clean_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [name for name in os.environ if name.startswith('GIT_')]:
        monkeypatch.delenv(name)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    space = Repo(root=tmp_path)
    space.git('init', '-q')
    return space


def subjects(report: Report[ChurnSignal]) -> list[str]:
    return [signal.subject for signal in report.signals]


@pytest.mark.usefixtures('clean_git_environment')
class TestCodeChurn:
    def test_churn_ranks_files_by_commits_then_lines(self, repo: Repo) -> None:
        repo.commit({'src/queue.py': 'a\n', 'src/client.py': 'a\nb\nc\n'})
        repo.commit({'src/queue.py': 'a\nb\n'})
        report = repo.churn()
        assert report.analysis == Analysis.CHURN
        assert report.signals[0] == ChurnSignal(
            subject='src/queue.py', commits=2, lines_added=2, lines_deleted=0
        )
        assert subjects(report) == ['src/queue.py', 'src/client.py']

    def test_files_deleted_since_are_left_out(self, repo: Repo) -> None:
        repo.commit({'gone.py': 'a\n', 'kept.py': 'a\n'})
        repo.git('rm', '-q', 'gone.py')
        repo.git('commit', '-q', '-m', 'drop')
        assert subjects(repo.churn()) == ['kept.py']

    def test_target_limits_the_files_counted(self, repo: Repo) -> None:
        repo.commit({'src/queue.py': 'a\n', 'docs/readme.md': 'a\n'})
        report = repo.churn(SignalsOptions(target='src'))
        assert (report.target, subjects(report)) == ('src', ['src/queue.py'])

    def test_baseline_ref_counts_only_later_commits(self, repo: Repo) -> None:
        base = repo.commit({'old.py': 'a\n'})
        repo.commit({'new.py': 'a\n'})
        report = repo.churn(SignalsOptions(baseline_ref=base))
        assert subjects(report) == ['new.py']

    def test_a_capped_window_says_it_was_truncated(self, repo: Repo) -> None:
        for text in ('a\n', 'b\n', 'c\n'):
            repo.commit({'queue.py': text})
        report = repo.churn(SignalsOptions(max_commits=CAPPED))
        assert report.history.truncated is True
        assert report.signals[0].commits == CAPPED
        assert any('--all-history' in note for note in report.limitations)

    def test_all_history_lifts_the_commit_cap(self, repo: Repo) -> None:
        for text in ('a\n', 'b\n', 'c\n'):
            repo.commit({'queue.py': text})
        report = repo.churn(SignalsOptions(max_commits=CAPPED, all_history=True))
        assert (report.history.max_commits, report.history.truncated) == (None, False)


@pytest.mark.usefixtures('clean_git_environment')
class TestChangeCoupling:
    def test_coupling_finds_files_that_change_together(self, repo: Repo) -> None:
        for text in ('a\n', 'b\n', 'c\n'):
            repo.commit({'queue.py': text, 'retry.py': text})
        repo.commit({'queue.py': 'd\n'})
        report = repo.coupling()
        assert report.signals == [
            CouplingSignal(subject='queue.py <-> retry.py', shared_commits=3, degree=1.0)
        ]

    def test_bulk_commits_do_not_create_coupling(self, repo: Repo) -> None:
        for text in ('a\n', 'b\n', 'c\n'):
            repo.commit({'queue.py': text, 'retry.py': text, 'other.py': text})
        report = repo.coupling(SignalsOptions(max_changeset=2))
        assert report.signals == []
        assert any('3 commits touching more than 2' in note for note in report.limitations)


@pytest.mark.usefixtures('clean_git_environment')
class TestCodeHotspots:
    def test_hotspots_weigh_churn_by_indentation(self, repo: Repo) -> None:
        nested = 'def f():\n    if x:\n        return 1\n'
        repo.commit({'flat.py': 'a = 1\nb = 2\n', 'nested.py': nested})
        repo.commit({'flat.py': 'a = 1\nb = 3\n', 'nested.py': nested + '    return 2\n'})
        report = repo.hotspots()
        assert report.signals[0] == HotspotSignal(
            subject='nested.py', commits=2, loc=4, indentation=4, hotspot=8
        )

    def test_deleted_and_binary_files_are_not_hotspots(self, repo: Repo) -> None:
        repo.commit({'gone.py': 'a\n', 'blob.bin': '\0\0\0'})
        repo.git('rm', '-q', 'gone.py')
        repo.git('commit', '-q', '-m', 'drop')
        assert repo.hotspots().signals == []


@pytest.mark.usefixtures('clean_git_environment')
class TestRefusals:
    def test_a_target_outside_the_repository_is_refused(self, repo: Repo) -> None:
        repo.commit({'queue.py': 'a\n'})
        with pytest.raises(TargetOutsideError, match='outside the repository'):
            repo.load(SignalsOptions(target='../..'))

    def test_outside_a_repository_is_refused(self, tmp_path: Path) -> None:
        lone = Repo(root=tmp_path.joinpath('lone'))
        lone.root.mkdir()
        with pytest.raises(NoRepositoryError, match='not inside a git repository'):
            lone.load(SignalsOptions())
