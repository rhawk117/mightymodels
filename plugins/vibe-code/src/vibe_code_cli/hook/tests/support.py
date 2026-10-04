import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from vibe_code_cli.cli import main
from vibe_code_cli.findings import Finding
from vibe_code_cli.hook.checks import check_hooks
from vibe_code_cli.hook.file import load_hooks_file
from vibe_code_cli.hook.nodes import decode_hooks
from vibe_code_cli.hook.runner import Expectations, HookTest, check_hook, parse_field_expectation

SCRIPT_COMMAND = 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check.py"'
ALLOW = "{'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow'}}"
SKILL = Path(__file__).resolve().parents[4] / 'skills' / 'create-hooks'
TEMPLATE = SKILL / 'assets' / 'hook.template.py'
EXAMPLE = SKILL / 'assets' / 'hooks.example.json'
PAYLOADS = SKILL / 'scripts' / 'payloads'
TEST_TIMEOUT_SECONDS = 15.0


def command_handler(command: str = SCRIPT_COMMAND, **extra: object) -> dict[str, object]:
    return {'type': 'command', 'command': command, 'timeout': 10, **extra}


def pre_tool_use(handler: Mapping[str, object], matcher: str | None = 'Bash') -> dict[str, object]:
    group: dict[str, object] = {'hooks': [handler]}
    if matcher is not None:
        group['matcher'] = matcher
    return {'PreToolUse': [group]}


@dataclass(slots=True, kw_only=True, frozen=True)
class HookRoot:
    root: Path

    def write_plugin(self, hooks: object, **top_level: object) -> Path:
        path = self.root / 'hooks' / 'hooks.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        scripts = self.root / 'hooks' / 'scripts'
        scripts.mkdir(exist_ok=True)
        (scripts / 'check.py').write_text('print()\n')
        path.write_text(json.dumps({'hooks': hooks, **top_level}))
        return path

    def write_settings(self, hooks: object, **top_level: object) -> Path:
        path = self.root / '.claude' / 'settings.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**top_level, 'hooks': hooks}))
        return path

    def check(self, path: Path, *, builtin_errored: bool = False) -> list[Finding]:
        hooks_file = load_hooks_file(path)
        decoded = decode_hooks(hooks_file.config)
        return [
            *(schema_finding.finding for schema_finding in decoded.findings),
            *check_hooks(hooks_file, decoded, builtin_errored=builtin_errored),
        ]

    def check_plugin(self, hooks: object, **top_level: object) -> list[Finding]:
        return self.check(self.write_plugin(hooks, **top_level))


@dataclass(slots=True, kw_only=True, frozen=True)
class ScriptRoot:
    root: Path

    def write_script(self, body: str, name: str = 'hook.py') -> Path:
        path = self.root / name
        path.write_text(f'import json, sys\npayload = json.load(sys.stdin)\n{body}\n')
        return path

    def write_payload(self, event: str | None = 'PreToolUse') -> Path:
        path = self.root / 'payload.json'
        payload = {'session_id': 's', 'cwd': '/p', 'tool_name': 'Bash'}
        path.write_text(json.dumps({**payload, 'hook_event_name': event} if event else payload))
        return path

    def run(self, script: Path, payload: Path, *options: str) -> int:
        return main(['hook', 'test', str(script), str(payload), *options])


@dataclass(slots=True, kw_only=True, frozen=True)
class Staging:
    hooks: str
    manifest: bool
    include_manifest: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class StagingRecorder:
    stagings: list[Staging] = field(default_factory=list)

    def __call__(self, target: Path, /, *, include_manifest: bool = True) -> list[Finding]:
        self.stagings.append(
            Staging(
                hooks=(target / 'hooks' / 'hooks.json').read_text(),
                manifest=(target / '.claude-plugin' / 'plugin.json').is_file(),
                include_manifest=include_manifest,
            )
        )
        return []


@dataclass(slots=True, kw_only=True, frozen=True)
class TemplateRun:
    def __call__(
        self,
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
        hook_test = HookTest(
            script=TEMPLATE,
            payload=payload,
            expectations=expectations,
            timeout=TEST_TIMEOUT_SECONDS,
            malformed=malformed,
        )
        return check_hook(hook_test)


@dataclass(slots=True, kw_only=True, frozen=True)
class PayloadFiles:
    root: Path

    def __call__(self, fixture: str, **changes: object) -> Path:
        payload = json.loads((PAYLOADS / fixture).read_text())
        payload.update(changes)
        path = self.root / fixture
        path.write_text(json.dumps(payload))
        return path


@pytest.fixture
def hook_root(tmp_path: Path) -> HookRoot:
    return HookRoot(root=tmp_path)


@pytest.fixture
def hook_other_keys() -> dict[str, object]:
    return {'permissions': {'allow': []}, 'model': 'x'}


@pytest.fixture
def hook_clean_plugin(hook_root: HookRoot) -> Path:
    return hook_root.write_plugin(pre_tool_use(command_handler()))


@pytest.fixture
def hook_scripts(tmp_path: Path) -> ScriptRoot:
    return ScriptRoot(root=tmp_path)


@pytest.fixture
def hook_template_run() -> TemplateRun:
    return TemplateRun()


@pytest.fixture
def hook_payload_with(tmp_path: Path) -> PayloadFiles:
    return PayloadFiles(root=tmp_path)
