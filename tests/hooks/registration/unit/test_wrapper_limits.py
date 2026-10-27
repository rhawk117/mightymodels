import re

import pytest

from tests.hooks.registration.registration_builders import ROOT, read_registered_hooks

LAUNCHER_ARGV = 'uv run --locked --no-dev --package mightymodels-hooks mightymodels-hooks'
DEFAULT_PATTERN = re.compile(
    r'^limit_seconds=\$\{(?P<variable>\w+):-(?P<seconds>\d+)\}$', re.MULTILINE
)


def wrapper_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('script', 'variable'),
        [
            pytest.param('dispatch-hook.sh', 'MIGHTYMODELS_DISPATCH_SECONDS', id='dispatch'),
            pytest.param(
                'main-thread-hook.sh', 'MIGHTYMODELS_MAIN_THREAD_SECONDS', id='main-thread'
            ),
        ],
    )


def read_default_seconds(script: str, variable: str) -> int:
    match = DEFAULT_PATTERN.search(ROOT.joinpath('hooks', script).read_text())
    assert match, f'{script} has no limit_seconds default'
    assert match['variable'] == variable
    return int(match['seconds'])


class TestWrapperLimits:
    @wrapper_cases()
    def test_wrapper_kills_the_launcher_after_eight_seconds(
        self, script: str, variable: str
    ) -> None:
        assert read_default_seconds(script, variable) == 8

    def test_launcher_runs_the_locked_hooks_package(self) -> None:
        launcher = ROOT.joinpath('hooks', 'lib.sh').read_text()

        assert f'exec {LAUNCHER_ARGV} "$@"' in launcher

    @wrapper_cases()
    def test_pre_tool_use_timeout_outlasts_the_wrapper_kill(
        self, script: str, variable: str
    ) -> None:
        default_seconds = read_default_seconds(script, variable)
        registered = [
            hook
            for hook in read_registered_hooks()
            if hook.event == 'PreToolUse' and hook.script == script
        ]

        assert registered
        assert all(hook.timeout > default_seconds for hook in registered)
