import os
import re

from vibe_code_cli.findings import Finding, warning
from vibe_code_cli.mcp.keys import (
    CREDENTIAL_VARIABLES,
    PROVIDED_VARIABLES,
    REMOTE_TRANSPORTS,
    USER_CONFIG_PREFIX,
)
from vibe_code_cli.mcp.servers import McpServer

# `${VAR}` and `${VAR:-default}`, the two forms mcp.md:633 to mcp.md:634 lists.
REFERENCE = re.compile(r'\$\{([A-Za-z_][\w.]*)(:-[^}]*)?\}')
BARE_REFERENCE = re.compile(r'\$[A-Za-z_]\w*')
REMOTE_LOCATIONS = ('url', 'headers.')


def variable_findings(name: str, server: McpServer) -> list[Finding]:
    """Rows MC-A9 and MC-B4: variable references in the places Claude Code expands them.

    A finding names the variable and the key, never the value, because `env` and `headers`
    hold credentials.
    """
    remote = server.type in REMOTE_TRANSPORTS
    findings: list[Finding] = []
    for location, text in expandable_values(server):
        credentials_empty = remote and location.startswith(REMOTE_LOCATIONS)
        findings.extend(
            text_findings(f'{name}.{location}', text, credentials_empty=credentials_empty)
        )
    return findings


def expandable_values(server: McpServer) -> list[tuple[str, str]]:
    """The string values of `command`, `args`, `env`, `url` and `headers` (mcp.md:640 to 644)."""
    candidates = [('command', server.command), ('url', server.url)]
    candidates.extend((f'args[{index}]', value) for index, value in enumerate(server.args))
    for key, mapping in (('env', server.env), ('headers', server.headers)):
        candidates.extend((f'{key}.{entry}', value) for entry, value in mapping.items())
    return [(location, value) for location, value in candidates if isinstance(value, str)]


def text_findings(where: str, text: str, *, credentials_empty: bool) -> list[Finding]:
    findings: list[Finding] = []
    for match in REFERENCE.finditer(text):
        variable = match.group(1)
        has_default = match.group(2) is not None
        findings.extend(
            reference_findings(
                where, variable, has_default=has_default, credentials_empty=credentials_empty
            )
        )
    if BARE_REFERENCE.search(text):
        findings.append(
            warning(f'{where}: a bare $NAME reference is not expanded; write it as ${{NAME}}')
        )
    return findings


def reference_findings(
    where: str, variable: str, *, has_default: bool, credentials_empty: bool
) -> list[Finding]:
    if credentials_empty and variable in CREDENTIAL_VARIABLES:
        return [
            warning(
                f'{where}: ${{{variable}}} reads as empty in a remote server url or headers, '
                'even with a default; copy it into a variable with a name of your own'
            )
        ]
    if has_default or provided(variable) or variable in os.environ:
        return []
    return [
        warning(
            f'{where}: ${{{variable}}} is not set here and has no :-default; Claude Code loads '
            'the server with the text unexpanded'
        )
    ]


def provided(variable: str) -> bool:
    return variable in PROVIDED_VARIABLES or variable.startswith(USER_CONFIG_PREFIX)
