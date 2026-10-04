import json
from dataclasses import dataclass
from pathlib import Path

from ai_engineer_cli.findings import CannotCheckError
from ai_engineer_cli.hook.file import reject_constant

KINDS = ('plugin', 'project', 'user')
SERVER_FILE_NAME = '.mcp.json'


@dataclass(frozen=True)
class McpFile:
    """An MCP config file as read from disk, checked as one of the three kinds.

    A plugin file is the plugin-root `.mcp.json`, a project file is the repository-root
    `.mcp.json`, and a user file is `~/.claude.json`, which holds user servers under a
    top-level `mcpServers` key beside unrelated keys.
    """

    path: Path
    kind: str
    text: str
    document: object
    valid_json: bool

    @property
    def directory(self) -> Path:
        """The directory that holds the file, which `${CLAUDE_PLUGIN_ROOT}` names for a plugin."""
        return self.path.resolve().parent

    def builtin_text(self) -> str:
        """The text of a plugin-root `.mcp.json` that holds this file's servers."""
        if self.kind != 'user' or not isinstance(self.document, dict):
            return self.text
        return json.dumps({'mcpServers': self.document.get('mcpServers', {})})


def load_mcp_file(path: Path, kind: str) -> McpFile:
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as problem:
        message = f'could not read {path}: {problem}'
        raise CannotCheckError(message) from problem
    try:
        document = json.loads(text, parse_constant=reject_constant)
    except ValueError:
        return McpFile(path, kind, text, document=None, valid_json=False)
    return McpFile(path, kind, text, document=document, valid_json=True)
