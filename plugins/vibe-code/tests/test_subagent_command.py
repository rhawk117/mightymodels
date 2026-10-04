import os
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from vibe_code_cli.builtin import Services
from vibe_code_cli.cli import main
from vibe_code_cli.findings import Finding, error, warning
from vibe_code_cli.subagent.tests.support import AgentRoot, agent_text

type ServicesFactory = Callable[[Sequence[Finding]], Services]
type StagingRecorder = tuple[Services, list[dict[str, object]]]


class TestUsage:
    def test_validate_help_shows_the_file_and_strict(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['subagent', 'validate', '--help'])

        assert exit_info.value.code == 0
        output = capsys.readouterr().out
        assert 'FILE' in output
        assert '--strict' in output

    def test_create_subagent_without_a_command_prints_usage_and_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['subagent']) == 2
        assert 'usage: vibe-code' in capsys.readouterr().err


class TestCleanAgent:
    @pytest.mark.parametrize(
        'plugin', [pytest.param(False, id='False'), pytest.param(True, id='True')]
    )
    def test_clean_agent_exits_zero(self, subagent_root: AgentRoot, *, plugin: bool) -> None:
        code, output = subagent_root.check(agent_text(), plugin=plugin)

        assert code == 0
        assert 'PASS demo-agent.md: 0 error(s), 0 warning(s)' in output


class TestTargetThatCannotBeChecked:
    @pytest.fixture
    def text_file(self, tmp_path: Path) -> Path:
        text_file = tmp_path / 'agent.txt'
        text_file.write_text(agent_text())
        return text_file

    @pytest.fixture
    def unreadable_agent(self, subagent_root: AgentRoot) -> Path:
        path = subagent_root.write(agent_text())
        path.chmod(0)
        if os.access(path, os.R_OK):
            pytest.skip('this user can read a mode 000 file')
        return path

    @pytest.fixture
    def non_utf8_agent(self, subagent_root: AgentRoot) -> Path:
        path = subagent_root.write('')
        path.write_bytes(b'---\nname: \xff\n---\n')
        return path

    def test_path_that_is_not_a_markdown_file_exits_two(
        self, tmp_path: Path, text_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for path in (text_file, tmp_path, tmp_path / 'missing.md'):
            assert main(['subagent', 'validate', str(path)]) == 2
            captured = capsys.readouterr()
            assert 'is not a .md file' in captured.err
            assert 'PASS' not in captured.out

    def test_unreadable_agent_file_exits_two_naming_the_path(
        self, unreadable_agent: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['subagent', 'validate', str(unreadable_agent)]) == 2
        captured = capsys.readouterr()
        assert str(unreadable_agent) in captured.err
        assert 'PASS' not in captured.out
        assert 'FAIL' not in captured.out

    def test_file_that_is_not_utf8_exits_two(
        self, non_utf8_agent: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['subagent', 'validate', str(non_utf8_agent)]) == 2
        assert 'could not read' in capsys.readouterr().err


class TestBuiltinFindings:
    NO_TOOLS = agent_text({'tools': None})
    UNCLOSED_LIST = agent_text({'description': '[unclosed'})
    UNCLOSED_QUOTE = agent_text({'description': '"unclosed', 'tools': None})
    PARSE_ERROR = (error('YAML frontmatter failed to parse'),)
    NO_DESCRIPTION = (warning('No description in frontmatter.'),)

    def test_warning_exits_zero_and_strict_turns_it_into_one(
        self, subagent_root: AgentRoot
    ) -> None:
        path = subagent_root.write(self.NO_TOOLS)

        assert subagent_root.run(path)[0] == 0
        assert subagent_root.run(path, '--strict')[0] == 1

    def test_invalid_yaml_the_builtin_passed_exits_two_without_a_verdict(
        self,
        subagent_root: AgentRoot,
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = subagent_root.write(self.UNCLOSED_LIST)

        assert main(['subagent', 'validate', str(path)], fake_services(())) == 2
        captured = capsys.readouterr()
        assert 'not valid YAML' in captured.err
        assert 'PASS' not in captured.out
        assert 'FAIL' not in captured.out

    def test_builtin_error_exits_one_and_skips_the_field_checks(
        self, subagent_root: AgentRoot, fake_services: ServicesFactory
    ) -> None:
        services = fake_services(self.PARSE_ERROR)

        code, output = subagent_root.check(self.UNCLOSED_QUOTE, services=services)

        assert code == 1
        assert 'error: YAML frontmatter failed to parse' in output
        assert 'inherits every tool' not in output

    def test_builtin_that_cannot_run_exits_two_without_a_verdict(
        self,
        subagent_root: AgentRoot,
        unavailable_services: Services,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = subagent_root.write(agent_text())

        assert main(['subagent', 'validate', str(path)], unavailable_services) == 2
        assert 'PASS' not in capsys.readouterr().out

    def test_builtin_findings_come_before_the_own_findings(
        self, subagent_root: AgentRoot, fake_services: ServicesFactory
    ) -> None:
        services = fake_services(self.NO_DESCRIPTION)

        code, output = subagent_root.check(self.NO_TOOLS, services=services)

        assert code == 0
        assert output.index('No description in frontmatter') < output.index('inherits every tool')


class TestStaging:
    @pytest.fixture
    def record_staging(self) -> StagingRecorder:
        seen: list[dict[str, object]] = []

        def fake(target: Path, **options: bool) -> list[Finding]:
            seen.append(
                {
                    'target': target.name,
                    'parent': target.parent.name,
                    'files': sorted(
                        str(item.relative_to(target))
                        for item in target.rglob('*')
                        if item.is_file()
                    ),
                    'options': options,
                }
            )
            return []

        return Services(run_builtin=fake), seen

    @pytest.fixture
    def agent_beside_a_sibling(self, subagent_root: AgentRoot) -> Path:
        path = subagent_root.write(agent_text())
        (path.parent / 'sibling.md').write_text('no frontmatter\n')
        return path

    def test_plugin_agent_is_staged_in_a_plugin_with_the_manifest_findings_dropped(
        self, subagent_root: AgentRoot, record_staging: StagingRecorder
    ) -> None:
        services, seen = record_staging
        path = subagent_root.write(agent_text(), plugin=True)

        assert main(['subagent', 'validate', str(path)], services) == 0
        assert seen == [
            {
                'target': seen[0]['target'],
                'parent': seen[0]['parent'],
                'files': ['.claude-plugin/plugin.json', 'agents/demo-agent.md'],
                'options': {'include_manifest': False},
            }
        ]

    @pytest.mark.parametrize(
        'relative',
        [
            pytest.param('.claude/agents', id='.claude/agents'),
            pytest.param('notes', id='notes'),
            pytest.param('docs/agents/.claude', id='docs/agents/.claude'),
        ],
    )
    def test_any_other_parent_is_staged_as_a_claude_agents_directory(
        self, tmp_path: Path, record_staging: StagingRecorder, relative: str
    ) -> None:
        services, seen = record_staging
        directory = tmp_path / relative
        directory.mkdir(parents=True)
        path = directory / 'demo-agent.md'
        path.write_text(agent_text())

        assert main(['subagent', 'validate', str(path)], services) == 0
        assert seen[0]['target'] == 'agents'
        assert seen[0]['parent'] == '.claude'
        assert seen[0]['files'] == ['demo-agent.md']

    def test_builtin_runs_on_a_copy_of_the_one_file_not_its_siblings(
        self, agent_beside_a_sibling: Path, record_staging: StagingRecorder
    ) -> None:
        services, seen = record_staging

        assert main(['subagent', 'validate', str(agent_beside_a_sibling)], services) == 0
        assert seen[0]['files'] == ['demo-agent.md']


class TestYamlTypedFrontmatter:
    UNQUOTED_DATE = agent_text({'name': '2024-01-01'})
    BOOL_ALIAS = agent_text({'name': 'on'})
    NON_STRING_KEY = agent_text({'1': 'one'})

    @pytest.mark.parametrize(
        'text',
        [
            pytest.param(UNQUOTED_DATE, id='unquoted_date'),
            pytest.param(BOOL_ALIAS, id='bool_alias'),
            pytest.param(NON_STRING_KEY, id='non_string_key'),
        ],
    )
    def test_a_yaml_typed_frontmatter_value_or_key_is_one_finding(
        self, subagent_root: AgentRoot, capsys: pytest.CaptureFixture[str], text: str
    ) -> None:
        code, output = subagent_root.check(text)

        assert code == 1
        assert 'Traceback' not in capsys.readouterr().err
        assert 'FAIL demo-agent.md: 1 error(s), 0 warning(s)' in output
