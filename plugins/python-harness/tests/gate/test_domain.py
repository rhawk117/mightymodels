"""Gate values: command argv, outcomes and created paths."""

import pytest
from python_harness.core.output import to_json_value
from python_harness.gate.domain import (
    CreatedPaths,
    CreationTracking,
    Exited,
    GateCommand,
    GateOutcome,
    GateResult,
    GateTool,
    NotTracked,
    ResolvedCommand,
    TimedOut,
)


class TestCommandArgv:
    COMMAND = GateCommand(GateTool.TY, 'uv', ('run', '--isolated', 'ty', 'check'))

    def test_argv_starts_with_the_program(self) -> None:
        assert self.COMMAND.argv == ('uv', 'run', '--isolated', 'ty', 'check')

    def test_resolved_argv_swaps_in_the_executable(self) -> None:
        resolved = ResolvedCommand(self.COMMAND, '/opt/uv/bin/uv')

        assert resolved.argv == ('/opt/uv/bin/uv', 'run', '--isolated', 'ty', 'check')


class TestOutcome:
    COMMAND = GateCommand(GateTool.PYTEST, 'uv', ('run', 'pytest'))

    @pytest.mark.parametrize(
        ('outcome', 'expected'),
        [
            pytest.param(Exited(0), (True, False), id='exit-zero-passes'),
            pytest.param(Exited(1), (False, False), id='nonzero-exit-fails'),
            pytest.param(TimedOut(), (False, True), id='timeout-fails'),
        ],
    )
    def test_passed_and_timed_out_follow_the_outcome(
        self, outcome: GateOutcome, expected: tuple[bool, bool]
    ) -> None:
        result = GateResult(self.COMMAND, outcome, '')

        assert (result.passed, result.timed_out) == expected


class TestCreatedPathsDocument:
    @pytest.mark.parametrize(
        ('created_paths', 'expected'),
        [
            pytest.param(
                CreatedPaths(('build/report.txt',)),
                {'paths': ['build/report.txt'], 'kind': 'tracked'},
                id='tracked-in-a-repository',
            ),
            pytest.param(NotTracked(), {'kind': 'not_tracked'}, id='not-tracked'),
        ],
    )
    def test_created_paths_carry_their_kind(
        self, created_paths: CreationTracking, expected: dict[str, object]
    ) -> None:
        assert to_json_value(created_paths) == expected
