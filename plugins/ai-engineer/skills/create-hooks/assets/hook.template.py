"""HOOK_NAME: ONE_LINE_PURPOSE.

Claude Code command hook for the EVENT_NAME event, failure posture POSTURE_VALUE. One JSON payload
on stdin, one JSON object on stdout or nothing, diagnostics on stderr. The payload names its event
in `hook_event_name`, so `HANDLERS` dispatches on it and the config needs no extra argument.

Every decision the host acts on has one constructor below (`deny`, `ask`, `rewrite`, `context`,
`block`, `block_once`), so a handler never spells a field name. Context for the model is XML:
named sections with Markdown inside, wrapped in one `<hook_context>` element, because the model
reads that as structure rather than as more prose. The example handlers are working code for the
common hook shapes; keep the ones this hook needs and delete the rest.
"""

from __future__ import annotations

import json
import logging
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

HOOK_NAME = 'HOOK_NAME'
COMMAND_TIMEOUT_SECONDS = 4
GATE_TIMEOUT_SECONDS = 120
GATE_COMMAND = ('uv', 'run', 'pytest', '-q', '-x')
OUTPUT_PREVIEW_CHARS = 2000
BLOCK_REASON_LINES = 40
BLOCKING_EXIT_CODE = 2
RUNNER_TOOLS = frozenset({'pytest', 'ruff', 'mypy'})
SHELLS = frozenset({'sh', 'bash', 'zsh'})
DOWNLOADERS = frozenset({'curl', 'wget'})

log = logging.getLogger(HOOK_NAME)


class Event(StrEnum):
    PRE_TOOL_USE = 'PreToolUse'
    POST_TOOL_USE_FAILURE = 'PostToolUseFailure'
    SESSION_START = 'SessionStart'
    STOP = 'Stop'
    SUBAGENT_STOP = 'SubagentStop'


class Posture(StrEnum):
    ENFORCE = 'enforce'
    GATE = 'gate'
    CONTEXT = 'context'
    TRACKING = 'tracking'


POSTURE = Posture.ENFORCE


class PayloadShapeError(ValueError):
    def __init__(self) -> None:
        super().__init__('payload is not a JSON object')


class HookInput(TypedDict):
    session_id: str
    transcript_path: str
    cwd: str
    hook_event_name: str
    permission_mode: NotRequired[str]
    agent_id: NotRequired[str]
    agent_type: NotRequired[str]


class PreToolUseInput(HookInput):
    tool_name: str
    tool_input: dict[str, object]
    tool_use_id: NotRequired[str]


class PostToolUseFailureInput(HookInput):
    tool_name: str
    tool_input: dict[str, object]
    error: str
    is_interrupt: NotRequired[bool]


class SessionStartInput(HookInput):
    source: Literal['startup', 'resume', 'clear', 'compact', 'fork']


class StopInput(HookInput):
    stop_hook_active: bool
    last_assistant_message: NotRequired[str]


class SubagentStopInput(HookInput):
    stop_hook_active: bool
    agent_transcript_path: str
    last_assistant_message: str


type HookOutput = dict[str, object]
type Handler = Callable[..., HookOutput | None]


@dataclass(frozen=True, slots=True)
class ContextSection:
    tag: str
    body: str
    attributes: Mapping[str, str] = field(default_factory=dict)

    def render(self) -> str:
        attributes = ''.join(
            f' {name}="{escape_attribute(value)}"' for name, value in self.attributes.items()
        )
        return f'<{self.tag}{attributes}>\n{self.body.strip()}\n</{self.tag}>'


def escape_attribute(value: str) -> str:
    return value.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;')


def render_context(sections: Iterable[ContextSection]) -> str:
    inner = '\n'.join(section.render() for section in sections)
    return f'<hook_context hook="{HOOK_NAME}">\n{inner}\n</hook_context>'


def specific(event: Event, **fields: object) -> HookOutput:
    return {'hookSpecificOutput': {'hookEventName': event.value, **fields}}


def deny(reason: str) -> HookOutput:
    return specific(Event.PRE_TOOL_USE, permissionDecision='deny', permissionDecisionReason=reason)


def ask(reason: str) -> HookOutput:
    return specific(Event.PRE_TOOL_USE, permissionDecision='ask', permissionDecisionReason=reason)


def rewrite(tool_input: Mapping[str, object], why: str) -> HookOutput:
    return specific(
        Event.PRE_TOOL_USE,
        permissionDecision='allow',
        permissionDecisionReason=why,
        updatedInput=dict(tool_input),
        additionalContext=why,
    )


def context(event: Event, *sections: ContextSection) -> HookOutput:
    return specific(event, additionalContext=render_context(sections))


def block(reason: str) -> HookOutput:
    return {'decision': 'block', 'reason': reason}


def block_once(payload: Mapping[str, object], reason: str) -> HookOutput | None:
    if payload.get('stop_hook_active'):
        return None
    return block(reason)


TOKEN_PATTERNS = (
    re.compile(r'gh[pousr]_[A-Za-z0-9_.-]{20,}'),
    re.compile(r'Bearer [A-Za-z0-9_.-]+'),
    re.compile(r'(--password|--token)[= ]\S+'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
)


def redact(text: str) -> str:
    for pattern in TOKEN_PATTERNS:
        text = pattern.sub('[REDACTED]', text)
    return text


@dataclass(frozen=True, slots=True)
class CommandResult:
    succeeded: bool
    exit_code: int | None
    stdout: str = ''
    stderr: str = ''
    error: str | None = None

    @property
    def output(self) -> str:
        return (self.stdout + self.stderr).strip()

    def tail(self, lines: int = BLOCK_REASON_LINES) -> str:
        return '\n'.join(self.output.splitlines()[-lines:])


@dataclass(frozen=True, slots=True)
class CommandRunner:
    cwd: Path
    timeout: int = COMMAND_TIMEOUT_SECONDS

    def run(self, arguments: Sequence[str]) -> CommandResult:
        try:
            completed = subprocess.run(
                list(arguments),
                cwd=self.cwd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            return CommandResult(
                succeeded=False,
                exit_code=None,
                stdout=decode(error.stdout),
                stderr=decode(error.stderr),
                error=f'{arguments[0]} exceeded {self.timeout} seconds',
            )
        except OSError as error:
            return CommandResult(succeeded=False, exit_code=None, error=f'{arguments[0]}: {error}')
        return CommandResult(
            succeeded=completed.returncode == 0,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def decode(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors='replace')
    return value or ''


def shell_words(tool_input: Mapping[str, object]) -> list[str]:
    command = tool_input.get('command')
    if not isinstance(command, str):
        return []
    try:
        return shlex.split(command)
    except ValueError:
        return []


def pipes_download_to_shell(words: Sequence[str]) -> bool:
    if words[0] not in DOWNLOADERS or '|' not in words:
        return False
    after_pipe = words[words.index('|') + 1 :]
    return bool(after_pipe) and Path(after_pipe[0]).name in SHELLS


def is_release_workflow(file_path: str) -> bool:
    parts = Path(file_path).parts
    return '.github' in parts and 'workflows' in parts


def on_pre_tool_use(payload: PreToolUseInput) -> HookOutput | None:
    tool_input = payload['tool_input']
    file_path = tool_input.get('file_path')
    if isinstance(file_path, str) and is_release_workflow(file_path):
        return ask('This edits a release workflow; the person decides whether the change is wanted.')
    words = shell_words(tool_input)
    if not words:
        return None
    if pipes_download_to_shell(words):
        return deny(
            'Piping a download into a shell is not allowed from an agent session. Download the '
            'script to a file, read it, then run it.'
        )
    if words[:2] == ['git', 'push'] and '--force' in words:
        return deny(
            'Force-push is not allowed from an agent session. Open a PR from a branch instead; '
            'a human can force-push after review.'
        )
    if words[:2] == ['git', 'push']:
        return ask('Pushing to the remote; the person decides whether this branch is ready.')
    if words[0] in RUNNER_TOOLS and (Path(payload['cwd']) / 'uv.lock').exists():
        wrapped = {**tool_input, 'command': shlex.join(['uv', 'run', *words])}
        return rewrite(
            wrapped,
            f'`{words[0]}` now runs through `uv run` so the project environment applies.',
        )
    return None


RECOVERIES: dict[str, str] = {
    'ModuleNotFoundError': (
        'Run `uv sync` to install the project environment, then retry the command.'
    ),
    'command not found': (
        'The tool is not on PATH; use the project runner (`uv run`), not the bare name.'
    ),
}


def on_post_tool_use_failure(payload: PostToolUseFailureInput) -> HookOutput | None:
    if payload.get('is_interrupt'):
        return None
    error = payload['error']
    matches = [advice for marker, advice in RECOVERIES.items() if marker in error]
    if not matches:
        return None
    return context(
        Event.POST_TOOL_USE_FAILURE,
        ContextSection('failure', error[-OUTPUT_PREVIEW_CHARS:], {'tool': payload['tool_name']}),
        ContextSection('recovery', '\n'.join(f'- {advice}' for advice in matches)),
    )


def on_session_start(payload: SessionStartInput) -> HookOutput | None:
    runner = CommandRunner(Path(payload['cwd']))
    status = runner.run(['git', 'status', '--short', '--branch'])
    if not status.succeeded:
        return None
    return context(
        Event.SESSION_START,
        ContextSection(
            'repository_state',
            f'```\n{status.stdout.strip()}\n```',
            {'source': payload['source']},
        ),
        ContextSection(
            'conventions',
            'This repo runs `uv run ruff check .` and `uv run pytest -q` before work is done.',
        ),
    )


def on_stop(payload: StopInput) -> HookOutput | None:
    if payload['stop_hook_active'] or not (Path(payload['cwd']) / 'pyproject.toml').exists():
        return None
    tests = CommandRunner(Path(payload['cwd']), timeout=GATE_TIMEOUT_SECONDS).run(GATE_COMMAND)
    if tests.error is not None:
        log.warning('gate could not run, allowing: %s', tests.error)
        return None
    if tests.succeeded:
        return None
    reason = render_context(
        [
            ContextSection(
                'gate_failed', f'```\n{tests.tail()}\n```', {'command': ' '.join(GATE_COMMAND)}
            ),
            ContextSection(
                'instruction',
                'Fix the failing tests before finishing. Do not skip or delete them.',
            ),
        ]
    )
    return block_once(payload, reason)


def on_subagent_stop(payload: SubagentStopInput) -> HookOutput | None:
    if '<report>' in payload['last_assistant_message']:
        return None
    return block_once(payload, 'Return the findings inside a <report> element, then finish.')


HANDLERS: dict[str, Handler] = {
    Event.PRE_TOOL_USE: on_pre_tool_use,
    Event.POST_TOOL_USE_FAILURE: on_post_tool_use_failure,
    Event.SESSION_START: on_session_start,
    Event.STOP: on_stop,
    Event.SUBAGENT_STOP: on_subagent_stop,
}


def fail(detail: str) -> int:
    if POSTURE is Posture.ENFORCE:
        sys.stderr.write(
            f'{HOOK_NAME} could not evaluate this call ({detail}). '
            'Fix the hook script, then retry.\n'
        )
        return BLOCKING_EXIT_CODE
    log.warning('internal error, continuing without a decision: %s', detail)
    return 0


def read_payload(stream: str) -> dict[str, object]:
    payload = json.loads(stream)
    if not isinstance(payload, dict):
        raise PayloadShapeError
    return payload


def dispatch(stream: str) -> HookOutput | None:
    payload = read_payload(stream)
    event_name = payload.get('hook_event_name')
    handler = HANDLERS.get(event_name) if isinstance(event_name, str) else None
    if handler is None:
        log.info('no handler registered for %s', event_name)
        return None
    return handler(payload)


def main() -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format=f'{HOOK_NAME}: %(message)s',
    )
    try:
        output = dispatch(sys.stdin.read())
    except Exception as error:
        return fail(redact(f'{type(error).__name__}: {error}'))
    if output is not None:
        sys.stdout.write(json.dumps(output) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
