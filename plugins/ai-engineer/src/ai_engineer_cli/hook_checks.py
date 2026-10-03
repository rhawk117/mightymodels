from urllib.parse import urlparse

from ai_engineer_cli.findings import CannotCheckError, Finding, error, warning
from ai_engineer_cli.hook_events import (
    DEFAULT_TIMEOUT_SECONDS,
    ENFORCEMENT_EVENTS,
    EVENTS,
    LOWERED_DEFAULT_TIMEOUT_SECONDS,
    SLOW_ENFORCEMENT_SECONDS,
)
from ai_engineer_cli.hook_matchers import matcher_findings
from ai_engineer_cli.hook_nodes import Handler, iter_groups, iter_handlers
from ai_engineer_cli.hook_scripts import script_findings
from ai_engineer_cli.hooks_file import HooksFile, JsonObject, as_object

PLUGIN_TOP_LEVEL_KEYS = frozenset({'hooks', 'description'})

COMMON_FIELDS = frozenset({'type', 'if', 'timeout', 'statusMessage', 'once'})
HANDLER_FIELDS = {
    'command': COMMON_FIELDS | {'command', 'args', 'async', 'asyncRewake', 'shell'},
    'http': COMMON_FIELDS | {'url', 'headers', 'allowedEnvVars'},
    'mcp_tool': COMMON_FIELDS | {'server', 'tool', 'input'},
    'prompt': COMMON_FIELDS | {'prompt', 'model'},
    'agent': COMMON_FIELDS | {'prompt', 'model'},
}

WEB_SCHEMES = frozenset({'http', 'https'})


def check_hooks(hooks_file: HooksFile, *, builtin_errored: bool) -> list[Finding]:
    """The checks `claude plugin validate` is silent on, plus camelCase event names.

    Raises CannotCheckError when the file is not JSON the built-in let pass.
    """
    config = hooks_file.config
    if config is None:
        if builtin_errored:
            return []
        message = (
            f'{hooks_file.path} is not a JSON object the built-in let pass; '
            'the checks could not run'
        )
        raise CannotCheckError(message)
    findings = [
        error(f'duplicate JSON key {key!r}; the last one wins') for key in hooks_file.duplicate_keys
    ]
    if hooks_file.plugin_shape:
        findings.extend(top_level_findings(config))
    hooks = as_object(config.get('hooks'))
    if hooks is not None:
        findings.extend(hooks_findings(hooks, hooks_file))
    return findings


def top_level_findings(config: JsonObject) -> list[Finding]:
    """Row H6, for a plugin file; a settings file has other top-level keys by design."""
    return [
        error(
            f'unknown top-level field {key!r}; a plugin hooks file holds only hooks and description'
        )
        for key in sorted(config.keys() - PLUGIN_TOP_LEVEL_KEYS)
    ]


def hooks_findings(hooks: JsonObject, hooks_file: HooksFile) -> list[Finding]:
    if not hooks:
        return [error('hooks: must not be an empty object')]
    findings = [
        finding for event, entries in hooks.items() for finding in event_findings(event, entries)
    ]
    for group in iter_groups(hooks):
        findings.extend(matcher_findings(group))
        for handler in iter_handlers(group):
            findings.extend(handler_findings(handler, hooks_file))
    return findings


def event_findings(event: str, entries: object) -> list[Finding]:
    """Rows H11a and CH-A24."""
    findings = []
    pascal_case = event[:1].upper() + event[1:]
    if event not in EVENTS and pascal_case in EVENTS:
        findings.append(error(f'hooks.{event}: event names are PascalCase; spell it {pascal_case}'))
    if entries == []:
        findings.append(error(f'hooks.{event}: must not be an empty array'))
    return findings


def handler_findings(handler: Handler, hooks_file: HooksFile) -> list[Finding]:
    handler_type = handler.fields.get('type')
    if not isinstance(handler_type, str) or handler_type not in HANDLER_FIELDS:
        return []
    findings = [
        error(f'{handler.where}: unknown field {key!r} on a {handler_type} handler')
        for key in handler.fields.keys() - HANDLER_FIELDS[handler_type]
    ]
    findings.extend(timeout_findings(handler, handler_type))
    findings.extend(script_findings(handler, hooks_file))
    if handler_type == 'command':
        findings.extend(command_findings(handler))
    if handler_type == 'http':
        findings.extend(http_findings(handler))
    return findings


def command_findings(handler: Handler) -> list[Finding]:
    """Row H18b."""
    command = handler.fields.get('command')
    if isinstance(command, str) and not command.strip():
        return [error(f'{handler.where}: command must not be empty')]
    return []


def http_findings(handler: Handler) -> list[Finding]:
    """Rows H36d and H37."""
    findings = []
    url = handler.fields.get('url')
    if isinstance(url, str) and url.strip() and urlparse(url).scheme.lower() not in WEB_SCHEMES:
        findings.append(error(f'{handler.where}: url must use http:// or https://'))
    variables = handler.fields.get('allowedEnvVars')
    if isinstance(variables, list):
        findings.extend(
            error(f'{handler.where}: allowedEnvVars[{index}] must be a non-empty string')
            for index, name in enumerate(variables)
            if not isinstance(name, str) or not name.strip()
        )
    return findings


def timeout_findings(handler: Handler, handler_type: str) -> list[Finding]:
    """Rows H28 and H31, for the handler types that run for a wall-clock time."""
    if handler_type not in {'command', 'http'} or handler.fields.get('async') is True:
        return []
    if 'timeout' not in handler.fields:
        default = LOWERED_DEFAULT_TIMEOUT_SECONDS.get(handler.event, DEFAULT_TIMEOUT_SECONDS)
        message = f'no timeout set; Claude Code applies its default of {default:g} s'
        return [warning(f'{handler.where}: {message}')]
    seconds = handler.fields['timeout']
    if handler.event in ENFORCEMENT_EVENTS and is_slow(seconds):
        return [
            warning(
                f'{handler.where}: timeout is {seconds:g} s on {handler.event}; a timed-out hook '
                'does not block the call, so keep policy checks tight'
            )
        ]
    return []


def is_slow(seconds: object) -> bool:
    return isinstance(seconds, int | float) and seconds > SLOW_ENFORCEMENT_SECONDS
