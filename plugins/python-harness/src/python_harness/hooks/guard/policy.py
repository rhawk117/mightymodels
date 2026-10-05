"""Which words start plain python: a bare interpreter name, with no path, as a command."""

from python_harness.hooks.guard.domain import GuardOptions
from python_harness.hooks.guard.util.shell import Word


def interpreter_name(word: Word, options: GuardOptions) -> str | None:
    if word.value is None or options.interpreter.fullmatch(word.value) is None:
        return None
    return word.value
