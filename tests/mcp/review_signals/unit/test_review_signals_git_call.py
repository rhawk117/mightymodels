"""The git launch of the review signals domain, against a runner that records what it is asked."""

import asyncio
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self

import pytest
from mightymodels_core.git import GIT_TIMEOUT_SECONDS
from mightymodels_core.process import CompletedRun, FailedRun
from mightymodels_mcp.review_signals.history import (
    Analysis,
    GitFailedError,
    GitMissingError,
    GitSource,
    SignalsError,
    TargetNotUnicodeError,
    TargetOutsideError,
    load_history,
)
from mightymodels_mcp.review_signals.options import SignalsOptions

from tests.core.git.fakes import ScriptedRunner

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.process import RunOutcome

GIT = '/opt/git/bin/git'
LOG = [GIT, 'log', '--no-merges', '--no-renames', '--numstat', '--format=%x1e%H']
NO_COMMITS = CompletedRun(exit=0, stdout='', stderr='')


@dataclass(slots=True, kw_only=True, frozen=True)
class Launched:
    vectors: list[list[str]]
    refusal: SignalsError | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Checkout:
    root: Path
    executable: str | None
    runner: ScriptedRunner

    def answering(self, outcome: RunOutcome) -> Self:
        return replace(self, runner=ScriptedRunner(reply=outcome))

    def launch(self, options: SignalsOptions) -> Launched:
        git = GitSource(root=self.root, executable=self.executable, processes=self.runner)
        refusal: SignalsError | None = None
        try:
            asyncio.run(load_history(options, git))
        except SignalsError as error:
            refusal = error
        vectors = [list(run.argv) for run in self.runner.runs]
        return Launched(vectors=vectors, refusal=refusal)


@pytest.fixture
def checkout(tmp_path: Path) -> Checkout:
    root = tmp_path.joinpath('checkout')
    root.joinpath('.git').mkdir(parents=True)
    return Checkout(root=root, executable=GIT, runner=ScriptedRunner(reply=NO_COMMITS))


class TestGitLogArgumentVector:
    @pytest.mark.parametrize(
        ('target_fields', 'target'),
        [
            pytest.param({}, [], id='whole-repository'),
            pytest.param({'target': 'src'}, ['src'], id='target'),
        ],
    )
    @pytest.mark.parametrize(
        ('window_fields', 'window'),
        [
            pytest.param({}, ['--max-count=500', 'HEAD'], id='default-window'),
            pytest.param({'max_commits': 40}, ['--max-count=40', 'HEAD'], id='max-commits'),
            pytest.param({'all_history': True}, ['HEAD'], id='all-history'),
            pytest.param(
                {'since': '2026-01-01'},
                ['--max-count=500', '--since=2026-01-01', 'HEAD'],
                id='since',
            ),
            pytest.param(
                {'baseline_ref': 'release/1.2'},
                ['--max-count=500', 'release/1.2..HEAD'],
                id='baseline-ref',
            ),
            pytest.param(
                {'max_commits': 40, 'since': '2026-01-01', 'baseline_ref': 'main'},
                ['--max-count=40', '--since=2026-01-01', 'main..HEAD'],
                id='max-commits-since-and-baseline-ref',
            ),
            pytest.param(
                {'all_history': True, 'since': '2026-01-01', 'baseline_ref': 'v1.2.0'},
                ['--since=2026-01-01', 'v1.2.0..HEAD'],
                id='all-history-since-and-baseline-ref',
            ),
        ],
    )
    def test_git_is_passed_the_vector_built_for_the_window(
        self,
        checkout: Checkout,
        window_fields: dict[str, object],
        window: list[str],
        target_fields: dict[str, object],
        target: list[str],
    ) -> None:
        options = SignalsOptions.model_validate({**window_fields, **target_fields})

        launched = checkout.launch(options)

        assert (launched.refusal, launched.vectors) == (None, [[*LOG, *window, '--', *target]])

    @pytest.mark.parametrize(
        ('fields', 'values'),
        [
            pytest.param(
                {'since': '6 months ago'},
                ['--max-count=500', '--since=6 months ago', 'HEAD', '--'],
                id='since-holding-a-space',
            ),
            pytest.param(
                {'target': 'release notes/v2 draft.md'},
                ['--max-count=500', 'HEAD', '--', 'release notes/v2 draft.md'],
                id='target-holding-spaces',
            ),
            pytest.param(
                {'target': '--output=report'},
                ['--max-count=500', 'HEAD', '--', '--output=report'],
                id='option-shaped-target',
            ),
            pytest.param(
                {'since': '6 months ago', 'target': 'release notes'},
                ['--max-count=500', '--since=6 months ago', 'HEAD', '--', 'release notes'],
                id='since-and-target-holding-spaces',
            ),
        ],
    )
    def test_each_value_is_one_element_and_the_target_follows_the_separator(
        self, checkout: Checkout, fields: dict[str, object], values: list[str]
    ) -> None:
        launched = checkout.launch(SignalsOptions.model_validate(fields))

        assert launched.vectors == [[*LOG, *values]]

    def test_git_runs_once_at_the_repository_root_under_the_git_timeout(
        self, checkout: Checkout
    ) -> None:
        checkout.launch(SignalsOptions())

        assert [(run.timeout, run.cwd) for run in checkout.runner.runs] == [
            (GIT_TIMEOUT_SECONDS, checkout.root)
        ]


class TestTargetThatIsNotUnicode:
    NAME = 'caf\udce9'
    LINK = 'link'
    REASON = "--target resolves to 'caf\\udce9', which is not valid Unicode"

    @pytest.fixture
    def linked(self, checkout: Checkout) -> Checkout:
        checkout.root.joinpath(self.NAME).mkdir()
        checkout.root.joinpath(self.LINK).symlink_to(self.NAME, target_is_directory=True)
        return checkout

    @pytest.mark.parametrize(
        'target',
        [
            pytest.param(NAME, id='lone-surrogate'),
            pytest.param(LINK, id='symlink-to-a-name-that-is-not-utf8'),
        ],
    )
    def test_it_is_rejected_before_git_runs(self, linked: Checkout, target: str) -> None:
        launched = linked.launch(SignalsOptions(target=target))

        assert isinstance(launched.refusal, TargetNotUnicodeError)
        assert (str(launched.refusal), launched.vectors) == (self.REASON, [])


class TestRefusedTargets:
    @pytest.mark.parametrize('target', ['../..', '/etc'])
    def test_a_target_outside_the_repository_is_rejected_before_git_runs(
        self, checkout: Checkout, target: str
    ) -> None:
        launched = checkout.launch(SignalsOptions(target=target))

        assert isinstance(launched.refusal, TargetOutsideError)
        assert (str(launched.refusal), launched.vectors) == (
            f'--target {target!r} is outside the repository',
            [],
        )


class TestGitFailures:
    @pytest.mark.parametrize(
        ('outcome', 'reason'),
        [
            pytest.param(
                FailedRun(kind='timed_out', detail='timed out after 30s', stdout='', stderr=''),
                'timed out after 30s',
                id='timeout',
            ),
            pytest.param(
                FailedRun(kind='not_found', detail='No such file', stdout='', stderr=''),
                'No such file',
                id='missing-executable',
            ),
            pytest.param(
                FailedRun(kind='refused', detail='Permission denied', stdout='', stderr=''),
                'Permission denied',
                id='refused-launch',
            ),
            pytest.param(
                FailedRun(
                    kind='undecodable',
                    detail="can't decode byte 0xff",
                    stdout='',
                    stderr='',
                ),
                "can't decode byte 0xff",
                id='undecodable-output',
            ),
            pytest.param(
                CompletedRun(exit=128, stdout='', stderr="fatal: bad revision 'gone..HEAD'\n"),
                "fatal: bad revision 'gone..HEAD'",
                id='non-zero-exit',
            ),
        ],
    )
    def test_a_git_that_fails_is_rejected_with_its_reason(
        self, checkout: Checkout, outcome: RunOutcome, reason: str
    ) -> None:
        launched = checkout.answering(outcome).launch(SignalsOptions())

        assert isinstance(launched.refusal, GitFailedError)
        assert str(launched.refusal) == f'git log failed: {reason}'

    def test_a_missing_git_executable_is_rejected_before_anything_runs(
        self, checkout: Checkout
    ) -> None:
        launched = replace(checkout, executable=None).launch(SignalsOptions())

        assert isinstance(launched.refusal, GitMissingError)
        assert (str(launched.refusal), launched.vectors) == ('git is not on PATH', [])


def test_every_analysis_has_a_name() -> None:
    assert [analysis.value for analysis in Analysis] == [
        'code-churn',
        'change-coupling',
        'code-hotspots',
    ]
