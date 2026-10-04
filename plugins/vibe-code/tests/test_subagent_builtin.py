from pathlib import Path

import pytest
from vibe_code_cli.cli import main
from vibe_code_cli.subagent.tests.support import AgentRoot, agent_text


class TestRealBuiltin:
    UNCLOSED_QUOTE = agent_text({'description': '"unclosed'})
    ASKED = agent_text({'description': 'Reviews code. Use when asked.'})

    @pytest.fixture
    def no_claude_on_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('PATH', str(tmp_path))

    @pytest.mark.parametrize(
        'plugin', [pytest.param(False, id='False'), pytest.param(True, id='True')]
    )
    def test_unclosed_description_quote_prints_the_builtin_parse_error_and_exits_one(
        self, subagent_root: AgentRoot, capsys: pytest.CaptureFixture[str], *, plugin: bool
    ) -> None:
        path = subagent_root.write(self.UNCLOSED_QUOTE, plugin=plugin)

        assert main(['subagent', 'validate', str(path)]) == 1
        output = capsys.readouterr().out
        assert 'YAML frontmatter failed to parse' in output
        assert 'plugin.json' not in output
        assert 'author' not in output

    @pytest.mark.usefixtures('no_claude_on_path')
    def test_without_claude_on_path_exits_two_naming_claude(
        self, subagent_root: AgentRoot, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = subagent_root.write(self.ASKED)

        assert main(['subagent', 'validate', str(path)]) == 2
        captured = capsys.readouterr()
        assert 'claude is not on PATH' in captured.err
        assert 'PASS' not in captured.out
