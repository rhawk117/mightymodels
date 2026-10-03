from ai_engineer_cli.findings import CannotCheckError, Finding, error, warning
from ai_engineer_cli.hooks_file import JsonObject, as_object
from ai_engineer_cli.mcp_file import SERVER_FILE_NAME, McpFile
from ai_engineer_cli.mcp_keys import KEYS_BY_TRANSPORT, STDIO_KEYS
from ai_engineer_cli.mcp_variables import variable_findings

WRAPPER_KEY = 'mcpServers'


def check_mcp(mcp_file: McpFile, *, builtin_errored: bool) -> list[Finding]:
    """The checks `claude plugin validate` is silent on.

    Raises CannotCheckError when the file is not JSON the built-in let pass.
    """
    if not mcp_file.valid_json:
        if builtin_errored:
            return []
        message = f'{mcp_file.path} is not JSON the built-in let pass; the checks could not run'
        raise CannotCheckError(message)
    findings = filename_findings(mcp_file)
    servers, structure = server_map(mcp_file)
    findings.extend(structure)
    if servers is None:
        return findings
    if not servers:
        findings.append(error('no servers found: expected an "mcpServers" object with a server'))
    for name, entry in servers.items():
        server = as_object(entry)
        if server is not None:
            findings.extend(server_findings(mcp_file.kind, name, server))
    return findings


def filename_findings(mcp_file: McpFile) -> list[Finding]:
    """Rows M25 and M26: only a file named `.mcp.json` is read, in a plugin or a project."""
    if mcp_file.kind == 'user' or mcp_file.path.name == SERVER_FILE_NAME:
        return []
    return [
        warning(
            f'{mcp_file.path.name} is never read as a {mcp_file.kind} MCP config; '
            f'Claude Code reads {SERVER_FILE_NAME} at the {mcp_file.kind} root'
        )
    ]


def server_map(mcp_file: McpFile) -> tuple[JsonObject | None, list[Finding]]:
    """Rows M2, M4, M6 and MC-A5: the servers the file holds, or None when its shape is wrong."""
    document = as_object(mcp_file.document)
    if document is None:
        return None, [error('the MCP config must be a JSON object')]
    if WRAPPER_KEY not in document:
        return bare_servers(mcp_file.kind, document)
    servers = as_object(document[WRAPPER_KEY])
    if servers is None:
        return None, [error(f'{WRAPPER_KEY} must be an object that maps names to servers')]
    return servers, extra_key_findings(mcp_file.kind, document)


def bare_servers(kind: str, document: JsonObject) -> tuple[JsonObject, list[Finding]]:
    """A file with no `mcpServers` key: a plugin may be a bare map, a user file holds none."""
    if kind == 'user':
        return {}, []
    if kind == 'plugin':
        return document, []
    return document, [
        warning(f'a project .mcp.json is documented with the {WRAPPER_KEY} wrapper; add it')
    ]


def extra_key_findings(kind: str, document: JsonObject) -> list[Finding]:
    """Row M4; a user file is `~/.claude.json`, which holds other keys by design."""
    if kind == 'user':
        return []
    return [
        error(f'unexpected top-level key {key!r} beside {WRAPPER_KEY}; it is not a server')
        for key in document
        if key != WRAPPER_KEY
    ]


def server_findings(kind: str, name: str, server: JsonObject) -> list[Finding]:
    findings = key_findings(kind, name, server)
    if server.get('type') == 'sse':
        findings.append(
            warning(f'{name}: the sse transport is deprecated; use "type": "http" where available')
        )
    findings.extend(variable_findings(name, server))
    return findings


def key_findings(kind: str, name: str, server: JsonObject) -> list[Finding]:
    """Rows M10a and M10b, and MC-A7 and MC-A10: keys the docs show on no server entry.

    A plugin file is an error, as in the reference plugin schema; a project or user file is a
    warning, as in the reference's documented-field list, because the docs key list is not closed.
    """
    allowed = allowed_keys(server)
    if allowed is None:
        return []
    level = error if kind == 'plugin' else warning
    findings: list[Finding] = []
    for key in server:
        if key == 'tools':
            findings.append(level(tools_message(name)))
        elif key not in allowed:
            known = ', '.join(sorted(allowed))
            findings.append(
                level(f'{name}: unknown server key {key!r}; the known keys are {known}')
            )
    return findings


def allowed_keys(server: JsonObject) -> frozenset[str] | None:
    """The keys for the server's transport; None when the built-in already rejects its type."""
    if 'type' not in server:
        return None if 'url' in server else STDIO_KEYS
    transport = server['type']
    return KEYS_BY_TRANSPORT.get(transport) if isinstance(transport, str) else None


def tools_message(name: str) -> str:
    return (
        f'{name}: "tools" is not a Claude Code server key; narrow the tools with permission '
        'rules mcp__<server>, mcp__<server>__* or mcp__<server>__<tool> in permissions.allow '
        'and permissions.deny'
    )
