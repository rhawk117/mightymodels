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

WORKER = {'agent_type': 'mightymodels:triage:code-scout', 'tool_input': {}}
ENGINEER = {'tool_input': {'subagent_type': 'mightymodels:workers:engineer'}}
BARE_ARCHITECT = {'tool_input': {'subagent_type': 'architect'}}
INTERN = {'tool_input': {'subagent_type': 'mightymodels:workers:intern'}}
SCOUT = {'tool_input': {'subagent_type': 'mightymodels:triage:code-scout'}}
BROKEN_LAUNCHERS = pytest.mark.parametrize('launcher', [FAILING_LAUNCHER, HANGING_LAUNCHER])


class TestDispatchWrapper:
    def test_successful_launcher_output_is_passed_through(
        self, dispatch_runner: WrapperRunner
    ) -> None:
        outcome = dispatch_runner.run(SUCCEEDING_LAUNCHER, ENGINEER, with_ticket_dir=True)

        assert (outcome.code, outcome.stdout) == (0, '{}\n')

    @BROKEN_LAUNCHERS
    def test_refuses_a_mightymodels_worker_when_the_launcher_breaks(
        self, dispatch_runner: WrapperRunner, launcher: str
    ) -> None:
        outcome = dispatch_runner.run(launcher, WORKER)

        assert outcome.code == 2
        assert 'refused' in outcome.stderr

    @BROKEN_LAUNCHERS
    @pytest.mark.parametrize('payload', [ENGINEER, BARE_ARCHITECT, INTERN])
    def test_refuses_an_implementer_dispatch_when_a_ticket_dir_exists(
        self, dispatch_runner: WrapperRunner, launcher: str, payload: Mapping[str, object]
    ) -> None:
        outcome = dispatch_runner.run(launcher, payload, with_ticket_dir=True)

        assert outcome.code == 2
        assert 'refused' in outcome.stderr

    @BROKEN_LAUNCHERS
    @pytest.mark.parametrize('payload', [ENGINEER, SCOUT])
    def test_lets_other_dispatches_through_without_a_ticket_dir(
        self, dispatch_runner: WrapperRunner, launcher: str, payload: Mapping[str, object]
    ) -> None:
        outcome = dispatch_runner.run(launcher, payload)

        assert outcome.code == 0
        assert 'was not checked' in outcome.stderr

    @BROKEN_LAUNCHERS
    def test_lets_a_non_implementer_dispatch_through_with_a_ticket_dir(
        self, dispatch_runner: WrapperRunner, launcher: str
    ) -> None:
        outcome = dispatch_runner.run(launcher, SCOUT, with_ticket_dir=True)

        assert outcome.code == 0
