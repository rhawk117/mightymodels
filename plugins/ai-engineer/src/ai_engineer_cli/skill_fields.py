import re
from collections.abc import Callable
from pathlib import Path

from ai_engineer_cli.findings import Finding, error, warning

# The 17 keys in the Claude Code skills frontmatter table, plus the agentskills.io keys
# license, compatibility and metadata, which the checks below also validate.
KNOWN_KEYS = frozenset(
    {
        'name',
        'description',
        'allowed-tools',
        'disable-model-invocation',
        'user-invocable',
        'argument-hint',
        'when_to_use',
        'arguments',
        'paths',
        'shell',
        'context',
        'agent',
        'background',
        'hooks',
        'effort',
        'model',
        'disallowed-tools',
        'license',
        'compatibility',
        'metadata',
    }
)
NAME_MAX = 64
DESCRIPTION_MAX = 1024
LISTING_MAX = 1536
COMPATIBILITY_MAX = 500
NAME_PATTERN = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
TOOL_RULE = re.compile(r'\*|[A-Za-z][A-Za-z0-9_.*-]*(?:\([^()\r\n]+\))?')
TRUE_VALUES = frozenset({'true', 'yes', 'on', '1'})
FALSE_VALUES = frozenset({'false', 'no', 'off', '0'})
INVOCATION_FLAGS = ('disable-model-invocation', 'user-invocable')


def check_fields(fields: dict[str, object], directory_name: str) -> list[Finding]:
    return [
        *check_unknown_keys(fields),
        *check_name(fields, directory_name),
        *check_description(fields),
        *check_optional_strings(fields),
        *check_metadata(fields),
        *check_invocation(fields),
        *check_allowed_tools(fields),
    ]


def check_unknown_keys(fields: dict[str, object]) -> list[Finding]:
    return [error(f'unknown frontmatter field {key!r}') for key in fields if key not in KNOWN_KEYS]


def check_name(fields: dict[str, object], directory_name: str) -> list[Finding]:
    name = fields.get('name')
    if name is None:
        return [warning('name is missing; Claude Code falls back to the directory name')]
    if not isinstance(name, str):
        return []
    return check_name_value(name, directory_name)


def check_name_value(name: str, directory_name: str) -> list[Finding]:
    if not name.strip():
        return [error('name must not be empty')]
    if len(name) > NAME_MAX or NAME_PATTERN.fullmatch(name) is None:
        return [
            error(
                f'name {name!r} must be 1 to {NAME_MAX} chars of lowercase letters, digits, '
                'and single hyphens, without leading or trailing hyphens'
            )
        ]
    if name != directory_name:
        return [error(f'name {name!r} must equal the directory name {directory_name!r}')]
    return []


def check_description(fields: dict[str, object]) -> list[Finding]:
    description = fields.get('description')
    if not isinstance(description, str):
        return []
    if not description.strip():
        return [error('description must not be empty')]
    findings = []
    if len(description) > DESCRIPTION_MAX:
        findings.append(
            error(f'description is {len(description)} chars; the limit is {DESCRIPTION_MAX}')
        )
    when_to_use = fields.get('when_to_use')
    listing_length = len(description) + (len(when_to_use) if isinstance(when_to_use, str) else 0)
    if listing_length > LISTING_MAX:
        findings.append(
            warning(
                f'description and when_to_use total {listing_length} chars; '
                f'Claude Code truncates the skill listing at {LISTING_MAX}'
            )
        )
    return findings


def check_optional_strings(fields: dict[str, object]) -> list[Finding]:
    return [
        *optional_string(fields, 'license', None),
        *optional_string(fields, 'compatibility', COMPATIBILITY_MAX),
        *optional_string(fields, 'argument-hint', None),
    ]


def optional_string(fields: dict[str, object], key: str, max_length: int | None) -> list[Finding]:
    if key not in fields:
        return []
    value = fields[key]
    if not isinstance(value, str):
        problem = f'{key} must be a string, got {type(value).__name__}'
    elif not value.strip():
        problem = f'{key} must not be empty when provided'
    elif max_length is not None and len(value) > max_length:
        problem = f'{key} is {len(value)} chars; the limit is {max_length}'
    else:
        return []
    return [error(problem)]


def check_metadata(fields: dict[str, object]) -> list[Finding]:
    metadata = fields.get('metadata')
    if not isinstance(metadata, dict):
        return []
    return [
        error(f'metadata must contain only string keys and string values; got {key!r}: {value!r}')
        for key, value in metadata.items()
        if not isinstance(key, str) or not isinstance(value, str)
    ]


def as_flag(value: object) -> bool | None:
    text = str(value).lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return None


def check_invocation(fields: dict[str, object]) -> list[Finding]:
    flags = {key: as_flag(fields[key]) for key in INVOCATION_FLAGS if key in fields}
    findings = [
        error(f'{key} must be true or false (or yes, no, on, off, 1, 0), got {fields[key]!r}')
        for key, flag in flags.items()
        if flag is None
    ]
    human_only = flags.get('disable-model-invocation') is True
    if human_only and flags.get('user-invocable') is False:
        findings.append(
            error(
                'disable-model-invocation: true with user-invocable: false leaves the skill '
                'neither user-invocable nor model-invocable'
            )
        )
    if human_only and 'argument-hint' not in fields:
        findings.append(
            warning('human-only skill has no argument-hint for the slash-command picker')
        )
    return findings


def split_outside_parens(text: str, is_separator: Callable[[str], bool]) -> list[str]:
    pieces = ['']
    depth = 0
    for char in text:
        if char == '(':
            depth += 1
        elif char == ')':
            depth = max(depth - 1, 0)
        if depth == 0 and is_separator(char):
            pieces.append('')
        else:
            pieces[-1] += char
    return pieces


def split_tool_string(text: str) -> list[str]:
    entries: list[str] = []
    for segment in split_outside_parens(text, lambda char: char == ','):
        words = [word for word in split_outside_parens(segment, str.isspace) if word]
        entries.extend(words or [''])
    return entries


def check_allowed_tools(fields: dict[str, object]) -> list[Finding]:
    value = fields.get('allowed-tools')
    if isinstance(value, str):
        return check_tool_string(value)
    if isinstance(value, list):
        items = [item.strip() for item in value if isinstance(item, str)]
        if len(items) == len(value):
            return check_tool_list(items)
    return []


def check_tool_string(value: str) -> list[Finding]:
    if not value.strip():
        return [error('allowed-tools must not be an empty string')]
    return check_tool_entries(split_tool_string(value))


def check_tool_list(value: list[str]) -> list[Finding]:
    if not value:
        return [error('allowed-tools must not be an empty list')]
    return check_tool_entries(value)


def check_tool_entries(entries: list[str]) -> list[Finding]:
    findings = [
        error(f'allowed-tools entry {entry!r} is not a Claude Code rule such as Bash(uv *)')
        for entry in entries
        if entry and TOOL_RULE.fullmatch(entry) is None
    ]
    if '' in entries:
        findings.append(error('allowed-tools contains an empty entry'))
    if '*' in entries and len(entries) > 1:
        findings.append(
            warning("allowed-tools contains '*' plus other entries; the others are redundant")
        )
    return findings


def directory_name_of(skill_dir: Path) -> str:
    return skill_dir.resolve().name
