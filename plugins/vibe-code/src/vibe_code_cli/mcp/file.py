from dataclasses import dataclass
from pathlib import Path

import msgspec

from vibe_code_cli.findings import CannotCheckError
from vibe_code_cli.jsondoc import Json

KINDS = ('plugin', 'project', 'user')
SERVER_FILE_NAME = '.mcp.json'


@dataclass(slots=True, kw_only=True, frozen=True)
class McpFile:
    path: Path
    kind: str
    text: str
    document: Json
    valid_json: bool

    @property
    def directory(self) -> Path:
        return self.path.resolve().parent

    def builtin_text(self) -> str:
        if self.kind != 'user' or not isinstance(self.document, dict):
            return self.text
        return msgspec.json.encode({'mcpServers': self.document.get('mcpServers', {})}).decode()


def load_mcp_file(path: Path, kind: str) -> McpFile:
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as problem:
        message = f'could not read {path}: {problem}'
        raise CannotCheckError(message) from problem
    try:
        document = msgspec.json.decode(text)
    except msgspec.DecodeError:
        return McpFile(path=path, kind=kind, text=text, document=None, valid_json=False)
    return McpFile(path=path, kind=kind, text=text, document=document, valid_json=True)
