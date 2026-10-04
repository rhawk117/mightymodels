import json
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from vibe_code_cli.builtin import Services
from vibe_code_cli.cli import main
from vibe_code_cli.findings import Finding
from vibe_code_cli.hook.tests.support import (
    EXAMPLE,
    PAYLOADS,
    TEMPLATE,
    PayloadFiles,
    TemplateRun,
)

type ServicesFactory = Callable[[Sequence[Finding]], Services]


class TestExample:
    SCRIPT_PATH = re.compile(r'\$\{CLAUDE_PROJECT_DIR\}/(\S+?\.py)')

    @pytest.fixture
    def settings(self, tmp_path: Path) -> Path:
        settings = tmp_path / '.claude' / 'settings.json'
        settings.parent.mkdir()
        shutil.copy(EXAMPLE, settings)
        return settings

    @pytest.fixture
    def scripts_it_names(self, settings: Path) -> None:
        root = settings.parents[1]
        for relative in set(self.SCRIPT_PATH.findall(EXAMPLE.read_text())):
            script = root / relative
            script.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(TEMPLATE, script)

    @pytest.mark.usefixtures('scripts_it_names')
    def test_example_validates_strict_with_the_template_at_every_path_it_names(
        self, settings: Path, fake_services: ServicesFactory
    ) -> None:
        assert main(['hook', 'validate', str(settings), '--strict'], fake_services(())) == 0

    def test_example_fails_validation_when_a_script_it_names_is_missing(
        self, settings: Path, fake_services: ServicesFactory, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['hook', 'validate', str(settings), '--strict'], fake_services(())) == 1
        assert 'script not found' in capsys.readouterr().out


class TestPayloadFixtures:
    NINE_PAYLOADS = frozenset(
        {
            'PostToolUse-Bash',
            'PostToolUseFailure-Bash',
            'PreToolUse-Bash',
            'PreToolUse-Bash-dangerous',
            'PreToolUse-Edit',
            'SessionStart',
            'Stop',
            'Stop-active',
            'SubagentStop',
        }
    )
    SUBAGENT_STOP_FIELDS = frozenset(
        {
            'stop_hook_active',
            'agent_id',
            'agent_type',
            'agent_transcript_path',
            'last_assistant_message',
        }
    )

    @pytest.fixture
    def payload_files(self) -> list[Path]:
        return sorted(PAYLOADS.glob('*.json'))

    def test_fixtures_cover_the_nine_payloads_and_each_names_its_event(
        self, payload_files: list[Path]
    ) -> None:
        assert {path.stem for path in payload_files} == self.NINE_PAYLOADS
        for path in payload_files:
            assert json.loads(path.read_text())['hook_event_name'] == path.stem.split('-')[0]

    def test_fixtures_carry_the_corrected_documented_fields(self) -> None:
        edit = json.loads((PAYLOADS / 'PreToolUse-Edit.json').read_text())
        failure = json.loads((PAYLOADS / 'PostToolUseFailure-Bash.json').read_text())
        subagent = json.loads((PAYLOADS / 'SubagentStop.json').read_text())

        assert Path(edit['tool_input']['file_path']).is_absolute()
        assert re.match(r'Exit code \d+', failure['error'])
        assert 'last_message' not in subagent
        assert subagent.keys() >= self.SUBAGENT_STOP_FIELDS

    @pytest.mark.parametrize(
        'fixture',
        [pytest.param(path, id=path.stem) for path in sorted(PAYLOADS.glob('*.json'))],
    )
    def test_template_passes_the_contract_on_every_fixture(
        self, hook_template_run: TemplateRun, fixture: Path
    ) -> None:
        assert hook_template_run(fixture) == []


class TestTemplateDecisions:
    DENY = (
        'hookSpecificOutput.hookEventName=PreToolUse',
        'hookSpecificOutput.permissionDecision=deny',
    )
    ASK = ('hookSpecificOutput.permissionDecision=ask',)
    FAILURE_CONTEXT = (
        'hookSpecificOutput.hookEventName=PostToolUseFailure',
        'hookSpecificOutput.additionalContext',
    )

    def test_dangerous_command_is_denied_by_the_example_handler(
        self, hook_template_run: TemplateRun
    ) -> None:
        findings = hook_template_run(PAYLOADS / 'PreToolUse-Bash-dangerous.json', fields=self.DENY)

        assert findings == []

    def test_ordinary_command_gets_no_decision(self, hook_template_run: TemplateRun) -> None:
        assert hook_template_run(PAYLOADS / 'PreToolUse-Bash.json', silent=True) == []

    def test_release_workflow_edit_asks_the_person(self, hook_template_run: TemplateRun) -> None:
        findings = hook_template_run(PAYLOADS / 'PreToolUse-Edit.json', fields=self.ASK)

        assert findings == []

    def test_failure_playbook_adds_the_fix_as_context(self, hook_template_run: TemplateRun) -> None:
        findings = hook_template_run(
            PAYLOADS / 'PostToolUseFailure-Bash.json', fields=self.FAILURE_CONTEXT
        )

        assert findings == []

    def test_malformed_input_blocks_with_exit_two_under_the_enforce_posture(
        self, hook_template_run: TemplateRun
    ) -> None:
        findings = hook_template_run(PAYLOADS / 'PreToolUse-Bash.json', exit_code=2, malformed=True)

        assert findings == []


class TestTemplateInAProject:
    REWRITE = (
        'hookSpecificOutput.permissionDecision=allow',
        'hookSpecificOutput.updatedInput.command=uv run pytest tests/ -x',
    )
    SESSION_CONTEXT = (
        'hookSpecificOutput.hookEventName=SessionStart',
        'hookSpecificOutput.additionalContext',
    )
    BLOCK = ('decision=block', 'reason')

    @pytest.fixture
    def git_repository(self, tmp_path: Path) -> Path:
        subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)  # noqa: S603, S607  # fixed git command on a tmp dir
        return tmp_path

    @pytest.fixture
    def lock_file(self, tmp_path: Path) -> Path:
        path = tmp_path / 'uv.lock'
        path.touch()
        return path

    @pytest.fixture
    def pyproject(self, tmp_path: Path) -> Path:
        path = tmp_path / 'pyproject.toml'
        path.touch()
        return path

    @pytest.mark.usefixtures('lock_file')
    def test_bare_runner_command_is_rewritten_when_the_project_has_a_lock_file(
        self, tmp_path: Path, hook_template_run: TemplateRun, hook_payload_with: PayloadFiles
    ) -> None:
        payload = hook_payload_with('PreToolUse-Bash.json', cwd=str(tmp_path))

        assert hook_template_run(payload, fields=self.REWRITE) == []

    def test_session_start_reports_the_repository_state(
        self,
        git_repository: Path,
        hook_template_run: TemplateRun,
        hook_payload_with: PayloadFiles,
    ) -> None:
        payload = hook_payload_with('SessionStart.json', cwd=str(git_repository))

        assert hook_template_run(payload, fields=self.SESSION_CONTEXT) == []

    @pytest.mark.usefixtures('pyproject')
    def test_stop_gate_stands_down_when_a_stop_hook_is_already_active(
        self, tmp_path: Path, hook_template_run: TemplateRun, hook_payload_with: PayloadFiles
    ) -> None:
        payload = hook_payload_with('Stop-active.json', cwd=str(tmp_path))

        assert hook_template_run(payload, silent=True) == []

    def test_subagent_report_gate_blocks_once_then_allows(
        self, tmp_path: Path, hook_template_run: TemplateRun, hook_payload_with: PayloadFiles
    ) -> None:
        unstructured = hook_payload_with('SubagentStop.json', last_assistant_message='all done')
        already_continuing = tmp_path / 'again.json'
        already_continuing.write_text(
            json.dumps({**json.loads(unstructured.read_text()), 'stop_hook_active': True})
        )

        assert hook_template_run(unstructured, fields=self.BLOCK) == []
        assert hook_template_run(already_continuing, silent=True) == []
