"""The guard: which commands run plain python, and what to run instead."""

import pytest
from python_harness.hooks.domain import BashCall, OtherToolCall
from python_harness.hooks.guard.domain import (
    GuardOptions,
    InterpreterCall,
    NoNudge,
    Nudge,
)
from python_harness.hooks.guard.services import find_interpreter_calls, judge_tool_call


def suggestions_for(command: str) -> tuple[str, ...]:
    calls = find_interpreter_calls(command, GuardOptions())
    return tuple(call.suggestion for call in calls)


class TestNotedCommands:
    @pytest.mark.parametrize(
        ('command', 'expected'),
        [
            pytest.param('python x.py', ('uv run python x.py',), id='python'),
            pytest.param('python3 -m pytest', ('uv run python -m pytest',), id='python3'),
            pytest.param('python3.12 -V', ('uv run python -V',), id='versioned'),
            pytest.param('python3.14t -c 1', ('uv run python -c 1',), id='free-threaded'),
            pytest.param('python2 old.py', ('uv run python old.py',), id='python2'),
            pytest.param('"python3" x', ('uv run python x',), id='quoted-name'),
            pytest.param('FOO=1 python3 x', ('FOO=1 uv run python x',), id='leading-assignment'),
            pytest.param(
                'cd src && python x.py | tee out',
                ('uv run python x.py',),
                id='list-and-pipeline',
            ),
            pytest.param('ls; python2 a.py', ('uv run python a.py',), id='sequence'),
            pytest.param('(python3 a)', ('uv run python a',), id='subshell'),
            pytest.param(
                'echo $(python3 -V) `python -V`',
                ('uv run python -V', 'uv run python -V'),
                id='substitutions',
            ),
            pytest.param('diff <(python a) b', ('uv run python a',), id='process-subst'),
            pytest.param(
                'if python3 -c 1; then echo ok; fi',
                ('uv run python -c 1',),
                id='condition',
            ),
            pytest.param("python3 - <<'EOF'\nprint(1)\nEOF", ('uv run python',), id='heredoc'),
        ],
    )
    def test_each_plain_python_command_gets_a_uv_suggestion(
        self, command: str, expected: tuple[str, ...]
    ) -> None:
        assert suggestions_for(command) == expected


class TestQuietCommands:
    @pytest.mark.parametrize(
        'command',
        [
            pytest.param('uv run python -c 1', id='uv-run'),
            pytest.param('echo python', id='argument'),
            pytest.param('which python3', id='which'),
            pytest.param('/usr/bin/python3 -V', id='path'),
            pytest.param('.venv/bin/python -m pytest', id='virtualenv-path'),
            pytest.param('env python x', id='behind-a-wrapper'),
            pytest.param('bash -c "python3 -V"', id='nested-shell'),
            pytest.param("cat <<'EOF' > f\npython x\nEOF", id='heredoc-data'),
            pytest.param('pythonista docs read json.dumps', id='longer-name'),
            pytest.param('$PYTHON x.py', id='expansion-name'),
            pytest.param('', id='empty'),
            pytest.param('echo "unterminated python', id='syntax-error'),
        ],
    )
    def test_no_note_is_added(self, command: str) -> None:
        assert find_interpreter_calls(command, GuardOptions()) == ()


class TestCallFields:
    def test_a_call_names_the_interpreter_and_its_command(self) -> None:
        calls = find_interpreter_calls('cd a && python3 -m pytest -q', GuardOptions())

        assert calls == (
            InterpreterCall('python3', 'python3 -m pytest -q', 'uv run python -m pytest -q'),
        )

    def test_the_runner_comes_from_the_options(self) -> None:
        options = GuardOptions(runner_prefix='uv run --frozen')

        calls = find_interpreter_calls('python x', options)

        assert tuple(call.suggestion for call in calls) == ('uv run --frozen python x',)

    def test_non_ascii_text_keeps_its_offsets(self) -> None:
        command = 'echo "héllo" && python3 "naïve.py"'

        assert suggestions_for(command) == ('uv run python "naïve.py"',)

    def test_a_long_chain_stays_linear(self) -> None:
        command = ' && '.join(('true',) * 8000 + ('python x',))

        assert suggestions_for(command) == ('uv run python x',)


class TestJudgeToolCall:
    def test_a_plain_python_call_gets_a_nudge(self) -> None:
        verdict = judge_tool_call(BashCall('python x'))

        assert verdict == Nudge((InterpreterCall('python', 'python x', 'uv run python x'),))

    def test_a_bash_call_without_one_stays_quiet(self) -> None:
        assert judge_tool_call(BashCall('ls')) == NoNudge()

    def test_another_tool_stays_quiet(self) -> None:
        assert judge_tool_call(OtherToolCall('Edit')) == NoNudge()
