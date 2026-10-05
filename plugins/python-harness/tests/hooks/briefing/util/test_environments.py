"""pyvenv.cfg contents and pin mismatches."""

import pytest
from python_harness.hooks.briefing.domain import VirtualEnvironment
from python_harness.hooks.briefing.util.environments import (
    environment_differs_from_pin,
    environment_from_config,
    parse_pyvenv_config,
)


class TestPyvenvConfig:
    def test_version_info_wins_over_version(self) -> None:
        config = parse_pyvenv_config(
            'home = /usr/bin\nversion = 3.12.1\nversion_info = 3.12.1.final.0\n'
            'implementation = CPython\nnot a pair\n'
        )

        assert environment_from_config('.venv', config) == VirtualEnvironment(
            '.venv', '3.12.1.final.0', 'CPython'
        )


class TestPinMismatch:
    @pytest.mark.parametrize(
        ('pin', 'environment', 'expected'),
        [
            pytest.param('3.14', '3.14.0', False, id='same-minor'),
            pytest.param('3.14', '3.12.9', True, id='other-minor'),
            pytest.param('cpython@3.13', '3.13.1', False, id='request-form'),
            pytest.param(None, '3.12.9', False, id='no-pin'),
            pytest.param('3.14', None, False, id='no-version'),
        ],
    )
    def test_only_a_known_different_minor_differs(
        self, pin: str | None, environment: str | None, *, expected: bool
    ) -> None:
        assert environment_differs_from_pin(pin, environment) is expected
