"""Repositories and checkouts the review signals tests build their scenarios on."""

import asyncio
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self

from mightymodels_core.git import GitCommand
from mightymodels_core.process import CompletedRun, SubprocessRunner
from mightymodels_mcp.review_signals.errors import SignalsError
from mightymodels_mcp.review_signals.history import load_history
from mightymodels_mcp.review_signals.reports import change_coupling, code_churn, code_hotspots
from mightymodels_mcp.review_signals.schemas import (
    ChangeCouplingRequest,
    CodeChurnRequest,
    CodeHotspotsRequest,
)

from tests.core.git.fakes import ScriptedRunner
from tests.core.git.git_builders import run_git

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.process import RunOutcome
    from mightymodels_mcp.review_signals.history import History
    from mightymodels_mcp.review_signals.schemas import HistoryWindowRequest
    from mightymodels_mcp.review_signals.views import (
        ChurnSignal,
        CouplingSignal,
        HotspotSignal,
        Report,
    )

GIT = '/opt/git/bin/git'
LOG_OPTIONS = [
    '--literal-pathspecs',
    'log',
    '--no-merges',
    '--no-renames',
    '--numstat',
    '--format=%x1e%H',
]
NO_COMMITS = CompletedRun(exit=0, stdout='', stderr='')


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

    def load(self, options: HistoryWindowRequest) -> History:
        return asyncio.run(
            load_history(
                options, GitCommand(root=self.root, executable='git', processes=SubprocessRunner())
            )
        )

    def churn(self, options: CodeChurnRequest | None = None) -> Report[ChurnSignal]:
        options = options or CodeChurnRequest()
        return code_churn(self.load(options), options)

    def coupling(self, options: ChangeCouplingRequest | None = None) -> Report[CouplingSignal]:
        options = options or ChangeCouplingRequest()
        return change_coupling(self.load(options), options)

    def hotspots(self, options: CodeHotspotsRequest | None = None) -> Report[HotspotSignal]:
        options = options or CodeHotspotsRequest()
        return code_hotspots(self.load(options), options)


@dataclass(slots=True, kw_only=True, frozen=True)
class Launched:
    vectors: list[list[str]]
    refusal: SignalsError | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Checkout:
    root: Path
    executable: str | None
    runner: ScriptedRunner

    @property
    def log(self) -> list[str]:
        return [GIT, '-C', str(self.root), *LOG_OPTIONS]

    def answering(self, outcome: RunOutcome) -> Self:
        return replace(self, runner=ScriptedRunner(reply=outcome))

    def launch(self, options: HistoryWindowRequest) -> Launched:
        git = GitCommand(root=self.root, executable=self.executable, processes=self.runner)
        refusal: SignalsError | None = None
        try:
            asyncio.run(load_history(options, git))
        except SignalsError as error:
            refusal = error
        vectors = [list(run.argv) for run in self.runner.runs]
        return Launched(vectors=vectors, refusal=refusal)
