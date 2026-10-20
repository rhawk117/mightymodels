from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from mightymodels_core.edge import (
    PLUGIN_DATA_VARIABLE,
    SESSION_DATA_VARIABLE,
    DataDirectoryMissingError,
    data_directory_from,
    export_line,
)


def unset_or_empty_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'environ',
        [
            pytest.param({}, id='unset'),
            pytest.param({PLUGIN_DATA_VARIABLE: ''}, id='empty'),
            pytest.param({SESSION_DATA_VARIABLE: '/data'}, id='only-the-other-variable'),
        ],
    )


class TestDataDirectoryFrom:
    directories = st.text(min_size=1).filter(lambda text: '\0' not in text)

    @given(directory=directories)
    def test_a_set_variable_is_the_directory(self, directory: str) -> None:
        assert data_directory_from({PLUGIN_DATA_VARIABLE: directory}, PLUGIN_DATA_VARIABLE) == Path(
            directory
        )

    @unset_or_empty_cases()
    def test_an_unset_or_empty_variable_is_the_refusal_naming_it(
        self, environ: dict[str, str]
    ) -> None:
        refusal = data_directory_from(environ, PLUGIN_DATA_VARIABLE)

        assert isinstance(refusal, DataDirectoryMissingError)
        assert refusal.variable == PLUGIN_DATA_VARIABLE
        assert PLUGIN_DATA_VARIABLE in str(refusal)

    def test_there_is_no_fallback_to_the_other_variable(self) -> None:
        environ = {PLUGIN_DATA_VARIABLE: '/plugin', SESSION_DATA_VARIABLE: '/session'}

        assert data_directory_from(environ, SESSION_DATA_VARIABLE) == Path('/session')


class TestExportLine:
    def test_the_line_exports_the_session_variable(self) -> None:
        assert export_line(Path('/data')) == f'export {SESSION_DATA_VARIABLE}=/data\n'

    def test_a_directory_with_a_space_is_quoted(self) -> None:
        assert export_line(Path('/my data')) == f"export {SESSION_DATA_VARIABLE}='/my data'\n"
