"""The note Claude reads after a plain-python command, and the briefing's rule line."""

from python_harness.hooks.guard.domain import GuardOptions, InterpreterCall, Nudge
from python_harness.hooks.presentation import code_span, shorten_line


def call_line(call: InterpreterCall, limit: int) -> str:
    command = code_span(shorten_line(call.command, limit))
    suggestion = code_span(shorten_line(call.suggestion, limit))
    return f'- {command} -> {suggestion}'


def more_calls_line(hidden: int) -> tuple[str, ...]:
    if hidden <= 0:
        return ()
    return (f'- (+{hidden} more)',)


def render_note(verdict: Nudge, options: GuardOptions) -> str:
    names = sorted({call.interpreter for call in verdict.calls})
    interpreters = ', '.join(code_span(name) for name in names)
    explanation = (
        f'Note from the python-harness plugin: this command ran plain {interpreters},'
        ' which can pick a different interpreter or packages than the project'
        ' environment, so its result may be incorrect. Run Python with'
        f' {code_span(options.replacement)}, and rerun it that way if the result'
        ' matters:'
    )
    shown = verdict.calls[: options.max_listed_calls]
    limit = options.shown_command_characters
    calls = tuple(call_line(call, limit) for call in shown)
    hidden = more_calls_line(len(verdict.calls) - len(shown))
    return '\n'.join((explanation, *calls, *hidden))


def describe_guard_rule(options: GuardOptions) -> str:
    return (
        f'- Run Python with {code_span(options.replacement + " ...")}: plain'
        f' {options.interpreter_names} can pick a different interpreter or packages'
        ' than the project environment and give an incorrect result. The python-harness'
        ' plugin adds a note when a Bash command runs one.'
    )
