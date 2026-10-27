from typing import TYPE_CHECKING

from tests.hooks.wrappers.wrapper_builders import FAILING_LAUNCHER, SUCCEEDING_LAUNCHER

if TYPE_CHECKING:
    from tests.hooks.wrappers.wrapper_builders import WrapperRunner


class TestGenericWrapper:
    def test_launcher_failure_exits_zero_with_a_stderr_note(
        self, hook_runner: WrapperRunner
    ) -> None:
        outcome = hook_runner.run(FAILING_LAUNCHER, {}, args=('format',))

        assert outcome.code == 0
        assert outcome.stdout == ''
        assert 'format could not run' in outcome.stderr

    def test_launcher_output_is_passed_through(self, hook_runner: WrapperRunner) -> None:
        outcome = hook_runner.run(SUCCEEDING_LAUNCHER, {}, args=('format',))

        assert outcome.code == 0
        assert outcome.stdout == '{}\n'

    def test_launcher_receives_the_subcommand(self, hook_runner: WrapperRunner) -> None:
        outcome = hook_runner.run('printf "%s" "$1"', {}, args=('format',))

        assert outcome.stdout == 'format\n'
