import io
from typing import TYPE_CHECKING

import pytest
from mightymodels_hooks.cli import create_hook_router
from mightymodels_hooks.session_pointer import create_pointer_fields

from tests.hooks.registration.registration_builders import ROOT

if TYPE_CHECKING:
    from tests.hooks.registration.registration_builders import RegisteredHook

POINTER_TOOLS = create_pointer_fields().tool_names
POINTER_MATCHER = '^mcp__plugin_mightymodels_workflow_state__(' + '|'.join(POINTER_TOOLS) + ')$'
EXPECTED = [
    ('SessionStart', None, 'hook.sh', 'session-start'),
    ('PreToolUse', 'Agent', 'dispatch-hook.sh', None),
    ('PreToolUse', 'Edit|Write|Bash', 'main-thread-hook.sh', None),
    (
        'SubagentStop',
        '^mightymodels:triage:(code-scout|web-scout)$',
        'hook.sh',
        'subagent-record',
    ),
    (
        'SubagentStop',
        '^mightymodels:workers:(engineer|architect|intern)$',
        'hook.sh',
        'completion-gate',
    ),
    ('PostToolUse', 'SubagentHandback', 'hook.sh', 'subagent-handback'),
    ('PostToolUse', 'AskUserQuestion', 'hook.sh', 'ask-recorder'),
    ('PostToolUse', POINTER_MATCHER, 'hook.sh', 'session-pointer'),
    ('PreCompact', None, 'hook.sh', 'pre-compact'),
]


def fixed_wrapper_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'script',
        [
            pytest.param('dispatch-hook.sh', id='dispatch'),
            pytest.param('main-thread-hook.sh', id='main-thread'),
        ],
    )


class TestHooksJson:
    def test_the_nine_command_hooks_are_registered(
        self, registered_hooks: list[RegisteredHook]
    ) -> None:
        found = [(h.event, h.matcher, h.script, h.subcommand) for h in registered_hooks]

        assert found == EXPECTED

    def test_every_hook_has_a_ten_second_timeout(
        self, registered_hooks: list[RegisteredHook]
    ) -> None:
        assert {h.timeout for h in registered_hooks} == {10}

    def test_every_script_exists(self, registered_hooks: list[RegisteredHook]) -> None:
        assert all(ROOT.joinpath('hooks', h.script).is_file() for h in registered_hooks)

    def test_every_subcommand_is_defined_by_the_cli(
        self, registered_hooks: list[RegisteredHook]
    ) -> None:
        router = create_hook_router({}, io.StringIO())
        named = [h.subcommand for h in registered_hooks if h.subcommand]

        assert all(router.find_handler(name) is not None for name in named)

    def test_the_pointer_matcher_names_twenty_tools(self) -> None:
        assert len(POINTER_TOOLS) == 20

    @fixed_wrapper_cases()
    def test_fixed_wrappers_take_no_subcommand(
        self, registered_hooks: list[RegisteredHook], script: str
    ) -> None:
        assert [h.subcommand for h in registered_hooks if h.script == script] == [None]
