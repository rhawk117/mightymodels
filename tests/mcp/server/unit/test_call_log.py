from io import StringIO
from pathlib import Path
from types import MappingProxyType

import pytest
from mightymodels_mcp.server.call_log import (
    LOG_LEVEL_VARIABLE,
    LOG_LEVELS,
    InvalidLogLevelError,
    LogSettings,
    parse_log_level,
)


class TestParseLogLevel:
    def test_default_is_info(self) -> None:
        assert parse_log_level(MappingProxyType({})) == 'INFO'

    @pytest.mark.parametrize('level', LOG_LEVELS)
    def test_each_accepted_level_is_returned(self, level: str) -> None:
        assert parse_log_level({LOG_LEVEL_VARIABLE: level}) == level

    def test_case_is_ignored(self) -> None:
        assert parse_log_level({LOG_LEVEL_VARIABLE: 'warning'}) == 'WARNING'

    def test_unknown_level_names_the_accepted_ones(self) -> None:
        outcome = parse_log_level({LOG_LEVEL_VARIABLE: 'LOUD'})
        assert isinstance(outcome, InvalidLogLevelError)
        assert str(outcome).count('\n') == 0
        assert all(level in str(outcome) for level in LOG_LEVELS)


class TestLogSettings:
    settings = LogSettings(level='INFO', data_directory=Path('data'), stream=StringIO())

    def test_file_lives_under_the_logs_directory(self) -> None:
        assert self.settings.file_path.parent == Path('data', 'logs')
