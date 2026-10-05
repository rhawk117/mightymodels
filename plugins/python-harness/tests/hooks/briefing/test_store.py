"""Bounded reads that return every problem as a value."""

from pathlib import Path

from python_harness.hooks.briefing.domain import (
    IniDocument,
    MissingFile,
    TextFile,
    TomlDocument,
    UnreadableFile,
)
from python_harness.hooks.briefing.store import read_ini, read_text, read_toml


class TestReadText:
    def test_a_missing_file_is_missing(self, tmp_path: Path) -> None:
        assert read_text(tmp_path / 'absent', 'absent', 10) == MissingFile()

    def test_a_directory_is_missing(self, tmp_path: Path) -> None:
        assert read_text(tmp_path, 'dir', 10) == MissingFile()

    def test_a_file_over_the_limit_is_unreadable(self, tmp_path: Path) -> None:
        path = tmp_path / 'big'
        path.write_bytes(b'x' * 11)

        assert read_text(path, 'big', 10) == UnreadableFile('big', 'is larger than 10 bytes')

    def test_a_file_at_the_limit_is_read(self, tmp_path: Path) -> None:
        path = tmp_path / 'ok'
        path.write_bytes(b'x' * 10)

        assert read_text(path, 'ok', 10) == TextFile('x' * 10)

    def test_bytes_that_are_not_utf8_are_unreadable(self, tmp_path: Path) -> None:
        path = tmp_path / 'latin'
        path.write_bytes(b'caf\xe9')

        assert read_text(path, 'latin', 10) == UnreadableFile(
            'latin', 'is not UTF-8: unexpected end of data'
        )


class TestReadToml:
    def test_valid_toml_is_a_document(self, tmp_path: Path) -> None:
        path = tmp_path / 'a.toml'
        path.write_text('a = 1\n', encoding='utf-8')

        assert read_toml(path, 'a.toml', 100) == TomlDocument({'a': 1})

    def test_invalid_toml_names_the_line(self, tmp_path: Path) -> None:
        path = tmp_path / 'a.toml'
        path.write_text('a = 1\nb = \n', encoding='utf-8')

        assert read_toml(path, 'a.toml', 100) == UnreadableFile(
            'a.toml', 'is not valid TOML: Invalid value (line 2)'
        )


class TestReadIni:
    def test_sections_are_read_without_interpolation(self, tmp_path: Path) -> None:
        path = tmp_path / 'tox.ini'
        path.write_text('[pytest]\naddopts = -q %(x)s\n', encoding='utf-8')

        assert read_ini(path, 'tox.ini', 100) == IniDocument({'pytest': {'addopts': '-q %(x)s'}})

    def test_text_without_a_section_is_unreadable(self, tmp_path: Path) -> None:
        path = tmp_path / 'setup.cfg'
        path.write_text('key = value\n', encoding='utf-8')

        assert read_ini(path, 'setup.cfg', 100) == UnreadableFile(
            'setup.cfg', 'is not valid INI: File contains no section headers.'
        )
