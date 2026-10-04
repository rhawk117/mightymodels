import os
from pathlib import Path

import pytest
from ai_engineer_cli.builtin import BuiltinUnavailableError
from ai_engineer_cli.cli import main
from ai_engineer_cli.findings import Finding, error, warning
from ai_engineer_cli.subagent import command as subagent_command

SECTIONS = ('role', 'context', 'workflow', 'constraints', 'output_format', 'verification')
DESCRIPTION = 'Reviews code for defects. Use when the user asks for a code review.'
CLEAN_FIELDS: dict[str, str | None] = {
    'name': 'demo-agent',
    'description': DESCRIPTION,
    'tools': 'Read, Grep',
}


def sections(names: tuple[str, ...] = SECTIONS) -> str:
    return ''.join(f'<{name}>\nText.\n</{name}>\n\n' for name in names)


def agent_text(fields: dict[str, str | None] | None = None, body: str | None = None) -> str:
    """An agent file; a field set to None is dropped."""
    merged = {**CLEAN_FIELDS, **(fields or {})}
    lines = [f'{key}: {value}' for key, value in merged.items() if value is not None]
    return '---\n' + '\n'.join(lines) + '\n---\n' + (sections() if body is None else body)


def write_agent(
    root: Path, text: str, *, plugin: bool = False, name: str = 'demo-agent.md'
) -> Path:
    directory = root / 'plugin' / 'agents' if plugin else root / '.claude' / 'agents'
    directory.mkdir(parents=True)
    path = directory / name
    path.write_text(text)
    return path


def run(path: Path, capsys: pytest.CaptureFixture[str], *options: str) -> tuple[int, str]:
    code = main(['subagent', 'validate', str(path), *options])
    return code, capsys.readouterr().out


@pytest.fixture
def builtin_findings(monkeypatch: pytest.MonkeyPatch) -> list[Finding]:
    """What the stubbed built-in reports; a test appends to it."""
    findings: list[Finding] = []
    monkeypatch.setattr(subagent_command, 'run_builtin', lambda _target, **_options: findings)
    return findings


def check(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    text: str,
    *,
    plugin: bool = False,
    strict: bool = False,
) -> tuple[int, str]:
    path = write_agent(tmp_path, text, plugin=plugin)
    return run(path, capsys, *(['--strict'] if strict else []))


pytestmark = pytest.mark.usefixtures('builtin_findings')


def test_validate_help_shows_the_file_and_strict(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['subagent', 'validate', '--help'])

    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert 'FILE' in output
    assert '--strict' in output


def test_create_subagent_without_a_command_prints_usage_and_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(['subagent']) == 2
    assert 'usage: ai-engineer' in capsys.readouterr().err


@pytest.mark.parametrize('plugin', [False, True])
def test_clean_agent_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], *, plugin: bool
) -> None:
    code, output = check(tmp_path, capsys, agent_text(), plugin=plugin)

    assert code == 0
    assert 'PASS demo-agent.md: 0 error(s), 0 warning(s)' in output


def test_path_that_is_not_a_markdown_file_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text_file = tmp_path / 'agent.txt'
    text_file.write_text(agent_text())

    for path in (text_file, tmp_path, tmp_path / 'missing.md'):
        assert main(['subagent', 'validate', str(path)]) == 2
        captured = capsys.readouterr()
        assert 'is not a .md file' in captured.err
        assert 'PASS' not in captured.out


def test_unreadable_agent_file_exits_two_naming_the_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_agent(tmp_path, agent_text())
    path.chmod(0)
    if os.access(path, os.R_OK):
        pytest.skip('this user can read a mode 000 file')

    assert main(['subagent', 'validate', str(path)]) == 2
    captured = capsys.readouterr()
    assert str(path) in captured.err
    assert 'PASS' not in captured.out
    assert 'FAIL' not in captured.out


def test_file_that_is_not_utf8_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_agent(tmp_path, '')
    path.write_bytes(b'---\nname: \xff\n---\n')

    assert main(['subagent', 'validate', str(path)]) == 2
    assert 'could not read' in capsys.readouterr().err


def test_warning_exits_zero_and_strict_turns_it_into_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_agent(tmp_path, agent_text({'tools': None}))

    assert run(path, capsys)[0] == 0
    assert run(path, capsys, '--strict')[0] == 1


def test_invalid_yaml_the_builtin_passed_exits_two_without_a_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_agent(tmp_path, agent_text({'description': '[unclosed'}))

    assert main(['subagent', 'validate', str(path)]) == 2
    captured = capsys.readouterr()
    assert 'not valid YAML' in captured.err
    assert 'PASS' not in captured.out
    assert 'FAIL' not in captured.out


def test_builtin_error_exits_one_and_skips_the_field_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], builtin_findings: list[Finding]
) -> None:
    builtin_findings.append(error('YAML frontmatter failed to parse'))
    text = agent_text({'description': '"unclosed', 'tools': None})

    code, output = check(tmp_path, capsys, text)

    assert code == 1
    assert 'error: YAML frontmatter failed to parse' in output
    assert 'inherits every tool' not in output


def test_builtin_that_cannot_run_exits_two_without_a_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unavailable(_target: Path, **_options: object) -> list[Finding]:
        message = 'claude plugin validate printed no JSON report'
        raise BuiltinUnavailableError(message)

    monkeypatch.setattr(subagent_command, 'run_builtin', unavailable)

    assert main(['subagent', 'validate', str(write_agent(tmp_path, agent_text()))]) == 2
    assert 'PASS' not in capsys.readouterr().out


def test_builtin_findings_come_before_the_own_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], builtin_findings: list[Finding]
) -> None:
    builtin_findings.append(warning('No description in frontmatter.'))

    code, output = check(tmp_path, capsys, agent_text({'tools': None}))

    assert code == 0
    assert output.index('No description in frontmatter') < output.index('inherits every tool')


def record_staging(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    seen: list[dict[str, object]] = []

    def fake(target: Path, **options: object) -> list[Finding]:
        seen.append(
            {
                'target': target.name,
                'parent': target.parent.name,
                'files': sorted(
                    str(item.relative_to(target)) for item in target.rglob('*') if item.is_file()
                ),
                'options': options,
            }
        )
        return []

    monkeypatch.setattr(subagent_command, 'run_builtin', fake)
    return seen


def test_plugin_agent_is_staged_in_a_plugin_with_the_manifest_findings_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = record_staging(monkeypatch)

    assert (
        main(
            [
                'subagent',
                'validate',
                str(write_agent(tmp_path, agent_text(), plugin=True)),
            ]
        )
        == 0
    )
    assert seen == [
        {
            'target': seen[0]['target'],
            'parent': seen[0]['parent'],
            'files': ['.claude-plugin/plugin.json', 'agents/demo-agent.md'],
            'options': {'include_manifest': False},
        }
    ]


@pytest.mark.parametrize('relative', ['.claude/agents', 'notes', 'docs/agents/.claude'])
def test_any_other_parent_is_staged_as_a_claude_agents_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    seen = record_staging(monkeypatch)
    directory = tmp_path / relative
    directory.mkdir(parents=True)
    path = directory / 'demo-agent.md'
    path.write_text(agent_text())

    assert main(['subagent', 'validate', str(path)]) == 0
    assert seen[0]['target'] == 'agents'
    assert seen[0]['parent'] == '.claude'
    assert seen[0]['files'] == ['demo-agent.md']


def test_builtin_runs_on_a_copy_of_the_one_file_not_its_siblings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = record_staging(monkeypatch)
    path = write_agent(tmp_path, agent_text())
    (path.parent / 'sibling.md').write_text('no frontmatter\n')

    assert main(['subagent', 'validate', str(path)]) == 0
    assert seen[0]['files'] == ['demo-agent.md']
