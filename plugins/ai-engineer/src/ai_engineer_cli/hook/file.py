import json
from dataclasses import dataclass
from pathlib import Path

import msgspec

from ai_engineer_cli.findings import CannotCheckError
from ai_engineer_cli.jsondoc import JsonObject, as_object, duplicate_keys


@dataclass(frozen=True)
class HooksFile:
    """A hooks file as read from disk, in one of the two shapes Claude Code loads.

    A plugin `hooks/hooks.json` holds the hooks object under a top-level `hooks` key and
    allows one other key; a settings file holds the same `hooks` key beside unrelated keys.
    """

    path: Path
    text: str
    config: JsonObject | None
    duplicate_keys: tuple[str, ...]

    @property
    def plugin_shape(self) -> bool:
        return self.path.name == 'hooks.json'

    @property
    def plugin_root(self) -> Path | None:
        """The parent of `hooks/`, which `${CLAUDE_PLUGIN_ROOT}` names."""
        directory = self.path.resolve().parent
        return directory.parent if directory.name == 'hooks' else None

    @property
    def project_dir(self) -> Path | None:
        """The parent of `.claude/`, which `${CLAUDE_PROJECT_DIR}` names."""
        directory = self.path.resolve().parent
        return directory.parent if directory.name == '.claude' else None

    def hooks_text_for_builtin(self) -> str:
        """The text of a `hooks/hooks.json` that holds this file's hooks object."""
        if self.plugin_shape:
            return self.text
        if self.config is None:
            message = f'{self.path} is not a JSON object, so its hooks cannot be handed to claude'
            raise CannotCheckError(message)
        if 'hooks' not in self.config:
            message = f'{self.path} has no top-level "hooks" key, so there is nothing to validate'
            raise CannotCheckError(message)
        return json.dumps({'hooks': self.config['hooks']})


def load_hooks_file(path: Path) -> HooksFile:
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as problem:
        message = f'could not read {path}: {problem}'
        raise CannotCheckError(message) from problem
    try:
        value = msgspec.json.decode(text)
    except msgspec.DecodeError:
        return HooksFile(path, text, None, ())
    return HooksFile(path, text, as_object(value), duplicate_keys(text))
