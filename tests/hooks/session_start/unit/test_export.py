from typing import TYPE_CHECKING

import pytest
from mightymodels_core.edge import PLUGIN_DATA_VARIABLE, DataDirectoryMissingError, export_line
from mightymodels_hooks.session_start import (
    ENV_FILE_VARIABLE,
    EnvFileMissingError,
    export_data_directory,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestExportDataDirectory:
    @pytest.fixture
    def environ(self, env_file: Path, data_directory: Path) -> dict[str, str]:
        return {PLUGIN_DATA_VARIABLE: str(data_directory), ENV_FILE_VARIABLE: str(env_file)}

    def test_export_is_appended_once(
        self, environ: dict[str, str], env_file: Path, data_directory: Path
    ) -> None:
        export_data_directory(environ)
        first = env_file.read_bytes()
        export_data_directory(environ)
        assert (env_file.read_bytes(), first) == (first, export_line(data_directory).encode())

    def test_returns_the_data_directory(
        self, environ: dict[str, str], data_directory: Path
    ) -> None:
        assert export_data_directory(environ) == data_directory

    def test_last_line_without_newline_is_ended_first(
        self, environ: dict[str, str], env_file: Path, data_directory: Path
    ) -> None:
        env_file.write_bytes(b'export OTHER=1')
        export_data_directory(environ)
        assert env_file.read_bytes() == b'export OTHER=1\n' + export_line(data_directory).encode()

    def test_export_without_newline_is_left_alone(
        self, environ: dict[str, str], env_file: Path, data_directory: Path
    ) -> None:
        held = export_line(data_directory).rstrip('\n').encode()
        env_file.write_bytes(held)
        export_data_directory(environ)
        assert env_file.read_bytes() == held

    def test_carriage_return_is_not_translated(
        self, environ: dict[str, str], env_file: Path, data_directory: Path
    ) -> None:
        env_file.write_bytes(b'export OTHER=1\r\n')
        export_data_directory(environ)
        assert env_file.read_bytes() == b'export OTHER=1\r\n' + export_line(data_directory).encode()

    def test_missing_data_directory_variable_is_reported(
        self, environ: dict[str, str], env_file: Path
    ) -> None:
        del environ[PLUGIN_DATA_VARIABLE]
        assert isinstance(export_data_directory(environ), DataDirectoryMissingError)
        assert not env_file.exists()

    def test_missing_env_file_variable_is_reported(self, environ: dict[str, str]) -> None:
        del environ[ENV_FILE_VARIABLE]
        assert isinstance(export_data_directory(environ), EnvFileMissingError)
