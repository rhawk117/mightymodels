import json
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from vibe_code_cli.cli import main

PLUGIN_ROOT = Path(__file__).resolve().parents[4]
SKILLS = PLUGIN_ROOT / 'skills'
PLAN_PLUGIN = SKILLS / 'plan-plugin'
EXAMPLE = PLAN_PLUGIN / 'assets' / 'plan.example.json'
KIND_COMPONENTS = (
    ('skill', 'add-route'),
    ('command', 'ship-it'),
    ('agent', 'test-runner'),
    ('hook', 'uv-runner'),
    ('mcp', 'db-tools'),
    ('lsp', 'pyright'),
    ('executable', 'lint-all'),
    ('output-style', 'terse'),
)


def base_plan() -> dict[str, object]:
    return {
        'name': 'py-harness',
        'description': 'Python conventions for Claude Code sessions.',
        'keywords': ['python'],
        'problem': 'Agents skip ruff.',
        'audience': {'who': 'the team', 'how': 'team'},
        'kinds': ['ecosystem'],
        'ecosystem': 'python',
        'distribution': {'channel': 'local'},
        'author': {'name': 'Platform Team'},
        'components': [{'kind': 'skill', 'name': 'add-route', 'purpose': 'Add a route.'}],
    }


def base_manifest() -> dict[str, object]:
    return {
        'name': 'built-plugin',
        'version': '1.2.0',
        'description': 'A plugin that already exists.',
        'keywords': ['demo'],
        'license': 'MIT',
        'author': {'name': 'Platform Team'},
    }


def component(**changes: object) -> dict[str, object]:
    return {'kind': 'skill', 'name': 'add-route', 'purpose': 'Add a route.', **changes}


def all_kinds() -> list[dict[str, object]]:
    return [
        {'kind': kind, 'name': name, 'purpose': f'The {name} {kind}.'}
        for kind, name in KIND_COMPONENTS
    ]


def markdown(description: str, name: str | None = None) -> str:
    named = f'name: {name}\n' if name else ''
    return f'---\n{named}description: {description}\n---\nBody.\n'


def validate(path: Path, *options: str) -> int:
    return main(['plugin', 'validate', str(path), *options])


def render(plan: Path, target: Path, *options: str) -> int:
    return main(['plugin', 'render', str(plan), str(target), *options])


def inventory(plugin_dir: Path, *options: str) -> int:
    return main(['plugin', 'inventory', str(plugin_dir), *options])


def errors_of(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [line for line in capsys.readouterr().out.splitlines() if line.startswith('error:')]


def components_of(capsys: pytest.CaptureFixture[str]) -> dict[tuple[str, str], dict[str, object]]:
    record = json.loads(capsys.readouterr().out)
    return {(c['kind'], c['name']): c for c in record['components']}


def manifest_of(target: Path) -> dict[str, object]:
    return json.loads((target / '.claude-plugin' / 'plugin.json').read_text())


def directories_of(target: Path) -> set[str]:
    return {path.relative_to(target).as_posix() for path in target.rglob('*') if path.is_dir()}


@dataclass(slots=True, kw_only=True, frozen=True)
class PlanFiles:
    directory: Path

    def write(self, **changes: object) -> Path:
        path = self.directory / 'plan.json'
        path.write_text(json.dumps({**base_plan(), **changes}))
        return path

    def plan_md(self, **changes: object) -> str:
        assert render(self.write(**changes), self.directory / 'out') == 0
        return (self.directory / 'out' / 'PLAN.md').read_text()


@dataclass(slots=True, kw_only=True, frozen=True)
class PluginFiles:
    base: Path

    def write(self, relative: str, text: str) -> Path:
        path = self.base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def build_plugin(self, manifest: Mapping[str, object] | None = None) -> Path:
        self.write(
            'built-plugin/.claude-plugin/plugin.json', json.dumps(manifest or base_manifest())
        )
        self.write('built-plugin/skills/add-route/SKILL.md', markdown('Add a route.'))
        self.write('built-plugin/agents/sub/runner.md', markdown('Run tests.', name='test-runner'))
        self.write('built-plugin/agents/plain.md', markdown('Plain agent.'))
        self.write('built-plugin/commands/ship-it.md', markdown('Ship it.'))
        self.write(
            'built-plugin/hooks/hooks.json',
            json.dumps({'hooks': {'PreToolUse': [], 'Stop': []}}),
        )
        self.write(
            'built-plugin/.mcp.json',
            json.dumps({'mcpServers': {'db': {'command': 'uv', 'args': []}}}),
        )
        self.write(
            'built-plugin/.lsp.json',
            json.dumps({'pyright': {'extensionToLanguage': {'.py': 'python'}}}),
        )
        self.write('built-plugin/bin/lint-all', '#!/bin/sh\n')
        self.write('built-plugin/output-styles/terse.md', markdown('Short answers.'))
        return self.base / 'built-plugin'


@dataclass(slots=True, kw_only=True, frozen=True)
class ClaudeValidate:
    executable: str | None

    def __call__(self, target: Path) -> subprocess.CompletedProcess[str]:
        executable = self.executable or pytest.skip('claude is not on PATH')
        return subprocess.run(  # noqa: S603  # fixed argument list with no shell; target is a tmp path
            [executable, 'plugin', 'validate', '--strict', str(target)],
            capture_output=True,
            text=True,
            check=False,
        )


@pytest.fixture
def plugin_plans(tmp_path: Path) -> PlanFiles:
    return PlanFiles(directory=tmp_path)


@pytest.fixture
def plugin_target(tmp_path: Path) -> Path:
    return tmp_path / 'out'


@pytest.fixture
def plugin_manifest_path(plugin_target: Path) -> Path:
    return plugin_target / '.claude-plugin' / 'plugin.json'


@pytest.fixture
def plugin_files(tmp_path: Path) -> PluginFiles:
    return PluginFiles(base=tmp_path)


@pytest.fixture
def plugin_built(plugin_files: PluginFiles) -> Path:
    return plugin_files.build_plugin()


@pytest.fixture
def plugin_claude_validate() -> ClaudeValidate:
    return ClaudeValidate(executable=shutil.which('claude'))
