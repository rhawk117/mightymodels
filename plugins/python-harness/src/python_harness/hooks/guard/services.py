"""Judging a Bash call: the plain-python commands in it and what to run instead."""

from python_harness.hooks.domain import OtherToolCall, ToolCall
from python_harness.hooks.guard.domain import (
    GuardOptions,
    GuardVerdict,
    InterpreterCall,
    NoNudge,
    Nudge,
)
from python_harness.hooks.guard.policy import interpreter_name
from python_harness.hooks.guard.util.shell import SimpleCommand, parse_simple_commands


def interpreter_call(command: SimpleCommand, options: GuardOptions) -> InterpreterCall | None:
    head = command.words[0]
    name = interpreter_name(head, options)
    if name is None:
        return None
    suggestion = command.replace_span(head.start, head.end, options.replacement)
    return InterpreterCall(name, command.text, suggestion)


def find_interpreter_calls(script: str, options: GuardOptions) -> tuple[InterpreterCall, ...]:
    commands = parse_simple_commands(script.encode('utf-8', errors='replace'))
    calls = (interpreter_call(command, options) for command in commands)
    return tuple(call for call in calls if call is not None)


def judge_tool_call(call: ToolCall, options: GuardOptions | None = None) -> GuardVerdict:
    chosen = GuardOptions() if options is None else options
    if isinstance(call, OtherToolCall):
        return NoNudge()
    calls = find_interpreter_calls(call.command, chosen)
    if not calls:
        return NoNudge()
    return Nudge(calls)
