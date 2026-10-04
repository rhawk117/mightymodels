import json
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
from vibe_code_cli.builtin import Services
from vibe_code_cli.cli import main
from vibe_code_cli.findings import Finding, error, warning
from vibe_code_cli.mcp import help_probe
from vibe_code_cli.mcp.tests.support import McpFiles, ServicesFactory, Staging


class TestUsage:
    def test_mc_a29_validate_help_shows_the_file_kind_and_options(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['mcp', 'validate', '--help'])

        assert exit_info.value.code == 0
        output = capsys.readouterr().out
        for text in ('FILE', '--kind', 'plugin,project,user', '--check-command', '--strict'):
            assert text in output

    def test_create_mcp_without_a_command_prints_usage_and_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['mcp']) == 2
        assert 'usage: vibe-code' in capsys.readouterr().err

    def test_validate_without_a_kind_is_a_usage_error(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['mcp', 'validate', 'x.json'])

        assert exit_info.value.code == 2


class TestBuiltinFindings:
    ERROR = (error('Invalid input: expected string'),)
    WARNING = (warning('url uses http://'),)
    INVALID_JSON = (error('Invalid JSON syntax'),)
    TRUNCATED_JSON = '{"mcpServers": '

    @pytest.mark.parametrize(
        'kind',
        [
            pytest.param('plugin', id='plugin'),
            pytest.param('project', id='project'),
            pytest.param('user', id='user'),
        ],
    )
    def test_clean_file_exits_zero_for_every_kind(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str], kind: str
    ) -> None:
        path = mcp_files.servers({'db': mcp_files.stdio_server, 'api': mcp_files.http_server}, kind)

        assert mcp_files.validate(kind, path) == 0
        assert f'PASS {path} as {kind}' in capsys.readouterr().out

    def test_builtin_error_exits_one_and_its_message_is_printed(
        self,
        mcp_files: McpFiles,
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        services = fake_services(self.ERROR)

        assert mcp_files.validate('plugin', mcp_files.write(), services=services) == 1
        assert 'error: Invalid input: expected string' in capsys.readouterr().out

    def test_warning_exits_zero_and_strict_turns_it_into_one(
        self, mcp_files: McpFiles, fake_services: ServicesFactory
    ) -> None:
        services = fake_services(self.WARNING)
        path = mcp_files.write()

        assert mcp_files.validate('plugin', path, services=services) == 0
        assert mcp_files.validate('plugin', path, '--strict', services=services) == 1

    def test_builtin_that_cannot_run_exits_two_without_a_verdict(
        self,
        mcp_files: McpFiles,
        unavailable_services: Services,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = mcp_files.write()

        assert mcp_files.validate('plugin', path, services=unavailable_services) == 2
        captured = capsys.readouterr()
        assert 'no JSON report' in captured.err
        assert 'PASS' not in captured.out

    def test_invalid_json_that_the_builtin_reports_exits_one_without_own_findings(
        self,
        mcp_files: McpFiles,
        fake_services: ServicesFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        services = fake_services(self.INVALID_JSON)
        path = mcp_files.write(text=self.TRUNCATED_JSON)

        assert mcp_files.validate('project', path, services=services) == 1
        assert 'must be a JSON object' not in capsys.readouterr().out

    def test_invalid_json_that_the_builtin_lets_pass_exits_two(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert mcp_files.validate('project', mcp_files.write(text=self.TRUNCATED_JSON)) == 2
        captured = capsys.readouterr()
        assert 'not JSON' in captured.err
        assert 'PASS' not in captured.out


class TestTargetThatCannotBeChecked:
    @pytest.fixture
    def no_claude_on_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('PATH', str(tmp_path))

    @pytest.fixture
    def unreadable_file(self, mcp_files: McpFiles) -> Path:
        path = mcp_files.write()
        path.chmod(0)
        if os.access(path, os.R_OK):
            pytest.skip('this user can read a mode 000 file')
        return path

    def test_file_that_is_not_a_file_exits_two(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert mcp_files.validate('plugin', mcp_files.root) == 2
        captured = capsys.readouterr()
        assert 'is not a file' in captured.err
        assert 'FAIL' not in captured.out

    def test_unreadable_file_exits_two_naming_the_path(
        self, mcp_files: McpFiles, unreadable_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert mcp_files.validate('plugin', unreadable_file) == 2
        captured = capsys.readouterr()
        assert str(unreadable_file) in captured.err
        assert 'FAIL' not in captured.out

    @pytest.mark.usefixtures('no_claude_on_path')
    def test_without_claude_on_path_exits_two_naming_claude(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.write()

        assert mcp_files.validate('plugin', path, services=Services()) == 2
        captured = capsys.readouterr()
        assert 'claude is not on PATH' in captured.err
        assert 'PASS' not in captured.out


class TestStaging:
    USER_DOCUMENT: Mapping[str, int] = {'numStartups': 3}
    BARE_MAP = '{"db": {"command": "uv"}}'

    @pytest.fixture
    def staging(self) -> Staging:
        staged: dict[str, object] = {}

        def capture(target: Path, /, *, include_manifest: bool = True) -> list[Finding]:
            staged['mcp'] = (target / '.mcp.json').read_text()
            staged['manifest'] = (target / '.claude-plugin' / 'plugin.json').is_file()
            staged['include_manifest'] = include_manifest
            return []

        return Staging(services=Services(run_builtin=capture), staged=staged)

    @pytest.mark.parametrize(
        'kind',
        [pytest.param('plugin', id='plugin'), pytest.param('project', id='project')],
    )
    def test_plugin_and_project_files_are_staged_as_they_are(
        self, mcp_files: McpFiles, staging: Staging, kind: str
    ) -> None:
        path = mcp_files.write(text=self.BARE_MAP)

        mcp_files.validate(kind, path, services=staging.services)

        assert staging.staged == {
            'mcp': path.read_text(),
            'manifest': True,
            'include_manifest': False,
        }

    def test_user_file_is_staged_as_its_servers_alone(
        self, mcp_files: McpFiles, staging: Staging
    ) -> None:
        path = mcp_files.servers({'db': mcp_files.stdio_server}, 'user')

        mcp_files.validate('user', path, services=staging.services)

        assert json.loads(str(staging.staged['mcp'])) == {
            'mcpServers': {'db': mcp_files.stdio_server}
        }
        assert staging.staged['include_manifest'] is False

    def test_user_file_without_servers_is_staged_with_an_empty_server_map(
        self, mcp_files: McpFiles, staging: Staging
    ) -> None:
        path = mcp_files.write(self.USER_DOCUMENT, '.claude.json')

        mcp_files.validate('user', path, services=staging.services)

        assert json.loads(str(staging.staged['mcp'])) == {'mcpServers': {}}


class TestFileShape:
    def test_m2_top_level_array_exits_one(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert mcp_files.validate('plugin', mcp_files.write([])) == 1
        assert 'error: Expected `object`, got `array`' in capsys.readouterr().out

    def test_m4_extra_top_level_key_beside_the_servers_exits_one(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.write({'mcpServers': {'db': mcp_files.stdio_server}, 'extra': 1})

        assert mcp_files.validate('plugin', path) == 1
        assert "unexpected top-level key 'extra'" in capsys.readouterr().out

    def test_m4_does_not_fire_for_a_user_file_with_other_keys(self, mcp_files: McpFiles) -> None:
        path = mcp_files.servers({'db': mcp_files.stdio_server}, 'user')

        assert mcp_files.validate('user', path) == 0

    def test_m6_servers_that_are_not_an_object_exits_one(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert mcp_files.validate('plugin', mcp_files.write({'mcpServers': []})) == 1
        assert (
            'error: Expected `object`, got `array` - at `$.mcpServers`' in capsys.readouterr().out
        )

    @pytest.mark.parametrize(
        ('kind', 'document'),
        [
            pytest.param('plugin', {'mcpServers': {}}, id='plugin-document0'),
            pytest.param('plugin', {}, id='plugin-document1'),
            pytest.param('project', {'mcpServers': {}}, id='project-document2'),
            pytest.param('user', {'numStartups': 3}, id='user-document3'),
        ],
    )
    def test_m7_file_with_no_servers_exits_one(
        self,
        mcp_files: McpFiles,
        capsys: pytest.CaptureFixture[str],
        kind: str,
        document: object,
    ) -> None:
        assert mcp_files.validate(kind, mcp_files.write(document)) == 1
        assert 'no servers found' in capsys.readouterr().out


class TestFileNaming:
    @pytest.fixture
    def wrapped(self, mcp_files: McpFiles) -> Path:
        return mcp_files.write()

    @pytest.fixture
    def bare(self, mcp_files: McpFiles) -> Path:
        directory = mcp_files.root / 'bare'
        directory.mkdir()
        return mcp_files.write({'db': mcp_files.stdio_server}, directory=directory)

    def test_m25_plugin_file_not_named_dot_mcp_json_is_a_warning(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.write(name='mcp.json')

        assert mcp_files.validate('plugin', path) == 0
        assert mcp_files.validate('plugin', path, '--strict') == 1
        assert 'mcp.json is never read as a plugin MCP config' in capsys.readouterr().out

    def test_m26_project_file_not_named_dot_mcp_json_is_a_warning(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.write(name='mcp-config.json')

        assert mcp_files.validate('project', path) == 0
        assert mcp_files.validate('project', path, '--strict') == 1
        assert 'never read as a project MCP config' in capsys.readouterr().out

    def test_mc_a4_plugin_file_needs_no_schema_key(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert mcp_files.validate('plugin', mcp_files.write(), '--strict') == 0
        assert 'PASS' in capsys.readouterr().out

    def test_mc_a5_plugin_accepts_the_wrapper_and_a_bare_map(
        self, mcp_files: McpFiles, wrapped: Path, bare: Path
    ) -> None:
        assert mcp_files.validate('plugin', wrapped, '--strict') == 0
        assert mcp_files.validate('plugin', bare, '--strict') == 0

    def test_mc_a5_project_file_without_the_wrapper_is_a_warning(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.write({'db': mcp_files.stdio_server})

        assert mcp_files.validate('project', path) == 0
        assert mcp_files.validate('project', path, '--strict') == 1
        assert 'with the mcpServers wrapper' in capsys.readouterr().out


class TestServerKeys:
    SSE_SERVER: Mapping[str, str] = {'type': 'sse', 'url': 'https://example.com/sse'}

    @pytest.mark.parametrize(
        'transport',
        [
            pytest.param('stdio', id='stdio'),
            pytest.param('http', id='http'),
            pytest.param('sse', id='sse'),
            pytest.param('ws', id='ws'),
            pytest.param('streamable-http', id='streamable-http'),
        ],
    )
    def test_mc_a6_every_documented_transport_is_accepted(
        self,
        mcp_files: McpFiles,
        capsys: pytest.CaptureFixture[str],
        transport: str,
    ) -> None:
        server = {'type': transport, 'command': 'uv'}
        if transport != 'stdio':
            server = {'type': transport, 'url': 'https://example.com/mcp'}

        assert mcp_files.validate('plugin', mcp_files.servers({'db': server})) == 0
        assert 'unknown server key' not in capsys.readouterr().out

    def test_m10a_unknown_key_is_an_error_in_a_plugin_and_a_warning_elsewhere(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.write({'mcpServers': {'db': {**mcp_files.stdio_server, 'bogus': 1}}})

        assert mcp_files.validate('plugin', path) == 1
        assert mcp_files.validate('project', path) == 0
        assert mcp_files.validate('user', path, '--strict') == 1
        assert "unknown server key 'bogus'" in capsys.readouterr().out

    def test_m10a_remote_server_keys_are_checked_against_the_remote_set(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        remote = {
            **mcp_files.http_server,
            'command': 'uv',
            'oauth': {},
            'headersHelper': 'x',
            'alwaysLoad': True,
        }

        assert mcp_files.validate('plugin', mcp_files.servers({'api': remote})) == 1
        output = capsys.readouterr().out
        assert output.count('unknown server key') == 1
        assert "unknown server key 'command'" in output

    def test_mc_a10_cwd_is_reported_as_an_unknown_key(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.write({'mcpServers': {'db': {**mcp_files.stdio_server, 'cwd': '.'}}})

        assert mcp_files.validate('plugin', path) == 1
        assert "unknown server key 'cwd'" in capsys.readouterr().out

    def test_m10b_and_mc_a7_tools_key_is_reported_with_the_permission_rules(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.write({'mcpServers': {'db': {**mcp_files.stdio_server, 'tools': ['*']}}})

        assert mcp_files.validate('plugin', path) == 1
        output = capsys.readouterr().out
        assert '"tools" is not a Claude Code server key' in output
        assert 'permissions.allow' in output
        assert "unknown server key 'tools'" not in output

    def test_m23_sse_transport_is_a_warning(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.servers({'api': self.SSE_SERVER})

        assert mcp_files.validate('plugin', path) == 0
        assert mcp_files.validate('plugin', path, '--strict') == 1
        assert 'sse transport is deprecated' in capsys.readouterr().out


class TestVariableReferences:
    UNSET_NAMES = ('TOOL_BIN', 'OPT', 'API_BASE_URL', 'PROJECT_TOKEN', 'UNSET_BIN')

    @pytest.fixture
    def unset_variables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in self.UNSET_NAMES:
            monkeypatch.delenv(name, raising=False)

    @pytest.fixture
    def set_bin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('SET_BIN', 'uv')

    @pytest.mark.usefixtures('unset_variables')
    @pytest.mark.parametrize(
        'server',
        [
            pytest.param({'command': '${TOOL_BIN:-uv}'}, id='server0'),
            pytest.param(
                {'command': 'uv', 'args': ['--root', '${CLAUDE_PLUGIN_ROOT}/x', '${OPT:-1}']},
                id='server1',
            ),
            pytest.param(
                {
                    'command': 'uv',
                    'env': {'K': '${CLAUDE_PLUGIN_DATA}', 'U': '${user_config.token}'},
                },
                id='server2',
            ),
            pytest.param(
                {'type': 'http', 'url': '${API_BASE_URL:-https://example.com}/mcp'}, id='server3'
            ),
            pytest.param(
                {
                    'type': 'http',
                    'url': 'https://example.com',
                    'headers': {'A': '${PROJECT_TOKEN:-none}'},
                },
                id='server4',
            ),
        ],
    )
    def test_mc_a9_references_with_a_default_or_a_provided_name_pass(
        self, mcp_files: McpFiles, server: dict[str, object]
    ) -> None:
        assert mcp_files.validate('plugin', mcp_files.servers({'db': server}), '--strict') == 0

    @pytest.mark.usefixtures('unset_variables')
    @pytest.mark.parametrize(
        ('server', 'location'),
        [
            pytest.param({'command': '${UNSET_BIN}'}, 'db.command', id='server0-db.command'),
            pytest.param(
                {'command': 'uv', 'args': ['a', '${UNSET_BIN}']},
                'db.args[1]',
                id='server1-db.args[1]',
            ),
            pytest.param(
                {'command': 'uv', 'env': {'KEY': '${UNSET_BIN}'}},
                'db.env.KEY',
                id='server2-db.env.KEY',
            ),
            pytest.param(
                {'type': 'http', 'url': '${UNSET_BIN}/mcp'}, 'db.url', id='server3-db.url'
            ),
            pytest.param(
                {'type': 'http', 'url': 'https://x', 'headers': {'H': '${UNSET_BIN}'}},
                'db.headers.H',
                id='server4-db.headers.H',
            ),
        ],
    )
    def test_mc_a9_unset_variable_without_a_default_is_a_warning_in_every_location(
        self,
        mcp_files: McpFiles,
        capsys: pytest.CaptureFixture[str],
        server: dict[str, object],
        location: str,
    ) -> None:
        path = mcp_files.servers({'db': server})

        assert mcp_files.validate('plugin', path) == 0
        assert mcp_files.validate('plugin', path, '--strict') == 1
        assert f'{location}: ${{UNSET_BIN}} is not set here' in capsys.readouterr().out

    @pytest.mark.usefixtures('set_bin')
    def test_mc_a9_variable_that_is_set_passes(self, mcp_files: McpFiles) -> None:
        path = mcp_files.servers({'db': {'command': '${SET_BIN}'}})

        assert mcp_files.validate('plugin', path, '--strict') == 0

    def test_mc_a9_bare_dollar_variable_is_a_warning(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.servers({'db': {'command': 'uv', 'env': {'KEY': '$HOME/x'}}})

        assert mcp_files.validate('plugin', path) == 0
        assert mcp_files.validate('plugin', path, '--strict') == 1
        assert (
            'db.env.KEY: a bare $NAME reference is not expanded; write it as ${NAME}'
            in capsys.readouterr().out
        )


class TestCredentialVariables:
    @pytest.fixture
    def credential_in_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('ANTHROPIC_AUTH_TOKEN', 'real-secret')

    @pytest.fixture
    def npm_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('NPM_TOKEN', 'x')

    @pytest.mark.usefixtures('credential_in_environment')
    @pytest.mark.parametrize(
        'remote',
        [
            pytest.param(
                {'type': 'http', 'url': 'https://example.com/${ANTHROPIC_AUTH_TOKEN:-x}'},
                id='url',
            ),
            pytest.param(
                {
                    'type': 'http',
                    'url': 'https://example.com',
                    'headers': {'Authorization': 'Bearer ${ANTHROPIC_AUTH_TOKEN}'},
                },
                id='headers',
            ),
        ],
    )
    def test_mc_b4_credential_variable_in_a_remote_url_or_headers_is_a_warning(
        self,
        mcp_files: McpFiles,
        capsys: pytest.CaptureFixture[str],
        remote: dict[str, object],
    ) -> None:
        assert mcp_files.validate('plugin', mcp_files.servers({'api': remote}), '--strict') == 1
        output = capsys.readouterr().out
        assert 'reads as empty in a remote server url or headers' in output
        assert 'real-secret' not in output

    @pytest.mark.usefixtures('npm_token')
    def test_mc_b4_credential_variable_in_a_stdio_env_is_not_flagged(
        self, mcp_files: McpFiles
    ) -> None:
        server = {'command': 'uv', 'env': {'NPM_TOKEN': '${NPM_TOKEN}'}}

        assert mcp_files.validate('plugin', mcp_files.servers({'db': server}), '--strict') == 0


class TestSecretsNotPrinted:
    ENV_AND_HEADERS_SECRETS: Mapping[str, object] = {
        'db': {'command': 'uv', 'env': {'K': 'hunter2-env ${NOPE} $BARE', 'bogus': 'x'}},
        'api': {'type': 'http', 'url': 'https://x', 'headers': {'A': 'hunter2-header ${NOPE}'}},
    }
    BARE_PIECES: Mapping[str, object] = {
        'db': {'command': 'uv', 'env': {'PASSWORD': 'hunter$ecretpart'}},
        'api': {'type': 'http', 'url': 'https://x', 'headers': {'A': 'Bearer tok$ecretpart'}},
    }

    @pytest.fixture
    def unset_nope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv('NOPE', raising=False)

    @pytest.mark.usefixtures('unset_nope')
    def test_findings_never_print_an_env_or_headers_value(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.servers(self.ENV_AND_HEADERS_SECRETS)

        assert mcp_files.validate('plugin', path, '--strict') == 1
        output = capsys.readouterr().out
        assert 'NOPE' in output
        assert 'hunter2' not in output

    def test_bare_variable_warning_never_prints_a_piece_of_an_env_or_headers_value(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.servers(self.BARE_PIECES)

        assert mcp_files.validate('plugin', path, '--strict') == 1
        output = capsys.readouterr().out
        assert 'db.env.PASSWORD: a bare $NAME reference' in output
        assert 'api.headers.A: a bare $NAME reference' in output
        assert 'ecretpart' not in output


class TestCheckCommand:
    HANG = ('-c', 'import time; time.sleep(30)')
    NO_SUCH_COMMAND = 'no-such-command-xyz'

    @pytest.fixture
    def short_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(help_probe, 'COMMAND_TIMEOUT_SECONDS', 0.5)

    def test_m27_command_not_on_path_exits_one(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.command_config(self.NO_SUCH_COMMAND, [])

        assert mcp_files.validate('plugin', path, '--check-command') == 1
        assert f"command '{self.NO_SUCH_COMMAND}' not found on PATH" in capsys.readouterr().out

    def test_m28_help_that_exits_nonzero_exits_one(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.command_config(sys.executable, ['-c', 'import sys; sys.exit(7)'])

        assert mcp_files.validate('plugin', path, '--check-command') == 1
        assert '--help exited 7' in capsys.readouterr().out

    @pytest.mark.usefixtures('short_timeout')
    def test_m28_help_that_outlives_the_timeout_exits_one(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = mcp_files.command_config(sys.executable, self.HANG)

        assert mcp_files.validate('plugin', path, '--check-command') == 1
        assert '--help timed out after 0.5 s' in capsys.readouterr().out


class TestCheckCommandRuns:
    NO_SUCH_COMMAND = 'no-such-command-xyz'

    @pytest.fixture
    def server_script(self, mcp_files: McpFiles) -> Path:
        script = mcp_files.root / 'server.py'
        script.write_text('pass\n')
        return script

    @pytest.fixture
    def in_the_file_directory(self, mcp_files: McpFiles, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(mcp_files.root)

    def test_check_command_passes_when_help_exits_zero(self, mcp_files: McpFiles) -> None:
        path = mcp_files.command_config(sys.executable, ['-c', 'pass'])

        assert mcp_files.validate('plugin', path, '--check-command') == 0

    def test_check_command_runs_nothing_without_the_flag(self, mcp_files: McpFiles) -> None:
        marker = mcp_files.root / 'ran'
        touch = f'import pathlib; pathlib.Path({str(marker)!r}).touch()'
        path = mcp_files.command_config(sys.executable, ['-c', touch])

        assert mcp_files.validate('plugin', path) == 0
        assert not marker.exists()
        assert mcp_files.validate('plugin', path, '--check-command') == 0
        assert marker.exists()

    @pytest.mark.usefixtures('server_script')
    def test_check_command_substitutes_the_plugin_root_with_the_file_directory(
        self, mcp_files: McpFiles
    ) -> None:
        path = mcp_files.command_config(sys.executable, ['${CLAUDE_PLUGIN_ROOT}/server.py'])

        assert mcp_files.validate('plugin', path, '--check-command') == 0

    def test_check_command_does_not_run_a_remote_or_malformed_server(
        self, mcp_files: McpFiles
    ) -> None:
        servers = {
            'api': mcp_files.http_server,
            'bad': {'args': [self.NO_SUCH_COMMAND]},
        }

        assert mcp_files.validate('plugin', mcp_files.servers(servers), '--check-command') == 0

    def test_check_command_does_not_run_a_server_whose_value_has_the_wrong_type(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        servers = {'bad': {'command': self.NO_SUCH_COMMAND, 'args': 'x'}}

        assert mcp_files.validate('plugin', mcp_files.servers(servers), '--check-command') == 1
        output = capsys.readouterr().out
        assert 'Expected `array`, got `str` - at `$.mcpServers[...].args`' in output
        assert 'not found on PATH' not in output

    @pytest.mark.usefixtures('server_script', 'in_the_file_directory')
    def test_check_command_for_a_project_file_runs_in_the_current_directory(
        self, mcp_files: McpFiles
    ) -> None:
        path = mcp_files.command_config(sys.executable, ['server.py'])

        assert mcp_files.validate('project', path, '--check-command') == 0


class TestRealBuiltin:
    NO_COMMAND: Mapping[str, object] = {'mcpServers': {'db': {'type': 'stdio'}}}

    @pytest.mark.skipif(shutil.which('claude') is None, reason='needs the claude CLI')
    @pytest.mark.parametrize(
        'kind',
        [pytest.param('plugin', id='plugin'), pytest.param('project', id='project')],
    )
    def test_real_builtin_reports_a_server_with_no_command(
        self, mcp_files: McpFiles, capsys: pytest.CaptureFixture[str], kind: str
    ) -> None:
        path = mcp_files.write(self.NO_COMMAND)

        assert mcp_files.validate(kind, path, services=Services()) == 1
        output = capsys.readouterr().out
        assert 'mcpServers.db.command: Invalid input: expected string, received undefined' in output
        assert 'version' not in output
