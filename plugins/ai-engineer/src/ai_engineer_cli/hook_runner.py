import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ai_engineer_cli.findings import CannotCheckError, Finding, error
from ai_engineer_cli.hook_events import EXIT_2_IGNORED_EVENTS, PLAIN_TEXT_CONTEXT_EVENTS
from ai_engineer_cli.hooks_file import as_object

MALFORMED_PAYLOAD = '{not json'
EXCERPT_CHARACTERS = 300
BLOCKING_EXIT_CODE = 2
SUCCESS_EXIT_CODE = 0

INTERPRETERS = {
    '.py': (sys.executable,),
    '.sh': ('bash',),
    '.ps1': ('pwsh', 'powershell'),
    '.js': ('node',),
    '.mjs': ('node',),
}
INTERPRETER_ARGUMENTS = {'.ps1': ('-File',)}

MISSING = object()


@dataclass(frozen=True)
class FieldExpectation:
    key: str
    expected: str | None


@dataclass(frozen=True)
class Expectations:
    exit_code: int
    fields: tuple[FieldExpectation, ...]
    silent: bool


@dataclass(frozen=True)
class HookTest:
    script: Path
    payload: Path
    expectations: Expectations
    timeout: float
    malformed: bool


def parse_field_expectation(spec: str) -> FieldExpectation:
    key, separator, expected = spec.partition('=')
    if not key:
        message = f'{spec!r} has an empty key'
        raise argparse.ArgumentTypeError(message)
    return FieldExpectation(key, expected if separator else None)


def check_hook(hook_test: HookTest) -> list[Finding]:
    """Run the script on the payload and return how the run breaks the output contract.

    Raises CannotCheckError when the script or payload cannot be read, the payload is not
    JSON, or the script cannot be started.
    """
    payload_text = read_payload(hook_test.payload)
    event = payload_event(payload_text, hook_test.payload)
    command = hook_command(hook_test.script)
    stdin_text = MALFORMED_PAYLOAD if hook_test.malformed else payload_text
    try:
        completed = subprocess.run(  # noqa: S603  # argument list with no shell; running the script is the point
            command,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=hook_test.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [
            error(
                f'timed out after {hook_test.timeout:g} s; '
                'a real hook this slow stalls every matching call'
            )
        ]
    except OSError as problem:
        message = f'{hook_test.script} did not start: {problem}'
        raise CannotCheckError(message) from problem
    return contract_findings(completed, hook_test.expectations, event)


def read_payload(payload: Path) -> str:
    try:
        return payload.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as problem:
        message = f'could not read payload {payload}: {problem}'
        raise CannotCheckError(message) from problem


def payload_event(payload_text: str, payload: Path) -> str | None:
    """The `hook_event_name` of a payload, which says which event the hook is handling."""
    try:
        value = json.loads(payload_text)
    except json.JSONDecodeError as problem:
        message = f'payload {payload} is not JSON: {problem}'
        raise CannotCheckError(message) from problem
    event = value.get('hook_event_name') if isinstance(value, dict) else None
    return event if isinstance(event, str) else None


def hook_command(script: Path) -> list[str]:
    if not script.is_file():
        message = f'script not found: {script}'
        raise CannotCheckError(message)
    suffix = script.suffix.lower()
    candidates = INTERPRETERS.get(suffix)
    if candidates is None:
        return [str(script.resolve())]
    interpreter = next(filter(None, map(shutil.which, candidates)), None)
    if interpreter is None:
        message = f'{" or ".join(candidates)} is not on PATH, so {script} cannot run'
        raise CannotCheckError(message)
    return [interpreter, *INTERPRETER_ARGUMENTS.get(suffix, ()), str(script.resolve())]


def contract_findings(
    completed: subprocess.CompletedProcess[str],
    expectations: Expectations,
    event: str | None,
) -> list[Finding]:
    kind, output = classify_stdout(completed.stdout)
    return [
        *exit_findings(completed, expectations.exit_code, event),
        *stdout_findings(kind, event),
        *silent_findings(kind, expectations),
        *field_findings(output, expectations),
    ]


def exit_findings(
    completed: subprocess.CompletedProcess[str], expected: int, event: str | None
) -> list[Finding]:
    actual = completed.returncode
    findings = []
    if actual != expected:
        hint = ''
        if actual not in {SUCCESS_EXIT_CODE, BLOCKING_EXIT_CODE}:
            hint = ' (any exit other than 0 or 2 is a non-blocking error; only exit 2 blocks)'
        stderr = completed.stderr.strip()[:EXCERPT_CHARACTERS]
        findings.append(error(f'exit {actual}, expected {expected}{hint}; stderr: {stderr}'))
    if actual == BLOCKING_EXIT_CODE and event in EXIT_2_IGNORED_EVENTS:
        findings.append(error(f'exit 2 does not block on {event}; the exit code is ignored there'))
    return findings


Stdout = Literal['empty', 'json', 'text', 'broken']


def classify_stdout(raw: str) -> tuple[Stdout, dict[str, object] | None]:
    """Read stdout the way Claude Code does: `{...}` is JSON, anything else is plain text."""
    text = raw.strip()
    if not text:
        return 'empty', None
    if not (text.startswith('{') and text.endswith('}')):
        return 'text', None
    try:
        return 'json', as_object(json.loads(text))
    except json.JSONDecodeError:
        return 'broken', None


def stdout_findings(kind: Stdout, event: str | None) -> list[Finding]:
    if kind == 'broken':
        return [
            error(
                'stdout starts with { and ends with } but is not one JSON object; '
                'Claude Code reports a hook error'
            )
        ]
    if kind == 'text' and event not in PLAIN_TEXT_CONTEXT_EVENTS:
        return [
            error(
                f'plain-text stdout is not read as context on {event or "this event"}; '
                'print one JSON object or nothing'
            )
        ]
    return []


def silent_findings(kind: Stdout, expectations: Expectations) -> list[Finding]:
    if expectations.silent and kind != 'empty':
        return [error('expected empty stdout, got output')]
    return []


def field_findings(output: dict[str, object] | None, expectations: Expectations) -> list[Finding]:
    findings = []
    for expectation in expectations.fields:
        problem = field_problem(output or {}, expectation)
        if problem is not None:
            findings.append(error(problem))
    return findings


def field_problem(output: dict[str, object], expectation: FieldExpectation) -> str | None:
    value: object = output
    for part in expectation.key.split('.'):
        value = value.get(part, MISSING) if isinstance(value, dict) else MISSING
    if value is MISSING:
        return f'missing field {expectation.key}'
    if expectation.expected is not None and not matches(value, expectation.expected):
        return f'{expectation.key}={json.dumps(value)}, expected {expectation.expected}'
    return None


def matches(value: object, expected: str) -> bool:
    """Compare as JSON when the expected text parses as JSON, as a plain string otherwise."""
    try:
        wanted: object = json.loads(expected)
    except json.JSONDecodeError:
        wanted = expected
    return json.dumps(value, sort_keys=True) == json.dumps(wanted, sort_keys=True)
