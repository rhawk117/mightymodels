import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from ai_engineer_cli import create_hooks
from ai_engineer_cli.cli import main
from ai_engineer_cli.findings import Finding
from ai_engineer_cli.hook_runner import Expectations, HookTest, check_hook, parse_field_expectation

SKILL = Path(__file__).resolve().parents[1] / 'skills' / 'create-hooks'
TEMPLATE = SKILL / 'assets' / 'hook.template.py'
EXAMPLE = SKILL / 'assets' / 'hooks.example.json'
PAYLOADS = SKILL / 'scripts' / 'payloads'
FIXTURES = sorted(PAYLOADS.glob('*.json'))
SCRIPT_PATH = re.compile(r'\$\{CLAUDE_PROJECT_DIR\}/(\S+?\.py)')
TEST_TIMEOUT_SECONDS = 15.0


def stub_builtin(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_findings(_target: Path, **_options: bool) -> list[Finding]:
        return []

    monkeypatch.setattr(create_hooks, 'run_builtin', no_findings)


def run_template(
    payload: Path,
    *,
    exit_code: int = 0,
    fields: tuple[str, ...] = (),
    silent: bool = False,
    malformed: bool = False,
) -> list[Finding]:
    expectations = Expectations(
        exit_code=exit_code,
        fields=tuple(parse_field_expectation(spec) for spec in fields),
        silent=silent,
    )
    hook_test = HookTest(TEMPLATE, payload, expectations, TEST_TIMEOUT_SECONDS, malformed)
    return check_hook(hook_test)


def payload_with(tmp_path: Path, fixture: str, **changes: object) -> Path:
    payload = json.loads((PAYLOADS / fixture).read_text())
    payload.update(changes)
    path = tmp_path / fixture
    path.write_text(json.dumps(payload))
    return path


def install_example(root: Path, *, with_scripts: bool) -> Path:
    settings = root / '.claude' / 'settings.json'
    settings.parent.mkdir()
    shutil.copy(EXAMPLE, settings)
    if with_scripts:
        for relative in set(SCRIPT_PATH.findall(EXAMPLE.read_text())):
            script = root / relative
            script.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(TEMPLATE, script)
    return settings


def test_example_validates_strict_with_the_template_at_every_path_it_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_builtin(monkeypatch)
    settings = install_example(tmp_path, with_scripts=True)

    assert main(['create-hooks', 'validate', str(settings), '--strict']) == 0


def test_example_fails_validation_when_a_script_it_names_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub_builtin(monkeypatch)
    settings = install_example(tmp_path, with_scripts=False)

    assert main(['create-hooks', 'validate', str(settings), '--strict']) == 1
    assert 'script not found' in capsys.readouterr().out


def test_fixtures_cover_the_nine_payloads_and_each_names_its_event() -> None:
    assert {path.stem for path in FIXTURES} == {
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
    for path in FIXTURES:
        assert json.loads(path.read_text())['hook_event_name'] == path.stem.split('-')[0]


def test_fixtures_carry_the_corrected_documented_fields() -> None:
    edit = json.loads((PAYLOADS / 'PreToolUse-Edit.json').read_text())
    failure = json.loads((PAYLOADS / 'PostToolUseFailure-Bash.json').read_text())
    subagent = json.loads((PAYLOADS / 'SubagentStop.json').read_text())

    assert Path(edit['tool_input']['file_path']).is_absolute()
    assert re.match(r'Exit code \d+', failure['error'])
    assert 'last_message' not in subagent
    assert {
        'stop_hook_active',
        'agent_id',
        'agent_type',
        'agent_transcript_path',
        'last_assistant_message',
    } <= subagent.keys()


@pytest.mark.parametrize('fixture', FIXTURES, ids=lambda path: path.stem)
def test_template_passes_the_contract_on_every_fixture(fixture: Path) -> None:
    assert run_template(fixture) == []


def test_dangerous_command_is_denied_by_the_example_handler() -> None:
    findings = run_template(
        PAYLOADS / 'PreToolUse-Bash-dangerous.json',
        fields=(
            'hookSpecificOutput.hookEventName=PreToolUse',
            'hookSpecificOutput.permissionDecision=deny',
        ),
    )

    assert findings == []


def test_ordinary_command_gets_no_decision() -> None:
    assert run_template(PAYLOADS / 'PreToolUse-Bash.json', silent=True) == []


def test_release_workflow_edit_asks_the_person() -> None:
    findings = run_template(
        PAYLOADS / 'PreToolUse-Edit.json',
        fields=('hookSpecificOutput.permissionDecision=ask',),
    )

    assert findings == []


def test_bare_runner_command_is_rewritten_when_the_project_has_a_lock_file(tmp_path: Path) -> None:
    (tmp_path / 'uv.lock').touch()
    payload = payload_with(tmp_path, 'PreToolUse-Bash.json', cwd=str(tmp_path))

    findings = run_template(
        payload,
        fields=(
            'hookSpecificOutput.permissionDecision=allow',
            'hookSpecificOutput.updatedInput.command=uv run pytest tests/ -x',
        ),
    )

    assert findings == []


def test_failure_playbook_adds_the_fix_as_context() -> None:
    findings = run_template(
        PAYLOADS / 'PostToolUseFailure-Bash.json',
        fields=(
            'hookSpecificOutput.hookEventName=PostToolUseFailure',
            'hookSpecificOutput.additionalContext',
        ),
    )

    assert findings == []


def test_session_start_reports_the_repository_state(tmp_path: Path) -> None:
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)  # noqa: S603, S607  # fixed git command on a tmp dir
    payload = payload_with(tmp_path, 'SessionStart.json', cwd=str(tmp_path))

    findings = run_template(
        payload,
        fields=(
            'hookSpecificOutput.hookEventName=SessionStart',
            'hookSpecificOutput.additionalContext',
        ),
    )

    assert findings == []


def test_stop_gate_stands_down_when_a_stop_hook_is_already_active(tmp_path: Path) -> None:
    (tmp_path / 'pyproject.toml').touch()
    payload = payload_with(tmp_path, 'Stop-active.json', cwd=str(tmp_path))

    assert run_template(payload, silent=True) == []


def test_subagent_report_gate_blocks_once_then_allows(tmp_path: Path) -> None:
    unstructured = payload_with(tmp_path, 'SubagentStop.json', last_assistant_message='all done')
    already_continuing = tmp_path / 'again.json'
    already_continuing.write_text(
        json.dumps({**json.loads(unstructured.read_text()), 'stop_hook_active': True})
    )

    assert run_template(unstructured, fields=('decision=block', 'reason')) == []
    assert run_template(already_continuing, silent=True) == []


def test_malformed_input_blocks_with_exit_two_under_the_enforce_posture() -> None:
    findings = run_template(PAYLOADS / 'PreToolUse-Bash.json', exit_code=2, malformed=True)

    assert findings == []
