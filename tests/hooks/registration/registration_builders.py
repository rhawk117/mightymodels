"""The command hooks that hooks/hooks.json registers, flattened for assertions."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMMAND_PATTERN = re.compile(
    r'^"\$\{CLAUDE_PLUGIN_ROOT\}/hooks/(?P<script>[\w-]+\.sh)"(?: (?P<sub>[\w-]+))?$'
)


@dataclass(slots=True, kw_only=True, frozen=True)
class RegisteredHook:
    event: str
    matcher: str | None
    script: str
    subcommand: str | None
    timeout: int


def read_registered_hooks() -> list[RegisteredHook]:
    document = json.loads(ROOT.joinpath('hooks', 'hooks.json').read_text())
    registered: list[RegisteredHook] = []
    for event, groups in document['hooks'].items():
        for group in groups:
            for hook in group['hooks']:
                match = COMMAND_PATTERN.fullmatch(hook['command'])
                assert match, hook['command']
                registered.append(
                    RegisteredHook(
                        event=event,
                        matcher=group.get('matcher'),
                        script=match['script'],
                        subcommand=match['sub'],
                        timeout=hook['timeout'],
                    )
                )

    return registered
