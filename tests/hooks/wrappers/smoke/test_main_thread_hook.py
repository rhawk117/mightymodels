from typing import TYPE_CHECKING

import pytest

from tests.hooks.wrappers.conftest import (
    FAILING_LAUNCHER,
    HANGING_LAUNCHER,
    SUCCEEDING_LAUNCHER,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from tests.hooks.wrappers.conftest import (
        WrapperRunner,
    )

PUSH = {'tool_name': 'Bash', 'tool_input': {'command': 'git push origin main'}}
STATUS = {'tool_name': 'Bash', 'tool_input': {'command': 'git status'}}
EDIT = {'tool_name': 'Edit', 'tool_input': {'file_path': 'a.py'}}
WRITE = {'tool_name': 'Write', 'tool_input': {'file_path': 'a.py'}}
READ = {'tool_name': 'Read', 'tool_input': {'file_path': 'a.py'}}
WORKER_PUSH = {**PUSH, 'agent_type': 'mightymodels:workers:engineer'}
BROKEN_LAUNCHERS = pytest.mark.parametrize('launcher', [FAILING_LAUNCHER, HANGING_LAUNCHER])


class TestMainThreadWrapper:
    def test_successful_launcher_output_is_passed_through(
        self, main_thread_runner: WrapperRunner
    ) -> None:
        outcome = main_thread_runner.run(SUCCEEDING_LAUNCHER, PUSH, with_ticket_dir=True)

        assert (outcome.code, outcome.stdout) == (0, '{}\n')

    @BROKEN_LAUNCHERS
    def test_refuses_a_push_when_the_launcher_breaks(
        self, main_thread_runner: WrapperRunner, launcher: str
    ) -> None:
        outcome = main_thread_runner.run(launcher, PUSH, with_ticket_dir=True)

        assert outcome.code == 2
        assert 'push is refused' in outcome.stderr

    @BROKEN_LAUNCHERS
    @pytest.mark.parametrize('payload', [EDIT, WRITE])
    def test_warns_about_an_unchecked_edit_when_the_launcher_breaks(
        self, main_thread_runner: WrapperRunner, launcher: str, payload: Mapping[str, object]
    ) -> None:
        outcome = main_thread_runner.run(launcher, payload, with_ticket_dir=True)

        assert outcome.code == 0
        assert 'systemMessage' in outcome.stdout

    @BROKEN_LAUNCHERS
    @pytest.mark.parametrize('payload', [STATUS, READ, WORKER_PUSH])
    def test_lets_everything_else_through_when_the_launcher_breaks(
        self, main_thread_runner: WrapperRunner, launcher: str, payload: Mapping[str, object]
    ) -> None:
        outcome = main_thread_runner.run(launcher, payload, with_ticket_dir=True)

        assert (outcome.code, outcome.stdout) == (0, '')

    @BROKEN_LAUNCHERS
    @pytest.mark.parametrize('payload', [PUSH, EDIT])
    def test_lets_everything_through_without_a_ticket_dir(
        self, main_thread_runner: WrapperRunner, launcher: str, payload: Mapping[str, object]
    ) -> None:
        outcome = main_thread_runner.run(launcher, payload)

        assert (outcome.code, outcome.stdout) == (0, '')
