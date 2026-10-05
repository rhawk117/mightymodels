"""The note Claude reads after a plain-python command, and the briefing's rule line."""

from python_harness.hooks.guard.domain import GuardOptions, InterpreterCall, Nudge
from python_harness.hooks.guard.util.presentation import (
    describe_guard_rule,
    render_note,
)


class TestNote:
    def test_each_call_is_shown_with_its_suggestion(self) -> None:
        verdict = Nudge(
            (
                InterpreterCall('python3', 'python3 -m pytest', 'uv run python -m pytest'),
                InterpreterCall('python', 'echo `python -V`', 'echo `uv run python -V`'),
            )
        )

        note = render_note(verdict, GuardOptions())

        assert note.splitlines() == [
            (
                'Note from the pythonista plugin: this command ran plain `python`,'
                ' `python3`, which can pick a different interpreter or packages than the'
                ' project environment, so its result may be incorrect. Run Python with'
                ' `uv run python`, and rerun it that way if the result matters:'
            ),
            '- `python3 -m pytest` -> `uv run python -m pytest`',
            '- `` echo `python -V` `` -> `` echo `uv run python -V` ``',
        ]

    def test_calls_past_the_limit_are_counted(self) -> None:
        call = InterpreterCall('python', 'python x', 'uv run python x')

        note = render_note(Nudge((call,) * 5), GuardOptions(max_listed_calls=2))

        assert note.splitlines()[1:] == [
            '- `python x` -> `uv run python x`',
            '- `python x` -> `uv run python x`',
            '- (+3 more)',
        ]


class TestGuardRule:
    def test_the_rule_names_the_runner_and_the_risk(self) -> None:
        assert describe_guard_rule(GuardOptions()) == (
            '- Run Python with `uv run python ...`: plain python, python3 or pythonX.Y'
            ' can pick a different interpreter or packages than the project environment'
            ' and give an incorrect result. The pythonista plugin adds a note when a'
            ' Bash command runs one.'
        )
