import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from vibe_code_cli.builtin import Services
from vibe_code_cli.cli import main
from vibe_code_cli.findings import Finding

ASSETS = Path(__file__).resolve().parents[4] / 'skills' / 'create-mcp' / 'assets'
EXAMPLE_SPEC = ASSETS / 'spec.example.json'
TEMPLATE = ASSETS / 'template'

type Spec = dict[str, object]
type RenderedConfig = dict[str, dict[str, object]]
type ServicesFactory = Callable[[Sequence[Finding]], Services]


@dataclass(slots=True, kw_only=True, frozen=True)
class McpFiles:
    root: Path
    services: Services

    @property
    def stdio_server(self) -> dict[str, object]:
        return {'command': 'uv', 'args': ['run', 'server']}

    @property
    def http_server(self) -> dict[str, object]:
        return {'type': 'http', 'url': 'https://example.com/mcp'}

    def write(
        self,
        document: object = None,
        name: str = '.mcp.json',
        *,
        text: str | None = None,
        directory: Path | None = None,
    ) -> Path:
        path = (directory or self.root) / name
        if text is None:
            text = json.dumps(
                {'mcpServers': {'db': self.stdio_server}} if document is None else document
            )
        path.write_text(text)
        return path

    def servers(self, servers: Mapping[str, object], kind: str = 'plugin') -> Path:
        if kind == 'user':
            return self.write({'numStartups': 3, 'mcpServers': servers}, '.claude.json')
        return self.write({'mcpServers': servers})

    def command_config(self, command: str, args: Sequence[str]) -> Path:
        return self.write({'mcpServers': {'db': {'command': command, 'args': args}}})

    def validate(
        self, kind: str, path: Path, *options: str, services: Services | None = None
    ) -> int:
        argv = ['mcp', 'validate', str(path), '--kind', kind, *options]
        return main(argv, services or self.services)


@dataclass(slots=True, kw_only=True, frozen=True)
class Staging:
    services: Services
    staged: dict[str, object]


@dataclass(slots=True, kw_only=True, frozen=True)
class McpScaffold:
    root: Path

    @property
    def target(self) -> Path:
        return self.root / 'out'

    def write_spec_text(self, text: str, directory: Path | None = None) -> Path:
        path = (directory or self.root) / 'spec.json'
        path.write_text(text)
        return path

    def write_spec(self, spec: Spec, directory: Path | None = None) -> Path:
        return self.write_spec_text(json.dumps(spec), directory)

    def scaffolded(self, **changes: object) -> Path:
        assert scaffold(self.write_spec(example_spec(**changes)), self.target) == 0
        return self.target


def example_spec(**changes: object) -> Spec:
    return {**json.loads(EXAMPLE_SPEC.read_text()), **changes}


def tool_changes(index: int = 0, **changes: object) -> Spec:
    tools: list[dict[str, object]] = json.loads(EXAMPLE_SPEC.read_text())['tools']
    tools[index] = {**tools[index], **changes}
    return {'tools': tools}


def scaffold(spec: Path, target: Path, *options: str) -> int:
    return main(['mcp', 'scaffold', str(spec), str(target), *options])


def rendered_config(target: Path, name: str) -> RenderedConfig:
    return json.loads((target / 'config' / name).read_text())['mcpServers']


def rendered_args(target: Path, name: str, server: str) -> list[str]:
    text = (target / 'config' / name).read_text()
    servers: dict[str, dict[str, list[str]]] = json.loads(text)['mcpServers']
    return servers[server]['args']


def written_text(target: Path) -> str:
    return '\n'.join(path.read_text() for path in sorted(target.rglob('*')) if path.is_file())


@pytest.fixture
def mcp_files(tmp_path: Path, fake_services: ServicesFactory) -> McpFiles:
    return McpFiles(root=tmp_path, services=fake_services(()))


@pytest.fixture
def mcp_scaffold(tmp_path: Path) -> McpScaffold:
    return McpScaffold(root=tmp_path)
