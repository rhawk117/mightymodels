"""Simple commands and their words from a tree-sitter-bash parse."""

import pytest
from python_harness.hooks.guard.util.shell import Word, parse_simple_commands


def words_of(script: str) -> list[list[str | None]]:
    commands = parse_simple_commands(script.encode())
    return [[word.value for word in command.words] for command in commands]


class TestLiteralValues:
    @pytest.mark.parametrize(
        ('script', 'expected'),
        [
            pytest.param('echo a b', [['echo', 'a', 'b']], id='words'),
            pytest.param("echo 'a b'", [['echo', 'a b']], id='raw-string'),
            pytest.param('echo "a \\"b\\" \\q"', [['echo', 'a "b" \\q']], id='string'),
            pytest.param('echo "$HOME"', [['echo', None]], id='string-expansion'),
            pytest.param('echo a\\ b', [['echo', 'a b']], id='escaped-space'),
            pytest.param('echo "py"thon', [['echo', 'python']], id='concatenation'),
            pytest.param('echo $x', [['echo', None]], id='expansion'),
            pytest.param('timeout 5 x', [['timeout', '5', 'x']], id='number'),
            pytest.param('echo ""', [['echo', '']], id='empty-string'),
        ],
    )
    def test_words_have_their_shell_values(
        self, script: str, expected: list[list[str | None]]
    ) -> None:
        assert words_of(script) == expected


class TestCommands:
    def test_assignments_and_redirections_are_not_words(self) -> None:
        assert words_of('A=1 python x > out 2>&1') == [['python', 'x']]

    def test_nested_commands_come_after_their_parent(self) -> None:
        assert words_of('echo $(date) && ls') == [['echo', None], ['date'], ['ls']]

    def test_an_assignment_alone_is_not_a_command(self) -> None:
        assert words_of('A=1') == []

    def test_a_heredoc_body_is_data(self) -> None:
        assert words_of("cat <<'EOF'\npython x\nEOF") == [['cat']]


class TestSourceSpans:
    def test_a_word_spans_its_bytes_in_the_command(self) -> None:
        command = parse_simple_commands(b'A=1 python3 x >o')[0]

        assert (command.text, command.words[0]) == (
            'A=1 python3 x',
            Word('python3', 'python3', 4, 11),
        )

    def test_replacing_a_span_keeps_the_rest_of_the_command(self) -> None:
        command = parse_simple_commands('python3 "é"'.encode())[0]
        word = command.words[0]

        assert command.replace_span(word.start, word.end, 'uv run python') == ('uv run python "é"')
