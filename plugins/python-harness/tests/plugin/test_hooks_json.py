"""The plugin's hook registration: both events, the Bash filter, and the launcher they run."""

import json
import os
import shlex
from pathlib import Path

import pytest
from python_harness.cli import build_parser

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
HOOKS_FILE = PLUGIN_ROOT.joinpath('hooks', 'hooks.json')
PLUGIN_ROOT_VARIABLE = '${CLAUDE_PLUGIN_ROOT}/'
SUBCOMMANDS = {'SessionStart': 'session-start', 'PreToolUse': 'guard-python'}


def hook_handlers() -> list[tuple[str, dict[str, object]]]:
    document = json.loads(HOOKS_FILE.read_text(encoding='utf-8'))
    return [
        (event, handler)
        for event, matchers in document['hooks'].items()
        for matcher in matchers
        for handler in matcher['hooks']
    ]


class TestHooksJson:
    def test_the_plugin_registers_both_hooks(self) -> None:
        assert sorted(event for event, _ in hook_handlers()) == [
            'PreToolUse',
            'SessionStart',
        ]

    def test_the_guard_runs_on_bash_calls_that_mention_python(self) -> None:
        document = json.loads(HOOKS_FILE.read_text(encoding='utf-8'))
        matcher = document['hooks']['PreToolUse'][0]

        assert (matcher['matcher'], matcher['hooks'][0]['if']) == (
            'Bash',
            'Bash(*python*)',
        )

    @pytest.mark.parametrize(('event', 'handler'), hook_handlers())
    def test_each_hook_runs_the_cli_launcher(self, event: str, handler: dict[str, object]) -> None:
        executable, group, *_ = shlex.split(str(handler['command']))
        launcher = PLUGIN_ROOT.joinpath(executable.removeprefix(PLUGIN_ROOT_VARIABLE))

        assert (event, launcher.relative_to(PLUGIN_ROOT).as_posix(), group) == (
            event,
            'bin/python-harness',
            'hooks',
        )

    @pytest.mark.parametrize(('event', 'handler'), hook_handlers())
    def test_each_subcommand_is_one_the_cli_knows(
        self, event: str, handler: dict[str, object]
    ) -> None:
        _, group, subcommand, *_ = shlex.split(str(handler['command']))

        arguments = build_parser({group}).parse_args((group, subcommand))

        assert arguments.command == SUBCOMMANDS[event]

    def test_the_launcher_is_executable(self) -> None:
        assert os.access(PLUGIN_ROOT.joinpath('bin', 'python-harness'), os.X_OK)
