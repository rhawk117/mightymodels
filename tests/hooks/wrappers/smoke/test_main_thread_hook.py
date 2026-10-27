from typing import TYPE_CHECKING

import pytest

from tests.hooks.wrappers.wrapper_builders import (
    FAILING_LAUNCHER,
    HANGING_LAUNCHER,
    SUCCEEDING_LAUNCHER,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from tests.hooks.wrappers.wrapper_builders import (
        WrapperRunner,
    )

PUSH = {'tool_name': 'Bash', 'tool_input': {'command': 'git push origin main'}}
STATUS = {'tool_name': 'Bash', 'tool_input': {'command': 'git status'}}
EDIT = {'tool_name': 'Edit', 'tool_input': {'file_path': 'a.py'}}
WRITE = {'tool_name': 'Write', 'tool_input': {'file_path': 'a.py'}}
READ = {'tool_name': 'Read', 'tool_input': {'file_path': 'a.py'}}
WORKER_PUSH = {**PUSH, 'agent_type': 'mightymodels:workers:engineer'}


def broken_launcher_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'launcher',
        [
            pytest.param(FAILING_LAUNCHER, id='failing'),
            pytest.param(HANGING_LAUNCHER, id='hanging'),
        ],
    )


def unchecked_edit_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'payload', [pytest.param(EDIT, id='edit'), pytest.param(WRITE, id='write')]
    )


def passed_through_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'payload',
        [
            pytest.param(STATUS, id='status'),
            pytest.param(READ, id='read'),
            pytest.param(WORKER_PUSH, id='worker-push'),
        ],
    )


def unticketed_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'payload', [pytest.param(PUSH, id='push'), pytest.param(EDIT, id='edit')]
    )


class TestMainThreadWrapper:
    def test_successful_launcher_output_is_passed_through(
        self, main_thread_runner: WrapperRunner
    ) -> None:
        outcome = main_thread_runner.run(SUCCEEDING_LAUNCHER, PUSH, with_ticket_dir=True)

        assert (outcome.code, outcome.stdout) == (0, '{}\n')

    @broken_launcher_cases()
    def test_refuses_a_push_when_the_launcher_breaks(
        self, main_thread_runner: WrapperRunner, launcher: str
    ) -> None:
        outcome = main_thread_runner.run(launcher, PUSH, with_ticket_dir=True)

        assert outcome.code == 2
        assert 'push is refused' in outcome.stderr

    @broken_launcher_cases()
    @unchecked_edit_cases()
    def test_warns_about_an_unchecked_edit_when_the_launcher_breaks(
        self, main_thread_runner: WrapperRunner, launcher: str, payload: Mapping[str, object]
    ) -> None:
        outcome = main_thread_runner.run(launcher, payload, with_ticket_dir=True)

        assert outcome.code == 0
        assert 'systemMessage' in outcome.stdout

    @broken_launcher_cases()
    @passed_through_cases()
    def test_lets_everything_else_through_when_the_launcher_breaks(
        self, main_thread_runner: WrapperRunner, launcher: str, payload: Mapping[str, object]
    ) -> None:
        outcome = main_thread_runner.run(launcher, payload, with_ticket_dir=True)

        assert (outcome.code, outcome.stdout) == (0, '')

    @broken_launcher_cases()
    @unticketed_cases()
    def test_lets_everything_through_without_a_ticket_dir(
        self, main_thread_runner: WrapperRunner, launcher: str, payload: Mapping[str, object]
    ) -> None:
        outcome = main_thread_runner.run(launcher, payload)

        assert (outcome.code, outcome.stdout) == (0, '')
