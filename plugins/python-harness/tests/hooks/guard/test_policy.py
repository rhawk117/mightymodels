"""Bare interpreter names, judged without a parser."""

import pytest
from python_harness.hooks.guard.domain import GuardOptions
from python_harness.hooks.guard.policy import interpreter_name
from python_harness.hooks.guard.util.shell import Word


class TestInterpreterName:
    @pytest.mark.parametrize(
        ('value', 'expected'),
        [
            pytest.param('python', 'python', id='python'),
            pytest.param('python3', 'python3', id='python3'),
            pytest.param('python3.13', 'python3.13', id='versioned'),
            pytest.param('/usr/bin/python3', None, id='path'),
            pytest.param('python3.x', None, id='not-a-version'),
            pytest.param('pythonw', None, id='other-program'),
            pytest.param(None, None, id='expansion'),
        ],
    )
    def test_only_bare_interpreter_names_match(
        self, value: str | None, expected: str | None
    ) -> None:
        word = Word(value, value or '$X', 0, len(value or '$X'))

        assert interpreter_name(word, GuardOptions()) == expected
