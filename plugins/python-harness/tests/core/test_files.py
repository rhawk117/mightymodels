"""OS error wording and `.python-version` pins."""

import pytest
from python_harness.core.files import describe_os_error, parse_version_pin


class TestParseVersionPin:
    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            pytest.param('3.14\n', '3.14', id='plain'),
            pytest.param('# uv pin\n\n  3.13.2  \n3.12\n', '3.13.2', id='comments'),
            pytest.param('cpython@3.14\n', 'cpython@3.14', id='request'),
            pytest.param('\n# only a comment\n', None, id='no-pin'),
            pytest.param('3' * 100, '3' * 64, id='capped'),
        ],
    )
    def test_the_first_pin_line_is_read(self, text: str, expected: str | None) -> None:
        assert parse_version_pin(text) == expected


class TestDescribeOsError:
    def test_the_strerror_is_preferred(self) -> None:
        assert describe_os_error(PermissionError(13, 'Permission denied')) == ('Permission denied')

    def test_the_type_names_an_error_without_one(self) -> None:
        assert describe_os_error(OSError()) == 'OSError'
