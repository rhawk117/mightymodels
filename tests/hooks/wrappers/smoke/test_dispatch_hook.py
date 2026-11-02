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

WORKER = {
    'agent_id': 'a1',
    'agent_type': 'mightymodels:triage:code-scout',
    'tool_input': {},
}
PHASES = ('investigation', 'planning', 'implementation', 'review')
ENGINEER = {'tool_input': {'subagent_type': 'mightymodels:workers:engineer'}}
BARE_ARCHITECT = {'tool_input': {'subagent_type': 'architect'}}
INTERN = {'tool_input': {'subagent_type': 'mightymodels:workers:intern'}}
SCOUT = {'tool_input': {'subagent_type': 'mightymodels:triage:code-scout'}}


def broken_launcher_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'launcher',
        [
            pytest.param(FAILING_LAUNCHER, id='failing'),
            pytest.param(HANGING_LAUNCHER, id='hanging'),
        ],
    )


def implementer_dispatch_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'payload',
        [
            pytest.param(ENGINEER, id='engineer'),
            pytest.param(BARE_ARCHITECT, id='bare-architect'),
            pytest.param(INTERN, id='intern'),
        ],
    )


def unticketed_dispatch_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'payload', [pytest.param(ENGINEER, id='engineer'), pytest.param(SCOUT, id='scout')]
    )


class TestDispatchWrapper:
    def test_successful_launcher_output_is_passed_through(
        self, dispatch_runner: WrapperRunner
    ) -> None:
        outcome = dispatch_runner.run(SUCCEEDING_LAUNCHER, ENGINEER, with_ticket_dir=True)

        assert (outcome.code, outcome.stdout) == (0, '{}\n')

    @broken_launcher_cases()
    def test_refuses_a_mightymodels_worker_when_the_launcher_breaks(
        self, dispatch_runner: WrapperRunner, launcher: str
    ) -> None:
        outcome = dispatch_runner.run(launcher, WORKER)

        assert outcome.code == 2
        assert 'refused' in outcome.stderr

    @broken_launcher_cases()
    @implementer_dispatch_cases()
    def test_refuses_an_implementer_dispatch_when_a_ticket_dir_exists(
        self, dispatch_runner: WrapperRunner, launcher: str, payload: Mapping[str, object]
    ) -> None:
        outcome = dispatch_runner.run(launcher, payload, with_ticket_dir=True)

        assert outcome.code == 2
        assert 'refused' in outcome.stderr

    @broken_launcher_cases()
    @unticketed_dispatch_cases()
    def test_lets_other_dispatches_through_without_a_ticket_dir(
        self, dispatch_runner: WrapperRunner, launcher: str, payload: Mapping[str, object]
    ) -> None:
        outcome = dispatch_runner.run(launcher, payload)

        assert outcome.code == 0
        assert 'was not checked' in outcome.stderr

    @broken_launcher_cases()
    def test_lets_a_non_implementer_dispatch_through_with_a_ticket_dir(
        self, dispatch_runner: WrapperRunner, launcher: str
    ) -> None:
        outcome = dispatch_runner.run(launcher, SCOUT, with_ticket_dir=True)

        assert outcome.code == 0

    @broken_launcher_cases()
    @pytest.mark.parametrize('phase', PHASES)
    def test_does_not_refuse_a_phase_main_thread_for_its_agent_type(
        self, dispatch_runner: WrapperRunner, launcher: str, phase: str
    ) -> None:
        payload = {'agent_type': f'mightymodels:{phase}', **SCOUT}

        outcome = dispatch_runner.run(launcher, payload)

        assert outcome.code == 0

    @broken_launcher_cases()
    @pytest.mark.parametrize(
        'target', [ENGINEER, SCOUT, {'tool_input': {'subagent_type': 'review'}}]
    )
    @pytest.mark.parametrize('phase', PHASES)
    def test_refuses_any_dispatch_by_a_phase_worker(
        self,
        dispatch_runner: WrapperRunner,
        launcher: str,
        phase: str,
        target: Mapping[str, object],
    ) -> None:
        payload = {'agent_id': 'a1', 'agent_type': f'mightymodels:{phase}', **target}

        outcome = dispatch_runner.run(launcher, payload)

        assert outcome.code == 2
        assert 'refused' in outcome.stderr

    @broken_launcher_cases()
    @pytest.mark.parametrize('with_ticket_dir', [True, False], ids=['ticket-dir', 'no-ticket-dir'])
    @pytest.mark.parametrize('prefix', ['', 'mightymodels:'], ids=['bare', 'prefixed'])
    @pytest.mark.parametrize('phase', PHASES)
    def test_refuses_a_phase_agent_target_from_the_main_thread(
        self,
        dispatch_runner: WrapperRunner,
        launcher: str,
        phase: str,
        prefix: str,
        *,
        with_ticket_dir: bool,
    ) -> None:
        payload = {'tool_input': {'subagent_type': f'{prefix}{phase}'}}

        outcome = dispatch_runner.run(launcher, payload, with_ticket_dir=with_ticket_dir)

        assert outcome.code == 2
        assert 'refused' in outcome.stderr
