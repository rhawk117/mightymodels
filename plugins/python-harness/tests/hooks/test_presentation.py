"""Markdown pieces both hooks share."""

import pytest
from python_harness.hooks.presentation import code_span, shorten_line


class TestCodeSpan:
    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            pytest.param('uv run python', '`uv run python`', id='plain'),
            pytest.param('echo `x`', '`` echo `x` ``', id='with-backticks'),
            pytest.param('a `` b', '``` a `` b ```', id='with-a-double-backtick'),
            pytest.param('a ``` b', '```` a ``` b ````', id='with-a-triple-backtick'),
            pytest.param('a ` b ``` c `` d', '```` a ` b ``` c `` d ````', id='longest-run-wins'),
        ],
    )
    def test_the_span_survives_backticks(self, text: str, expected: str) -> None:
        assert code_span(text) == expected


class TestShortenLine:
    def test_a_multi_line_text_shows_its_first_line(self) -> None:
        assert shorten_line("python3 - <<'EOF'\nprint(1)\nEOF", 80) == ("python3 - <<'EOF' ...")

    def test_a_long_line_is_cut(self) -> None:
        assert shorten_line('python ' + 'x' * 20, 10) == 'python xxx...'

    def test_an_empty_text_stays_empty(self) -> None:
        assert shorten_line('', 10) == ''
