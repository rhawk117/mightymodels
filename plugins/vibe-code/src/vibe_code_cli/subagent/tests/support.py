from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from vibe_code_cli.builtin import Services
from vibe_code_cli.cli import main
from vibe_code_cli.findings import Finding

type ServicesFactory = Callable[[Sequence[Finding]], Services]

SECTIONS = ('role', 'context', 'workflow', 'constraints', 'output_format', 'verification')
DESCRIPTION = 'Reviews code for defects. Use when the user asks for a code review.'


def section_text(names: Sequence[str] = SECTIONS) -> str:
    return ''.join(f'<{name}>\nText.\n</{name}>\n\n' for name in names)


def agent_text(fields: dict[str, str | None] | None = None, body: str | None = None) -> str:
    clean_fields: dict[str, str | None] = {
        'name': 'demo-agent',
        'description': DESCRIPTION,
        'tools': 'Read, Grep',
    }
    merged = {**clean_fields, **(fields or {})}
    lines = [f'{key}: {value}' for key, value in merged.items() if value is not None]
    return '---\n' + '\n'.join(lines) + '\n---\n' + (section_text() if body is None else body)


@dataclass(slots=True, kw_only=True, frozen=True)
class AgentRoot:
    root: Path
    capsys: pytest.CaptureFixture[str]
    services: Services

    def write(self, text: str, *, plugin: bool = False, name: str = 'demo-agent.md') -> Path:
        directory = self.root / 'plugin' / 'agents' if plugin else self.root / '.claude' / 'agents'
        directory.mkdir(parents=True)
        path = directory / name
        path.write_text(text)
        return path

    def run(self, path: Path, *options: str, services: Services | None = None) -> tuple[int, str]:
        code = main(['subagent', 'validate', str(path), *options], services or self.services)
        return code, self.capsys.readouterr().out

    def check(
        self, text: str, *, plugin: bool = False, services: Services | None = None
    ) -> tuple[int, str]:
        return self.run(self.write(text, plugin=plugin), services=services)


@pytest.fixture
def subagent_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fake_services: ServicesFactory
) -> AgentRoot:
    return AgentRoot(root=tmp_path, capsys=capsys, services=fake_services(()))
