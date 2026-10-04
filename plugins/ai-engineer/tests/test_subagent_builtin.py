from pathlib import Path

import pytest
from ai_engineer_cli.cli import main

# The two tests that spawn the real `claude` are the ones taking no `monkeypatch`.
CLEAN_BODY = ''.join(
    f'<{name}>\nText.\n</{name}>\n\n'
    for name in ('role', 'context', 'workflow', 'constraints', 'output_format', 'verification')
)


def agent_text(description: str) -> str:
    return (
        f'---\nname: demo-agent\ndescription: {description}\ntools: Read, Grep\n---\n{CLEAN_BODY}'
    )


def write_agent(root: Path, text: str, *, plugin: bool = False) -> Path:
    directory = root / 'plugin' / 'agents' if plugin else root / '.claude' / 'agents'
    directory.mkdir(parents=True)
    path = directory / 'demo-agent.md'
    path.write_text(text)
    return path


@pytest.mark.parametrize('plugin', [False, True])
def test_unclosed_description_quote_prints_the_builtin_parse_error_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], *, plugin: bool
) -> None:
    path = write_agent(tmp_path, agent_text('"unclosed'), plugin=plugin)

    assert main(['create-subagent', 'validate', str(path)]) == 1
    output = capsys.readouterr().out
    assert 'YAML frontmatter failed to parse' in output
    assert 'plugin.json' not in output
    assert 'author' not in output


def test_without_claude_on_path_exits_two_naming_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_agent(tmp_path, agent_text('Reviews code. Use when asked.'))
    monkeypatch.setenv('PATH', str(tmp_path))

    assert main(['create-subagent', 'validate', str(path)]) == 2
    captured = capsys.readouterr()
    assert 'claude is not on PATH' in captured.err
    assert 'PASS' not in captured.out
