import re
from pathlib import Path

from msgspec import UNSET

from ai_engineer_cli.findings import Finding, error, warning
from ai_engineer_cli.hook.file import HooksFile
from ai_engineer_cli.hook.nodes import Handler
from ai_engineer_cli.hook.schema import CommandHook

PLUGIN_ROOT_MARKER = '@CLAUDE_PLUGIN_ROOT@'
PROJECT_DIR_MARKER = '@CLAUDE_PROJECT_DIR@'

PLACEHOLDER = re.compile(r'"?\$\{?(CLAUDE_PLUGIN_ROOT|CLAUDE_PROJECT_DIR)\}?"?')

SCRIPT_SUFFIXES = ('.py', '.sh', '.ps1')
SCRIPT_REFERENCE = re.compile(
    r"(?<![\w.-])([^\s\"'`|;&<>]+\.(?:py|sh|ps1))(?=$|[\s\"'`|;&<>])",
    re.IGNORECASE,
)


def script_findings(handler: Handler, hooks_file: HooksFile) -> list[Finding]:
    """Rows H23a, H23b, H24 and H25: the scripts a command handler names must exist."""
    hook = handler.hook
    if not isinstance(hook, CommandHook):
        return []
    if hook.args is UNSET:
        references = shell_references(hook.command)
    else:
        references = exec_form_references(hook.command, hook.args)
    findings = (script_finding(handler, reference, hooks_file) for reference in references)
    return [finding for finding in findings if finding is not None]


def shell_references(command: str) -> list[str]:
    return [str(reference) for reference in SCRIPT_REFERENCE.findall(marked(command))]


def exec_form_references(command: str, args: list[str]) -> list[str]:
    candidates = [command, *args]
    return [marked(candidate) for candidate in candidates if names_a_script(candidate)]


def names_a_script(value: str) -> bool:
    return value.lower().endswith(SCRIPT_SUFFIXES)


def marked(command: str) -> str:
    """Swap the path placeholders for markers that hold no whitespace, quotes dropped."""
    return PLACEHOLDER.sub(lambda match: f'@{match.group(1)}@', command)


def script_finding(handler: Handler, reference: str, hooks_file: HooksFile) -> Finding | None:
    located = locate(reference, hooks_file)
    if located is None:
        return None
    path, literal_absolute = located
    if not path.exists():
        return missing_script_finding(handler, path, literal_absolute=literal_absolute)
    if not path.is_file():
        return error(f'{handler.where}: script path is not a file: {path}')
    return None


def missing_script_finding(handler: Handler, path: Path, *, literal_absolute: bool) -> Finding:
    if literal_absolute:
        return warning(
            f'{handler.where}: absolute script path {path} does not exist on this machine; '
            'it may be runtime-specific'
        )
    return error(f'{handler.where}: script not found at {path}')


def locate(reference: str, hooks_file: HooksFile) -> tuple[Path, bool] | None:
    """The path a reference names and whether it was written as an absolute path.

    None means the path cannot be checked from here: its root is unknown, it expands at
    runtime, or it is relative to a working directory that is only known when the hook runs.
    """
    roots = (
        (PLUGIN_ROOT_MARKER, hooks_file.plugin_root),
        (PROJECT_DIR_MARKER, hooks_file.project_dir),
    )
    for marker, root in roots:
        if reference.startswith(marker):
            if root is None:
                return None
            return (root / reference.removeprefix(marker).lstrip('/')).resolve(), False
    if '$' in reference or '%' in reference or reference.startswith('~'):
        return None
    path = Path(reference.replace('\\', '/'))
    return (path, True) if path.is_absolute() else None
