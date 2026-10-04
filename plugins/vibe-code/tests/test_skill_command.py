import os
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from vibe_code_cli.builtin import BuiltinUnavailableError, Services, parse_report
from vibe_code_cli.cli import main
from vibe_code_cli.findings import Finding, error, warning
from vibe_code_cli.skill.tests.support import DESCRIPTION, SkillRoot

type ServicesFactory = Callable[[Sequence[Finding]], Services]


class TestUsage:
    def test_validate_help_shows_the_skill_directory_and_strict(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['skill', 'validate', '--help'])

        assert exit_info.value.code == 0
        output = capsys.readouterr().out
        assert 'SKILL_DIR' in output
        assert '--strict' in output

    def test_create_skill_without_a_command_prints_usage_and_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['skill']) == 2
        assert 'usage: vibe-code' in capsys.readouterr().err


class TestBuiltinFindings:
    ERROR = (error('name must be a string, got object.'),)
    WARNING = (warning('No description in frontmatter.'),)

    @pytest.fixture
    def skill_dir(self, skill_root: SkillRoot) -> str:
        return str(skill_root.write())

    def test_clean_skill_exits_zero(
        self, skill_dir: str, fake_services: ServicesFactory, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['skill', 'validate', skill_dir], fake_services(())) == 0
        assert 'PASS demo-skill' in capsys.readouterr().out

    def test_builtin_error_exits_one(
        self, skill_dir: str, fake_services: ServicesFactory, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['skill', 'validate', skill_dir], fake_services(self.ERROR)) == 1
        assert 'error: name must be a string' in capsys.readouterr().out

    def test_warning_exits_zero_and_strict_turns_it_into_one(
        self, skill_dir: str, fake_services: ServicesFactory
    ) -> None:
        services = fake_services(self.WARNING)

        assert main(['skill', 'validate', skill_dir], services) == 0
        assert main(['skill', 'validate', skill_dir, '--strict'], services) == 1

    def test_builtin_that_cannot_run_exits_two(
        self, skill_dir: str, unavailable_services: Services, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['skill', 'validate', skill_dir], unavailable_services) == 2
        assert 'PASS' not in capsys.readouterr().out


class TestOwnChecks:
    OTHER_NAME = f'name: other\ndescription: {DESCRIPTION}\n'
    UNQUOTED_DATE = f'name: 2024-01-01\ndescription: {DESCRIPTION}\n'
    BOOL_ALIAS = f'name: on\ndescription: {DESCRIPTION}\n'
    NON_STRING_KEY = f'name: demo-skill\ndescription: {DESCRIPTION}\n1: one\n'

    def test_own_check_error_exits_one(
        self, skill_root: SkillRoot, fake_services: ServicesFactory
    ) -> None:
        skill_dir = str(skill_root.write(self.OTHER_NAME))

        assert main(['skill', 'validate', skill_dir], fake_services(())) == 1

    @pytest.mark.parametrize(
        'frontmatter',
        [
            pytest.param(UNQUOTED_DATE, id='unquoted_date'),
            pytest.param(BOOL_ALIAS, id='bool_alias'),
            pytest.param(NON_STRING_KEY, id='non_string_key'),
        ],
    )
    def test_a_yaml_typed_frontmatter_value_or_key_is_one_finding(
        self,
        skill_root: SkillRoot,
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
        frontmatter: str,
    ) -> None:
        skill_dir = str(skill_root.write(frontmatter))

        assert main(['skill', 'validate', skill_dir], fake_services(())) == 1
        captured = capsys.readouterr()
        assert 'Traceback' not in captured.err
        assert 'FAIL demo-skill: 1 error(s), 0 warning(s)' in captured.out


class TestTargetThatCannotBeChecked:
    @pytest.fixture
    def no_claude_on_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('PATH', str(tmp_path))

    @pytest.fixture
    def unreadable_skill_md(self, skill_root: SkillRoot) -> Path:
        skill_md = skill_root.write() / 'SKILL.md'
        skill_md.chmod(0)
        if os.access(skill_md, os.R_OK):
            pytest.skip('this user can read a mode 000 file')
        return skill_md

    def test_path_that_is_not_a_directory_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['skill', 'validate', str(tmp_path / 'missing')]) == 2
        assert 'is not a directory' in capsys.readouterr().err

    @pytest.mark.usefixtures('no_claude_on_path')
    def test_without_claude_on_path_exits_two_naming_claude(
        self, skill_root: SkillRoot, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['skill', 'validate', str(skill_root.write())]) == 2
        captured = capsys.readouterr()
        assert 'claude is not on PATH' in captured.err
        assert 'PASS' not in captured.out

    def test_unreadable_skill_file_exits_two_naming_the_path(
        self, unreadable_skill_md: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['skill', 'validate', str(unreadable_skill_md.parent)]) == 2
        captured = capsys.readouterr()
        assert str(unreadable_skill_md) in captured.err
        assert 'PASS' not in captured.out
        assert 'FAIL' not in captured.out


class TestParseReport:
    ERRORS_AND_WARNINGS = (
        '{"success": false, "manifest": null, "contents": [{"file": "f", "type": "skill", '
        '"errors": [{"path": "name", "message": "bad name", "code": null}], '
        '"warnings": [{"path": "d", "message": "no description", "code": null}], "notes": []}]}'
    )
    PATHS = (
        '{"success": false, "manifest": null, "contents": [{"errors": ['
        '{"path": "mcpServers.db.command", "message": "expected string", "code": null}, '
        '{"path": "", "message": "empty path", "code": null}, '
        '{"message": "no path"}], "warnings": []}]}'
    )
    NOT_JSON = 'Error: something broke'

    def test_parse_report_reads_errors_and_warnings_from_contents(self) -> None:
        assert parse_report(self.ERRORS_AND_WARNINGS) == [
            error('name: bad name'),
            warning('d: no description'),
        ]

    def test_parse_report_prefixes_a_finding_with_its_path_only_when_it_has_one(self) -> None:
        assert parse_report(self.PATHS) == [
            error('mcpServers.db.command: expected string'),
            error('empty path'),
            error('no path'),
        ]

    def test_parse_report_rejects_output_that_is_not_json(self) -> None:
        with pytest.raises(BuiltinUnavailableError):
            parse_report(self.NOT_JSON)


class TestRealBuiltin:
    NAME_MAPPING = f'name: {{a: b}}\ndescription: {DESCRIPTION}\n'
    NO_DESCRIPTION = 'name: sibling-skill\n'

    def skill_beside_a_sibling(self, parent: Path) -> str:
        siblings = SkillRoot(root=parent)
        siblings.write(self.NO_DESCRIPTION, directory='sibling-skill')
        return str(siblings.write(self.NAME_MAPPING))

    def assert_only_the_named_skill_is_reported(
        self, skill_dir: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['skill', 'validate', skill_dir]) == 1
        output = capsys.readouterr().out
        assert 'name must be a string' in output
        assert 'No description in frontmatter' not in output

    @pytest.fixture
    def under_skills(self, tmp_path: Path) -> str:
        return self.skill_beside_a_sibling(tmp_path / 'skills')

    @pytest.fixture
    def under_another_name(self, tmp_path: Path) -> str:
        return self.skill_beside_a_sibling(tmp_path / 'collection')

    def test_builtin_runs_for_a_skill_under_a_directory_named_skills(
        self, under_skills: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.assert_only_the_named_skill_is_reported(under_skills, capsys)

    def test_builtin_runs_for_a_skill_under_a_directory_with_another_name(
        self, under_another_name: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.assert_only_the_named_skill_is_reported(under_another_name, capsys)


class TestInvalidYaml:
    UNCLOSED_LIST = 'name: demo-skill\ndescription: [unclosed\n'
    UNCLOSED_QUOTE = 'name: demo-skill\ndescription: "unclosed\n'
    PARSE_ERROR = (error('YAML frontmatter failed to parse'),)

    def test_invalid_yaml_the_builtin_passed_exits_two_without_a_verdict(
        self,
        skill_root: SkillRoot,
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        skill_dir = str(skill_root.write(self.UNCLOSED_LIST))

        assert main(['skill', 'validate', skill_dir], fake_services(())) == 2
        captured = capsys.readouterr()
        assert 'not valid YAML' in captured.err
        assert 'PASS' not in captured.out
        assert 'FAIL' not in captured.out

    def test_invalid_yaml_the_builtin_reported_exits_one(
        self,
        skill_root: SkillRoot,
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        skill_dir = str(skill_root.write(self.UNCLOSED_QUOTE))

        assert main(['skill', 'validate', skill_dir], fake_services(self.PARSE_ERROR)) == 1
        assert 'FAIL demo-skill' in capsys.readouterr().out
