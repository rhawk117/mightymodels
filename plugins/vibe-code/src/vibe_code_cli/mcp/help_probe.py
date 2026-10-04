import shutil
import subprocess
from pathlib import Path

import msgspec
from msgspec import UnsetType

from ai_engineer_cli.findings import Finding, error
from ai_engineer_cli.mcp.file import McpFile
from ai_engineer_cli.mcp.servers import McpServer, decode_servers

COMMAND_TIMEOUT_SECONDS = 120
PLUGIN_ROOT = '${CLAUDE_PLUGIN_ROOT}'
MESSAGE_TAIL_CHARACTERS = 200


def check_commands(mcp_file: McpFile) -> list[Finding]:
    """Rows M27 and M28: run `COMMAND ARGS --help` for each stdio server, without a shell.

    A plugin runs in the file's directory, which `${CLAUDE_PLUGIN_ROOT}` names; any other file
    runs in the current directory.
    """
    try:
        servers = decode_servers(mcp_file)
    except msgspec.ValidationError:
        return []
    plugin = mcp_file.kind == 'plugin'
    directory = mcp_file.directory if plugin else Path.cwd()
    findings: list[Finding] = []
    for name, entry in servers.items():
        argv = stdio_argv(entry.server)
        if argv is None:
            continue
        if plugin:
            argv = [item.replace(PLUGIN_ROOT, str(directory)) for item in argv]
        finding = check_invocation(name, argv, directory)
        if finding is not None:
            findings.append(finding)
    return findings


def stdio_argv(server: McpServer) -> list[str] | None:
    """The command and its arguments, or None when the server is not a stdio server with one."""
    transport = 'stdio' if isinstance(server.type, UnsetType) else server.type
    if transport != 'stdio' or isinstance(server.command, UnsetType):
        return None
    return [server.command, *server.args]


def check_invocation(name: str, argv: list[str], directory: Path) -> Finding | None:
    command = argv[0]
    if shutil.which(command) is None and not (directory / command).exists():
        return error(f'{name}: command {command!r} not found on PATH')
    return run_help(name, argv, directory)


def run_help(name: str, argv: list[str], directory: Path) -> Finding | None:
    try:
        completed = subprocess.run(  # noqa: S603  # argument list with no shell; the config names the command
            [*argv, '--help'],
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            cwd=directory,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return error(f'{name}: {argv[0]} --help timed out after {COMMAND_TIMEOUT_SECONDS} s')
    except (OSError, ValueError) as problem:
        return error(f'{name}: {argv[0]} --help failed to run: {problem}')
    if completed.returncode == 0:
        return None
    tail = (completed.stderr or completed.stdout).strip()[:MESSAGE_TAIL_CHARACTERS]
    return error(f'{name}: {argv[0]} --help exited {completed.returncode}: {tail}')
