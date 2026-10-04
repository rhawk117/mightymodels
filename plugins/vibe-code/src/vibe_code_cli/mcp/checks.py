import msgspec
from msgspec import UnsetType

from ai_engineer_cli.findings import CannotCheckError, Finding, decode_problem, error, warning
from ai_engineer_cli.jsondoc import Json
from ai_engineer_cli.mcp.file import SERVER_FILE_NAME, McpFile
from ai_engineer_cli.mcp.keys import KEYS_BY_TRANSPORT, STDIO_KEYS
from ai_engineer_cli.mcp.servers import WRAPPER_KEY, McpServer, ServerEntry, decode_servers
from ai_engineer_cli.mcp.variables import variable_findings


def check_mcp(mcp_file: McpFile, *, builtin_errored: bool) -> list[Finding]:
    """The checks `claude plugin validate` is silent on.

    Raises CannotCheckError when the file is not JSON the built-in let pass.
    """
    if not mcp_file.valid_json:
        if builtin_errored:
            return []
        message = f'{mcp_file.path} is not JSON the built-in let pass; the checks could not run'
        raise CannotCheckError(message)
    findings = [
        *filename_findings(mcp_file),
        *shape_findings(mcp_file.kind, mcp_file.document),
    ]
    try:
        servers = decode_servers(mcp_file)
    except msgspec.ValidationError as problem:
        return [*findings, *decode_problem(problem, builtin_errored=builtin_errored)]
    if not servers:
        findings.append(error('no servers found: expected an "mcpServers" object with a server'))
    for name, entry in servers.items():
        findings.extend(server_findings(mcp_file.kind, name, entry))
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


def shape_findings(kind: str, document: Json) -> list[Finding]:
    """Rows M2, M4, M6 and MC-A5: where the servers sit in the file."""
    if not isinstance(document, dict):
        return []
    if WRAPPER_KEY in document:
        return extra_key_findings(kind, document)
    if kind == 'project':
        return [
            warning(f'a project .mcp.json is documented with the {WRAPPER_KEY} wrapper; add it')
        ]
    return []


def extra_key_findings(kind: str, document: dict[str, Json]) -> list[Finding]:
    """Row M4; a user file is `~/.claude.json`, which holds other keys by design."""
    if kind == 'user':
        return []
    return [
        error(f'unexpected top-level key {key!r} beside {WRAPPER_KEY}; it is not a server')
        for key in document
        if key != WRAPPER_KEY
    ]


def server_findings(kind: str, name: str, entry: ServerEntry) -> list[Finding]:
    findings = key_findings(kind, name, entry)
    if entry.server.type == 'sse':
        findings.append(
            warning(f'{name}: the sse transport is deprecated; use "type": "http" where available')
        )
    findings.extend(variable_findings(name, entry.server))
    return findings


def key_findings(kind: str, name: str, entry: ServerEntry) -> list[Finding]:
    """Rows M10a and M10b, and MC-A7 and MC-A10: keys the docs show on no server entry.

    A plugin file is an error, as in the reference plugin schema; a project or user file is a
    warning, as in the reference's documented-field list, because the docs key list is not closed.
    """
    allowed = allowed_keys(entry.server)
    if allowed is None:
        return []
    level = error if kind == 'plugin' else warning
    findings: list[Finding] = []
    for key in entry.keys:
        if key == 'tools':
            findings.append(level(tools_message(name)))
        elif key not in allowed:
            known = ', '.join(sorted(allowed))
            findings.append(
                level(f'{name}: unknown server key {key!r}; the known keys are {known}')
            )
    return findings


def allowed_keys(server: McpServer) -> frozenset[str] | None:
    """The keys for the server's transport; None when the built-in already rejects its type."""
    if isinstance(server.type, UnsetType):
        return None if isinstance(server.url, str) else STDIO_KEYS
    return KEYS_BY_TRANSPORT.get(server.type)


def tools_message(name: str) -> str:
    return (
        f'{name}: "tools" is not a Claude Code server key; narrow the tools with permission '
        'rules mcp__<server>, mcp__<server>__* or mcp__<server>__<tool> in permissions.allow '
        'and permissions.deny'
    )
