import os
from pathlib import Path

import pytest
from vibe_code_cli.builtin import BuiltinUnavailableError, parse_report
from vibe_code_cli.cli import main
from vibe_code_cli.findings import Finding, error, warning
from vibe_code_cli.skill import command as skill_command

DESCRIPTION = 'Summarize a file. Use when the user asks for a summary of a file.'
NAME_MAPPING = f'name: {{a: b}}\ndescription: {DESCRIPTION}\n'
NO_DESCRIPTION = 'name: sibling-skill\n'


def write_skill(root: Path, frontmatter: str | None = None, directory: str = 'demo-skill') -> Path:
    skill_dir = root / directory
    skill_dir.mkdir()
    frontmatter = frontmatter or f'name: {directory}\ndescription: {DESCRIPTION}\n'
    (skill_dir / 'SKILL.md').write_text(f'---\n{frontmatter}---\n# Demo\n\nBody.\n')
    return skill_dir


def stub_builtin(monkeypatch: pytest.MonkeyPatch, findings: list[Finding]) -> None:
    monkeypatch.setattr(skill_command, 'run_builtin', lambda _target: findings)


def test_validate_help_shows_the_skill_directory_and_strict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['skill', 'validate', '--help'])

    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert 'SKILL_DIR' in output
    assert '--strict' in output


def test_create_skill_without_a_command_prints_usage_and_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(['skill']) == 2
    assert 'usage: vibe-code' in capsys.readouterr().err


def test_clean_skill_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch, [])

    assert main(['skill', 'validate', str(write_skill(tmp_path))]) == 0
    assert 'PASS demo-skill' in capsys.readouterr().out


def test_builtin_error_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch, [error('name must be a string, got object.')])

    assert main(['skill', 'validate', str(write_skill(tmp_path))]) == 1
    assert 'error: name must be a string' in capsys.readouterr().out


def test_own_check_error_exits_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub_builtin(monkeypatch, [])
    skill_dir = write_skill(tmp_path, f'name: other\ndescription: {DESCRIPTION}\n')

    assert main(['skill', 'validate', str(skill_dir)]) == 1


def test_warning_exits_zero_and_strict_turns_it_into_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_builtin(monkeypatch, [warning('No description in frontmatter.')])
    skill_dir = str(write_skill(tmp_path))

    assert main(['skill', 'validate', skill_dir]) == 0
    assert main(['skill', 'validate', skill_dir, '--strict']) == 1


def test_builtin_that_cannot_run_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unavailable(_target: Path) -> list[Finding]:
        message = 'claude plugin validate printed no JSON report'
        raise BuiltinUnavailableError(message)

    monkeypatch.setattr(skill_command, 'run_builtin', unavailable)

    assert main(['skill', 'validate', str(write_skill(tmp_path))]) == 2
    assert 'PASS' not in capsys.readouterr().out


def test_path_that_is_not_a_directory_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(['skill', 'validate', str(tmp_path / 'missing')]) == 2
    assert 'is not a directory' in capsys.readouterr().err


def test_without_claude_on_path_exits_two_naming_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    skill_dir = write_skill(tmp_path)
    monkeypatch.setenv('PATH', str(tmp_path))

    assert main(['skill', 'validate', str(skill_dir)]) == 2
    captured = capsys.readouterr()
    assert 'claude is not on PATH' in captured.err
    assert 'PASS' not in captured.out


def test_parse_report_reads_errors_and_warnings_from_contents() -> None:
    report = (
        '{"success": false, "manifest": null, "contents": [{"file": "f", "type": "skill", '
        '"errors": [{"path": "name", "message": "bad name", "code": null}], '
        '"warnings": [{"path": "d", "message": "no description", "code": null}], "notes": []}]}'
    )

    assert parse_report(report) == [error('name: bad name'), warning('d: no description')]


def test_parse_report_prefixes_a_finding_with_its_path_only_when_it_has_one() -> None:
    report = (
        '{"success": false, "manifest": null, "contents": [{"errors": ['
        '{"path": "mcpServers.db.command", "message": "expected string", "code": null}, '
        '{"path": "", "message": "empty path", "code": null}, '
        '{"message": "no path"}], "warnings": []}]}'
    )

    assert parse_report(report) == [
        error('mcpServers.db.command: expected string'),
        error('empty path'),
        error('no path'),
    ]


def test_parse_report_rejects_output_that_is_not_json() -> None:
    with pytest.raises(BuiltinUnavailableError):
        parse_report('Error: something broke')


def test_builtin_runs_for_a_skill_under_a_directory_named_skills(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skills = tmp_path / 'skills'
    skills.mkdir()
    skill_dir = write_skill(skills, NAME_MAPPING)
    write_skill(skills, NO_DESCRIPTION, directory='sibling-skill')

    assert main(['skill', 'validate', str(skill_dir)]) == 1
    output = capsys.readouterr().out
    assert 'name must be a string' in output
    assert 'No description in frontmatter' not in output


def test_builtin_runs_for_a_skill_under_a_directory_with_another_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    collection = tmp_path / 'collection'
    collection.mkdir()
    skill_dir = write_skill(collection, NAME_MAPPING)
    write_skill(collection, NO_DESCRIPTION, directory='sibling-skill')

    assert main(['skill', 'validate', str(skill_dir)]) == 1
    output = capsys.readouterr().out
    assert 'name must be a string' in output
    assert 'No description in frontmatter' not in output


def test_invalid_yaml_the_builtin_passed_exits_two_without_a_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch, [])
    skill_dir = write_skill(tmp_path, 'name: demo-skill\ndescription: [unclosed\n')

    assert main(['skill', 'validate', str(skill_dir)]) == 2
    captured = capsys.readouterr()
    assert 'not valid YAML' in captured.err
    assert 'PASS' not in captured.out
    assert 'FAIL' not in captured.out


def test_invalid_yaml_the_builtin_reported_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch, [error('YAML frontmatter failed to parse')])
    skill_dir = write_skill(tmp_path, 'name: demo-skill\ndescription: "unclosed\n')

    assert main(['skill', 'validate', str(skill_dir)]) == 1
    assert 'FAIL demo-skill' in capsys.readouterr().out


def test_unreadable_skill_file_exits_two_naming_the_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skill_dir = write_skill(tmp_path)
    skill_md = skill_dir / 'SKILL.md'
    skill_md.chmod(0)
    if os.access(skill_md, os.R_OK):
        pytest.skip('this user can read a mode 000 file')

    assert main(['skill', 'validate', str(skill_dir)]) == 2
    captured = capsys.readouterr()
    assert str(skill_md) in captured.err
    assert 'PASS' not in captured.out
    assert 'FAIL' not in captured.out
