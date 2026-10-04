import json
import keyword
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from ai_engineer_cli.findings import CannotCheckError

Spec = dict[str, Any]
Json = Spec | list[Any] | str | float | bool | None

NAME_PATTERN = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
IDENTIFIER = re.compile(r'[a-z_][a-z0-9_]*')
PROPERTY_NAME = re.compile(r'[A-Za-z0-9_.-]{1,64}')
PLACEHOLDER = re.compile(r'\{(\w+)\}')
MAX_NAME_LENGTH = 64
MAX_RESULT_CHARS = 500_000
INSTRUCTIONS_LIMIT = 2048
PYTHON_TYPES = (
    'str',
    'int',
    'float',
    'bool',
    'list[str]',
    'list[int]',
    'dict[str, str]',
    'list[dict[str, str]]',
)
SIDE_EFFECTS = ('read_only', 'writes', 'destructive')
REACHES = ('local', 'network', 'both')
ROOT_SOURCES = ('cwd', 'parameter', 'env', 'roots')
KIND_NAMES: dict[type, str] = {
    str: 'a string',
    bool: 'true or false',
    int: 'an integer',
    list: 'a list',
    dict: 'an object',
}
ROOT_PARAMETER = {
    'name': 'root',
    'type': 'str',
    'description': (
        'Absolute path of the repository the session is working in; '
        'pass the current working directory.'
    ),
    'required': True,
}
DEFAULT_OUTPUT = {
    'name': 'summary',
    'type': 'str',
    'description': 'What happened, for the model to read.',
}


def reject(message: str) -> NoReturn:
    raise CannotCheckError(message)


def is_identifier(text: str) -> bool:
    return (
        IDENTIFIER.fullmatch(text) is not None
        and len(text) <= MAX_NAME_LENGTH
        and not keyword.iskeyword(text)
    )


def _reject_constant(_: str) -> NoReturn:
    message = 'NaN and Infinity are not valid JSON'
    raise ValueError(message)


@dataclass(frozen=True, slots=True)
class Fields:
    """One JSON object of the spec; every rejection names the field and never echoes a value."""

    source: Spec
    where: str = ''

    def get[T](self, key: str, kind: type[T], default: T) -> T:
        value = self.source.get(key, default)
        if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
            reject(f'{self.where}{key} must be {KIND_NAMES[kind]}')
        return value

    def text(self, key: str, default: str = '') -> str:
        return self.get(key, str, default)

    def flag(self, key: str, *, default: bool) -> bool:
        return self.get(key, bool, default)

    def choice(self, key: str, choices: tuple[str, ...], default: str) -> str:
        value = self.text(key, default)
        if value not in choices:
            reject(f'{self.where}{key} must be one of {", ".join(choices)}')
        return value

    def objects(self, key: str) -> list['Fields']:
        items = self.get(key, list, [])
        if not all(isinstance(item, dict) for item in items):
            reject(f'{self.where}{key} must be a list of objects')
        return [Fields(item, f'{self.where}{key}[{index}].') for index, item in enumerate(items)]

    def strings(self, key: str) -> list[str]:
        items = self.get(key, list, [])
        strings = [str(item) for item in items if isinstance(item, str) and item]
        if len(strings) != len(items):
            reject(f'{self.where}{key} must be a list of non-empty strings')
        return strings

    def identifier(self, key: str, default: str = '') -> str:
        value = self.text(key, default)
        if not is_identifier(value):
            reject(f'{self.where}{key} must be a lowercase snake_case Python identifier')
        return value


def load_spec(path: Path) -> Spec:
    """Read and normalize a spec file; raise CannotCheckError for anything it rejects."""
    try:
        document = json.loads(path.read_text(encoding='utf-8'), parse_constant=_reject_constant)
    except (OSError, UnicodeError) as problem:
        reject(f'cannot read the spec {path}: {type(problem).__name__}')
    except ValueError as problem:
        reject(f'{path} is not valid JSON: {problem}')
    return normalize_spec(document)


def normalize_spec(document: Json) -> Spec:
    if not isinstance(document, dict):
        reject('the spec must be a JSON object')
    fields = Fields(document)
    name = fields.text('name')
    if NAME_PATTERN.fullmatch(name) is None or len(name) > MAX_NAME_LENGTH:
        reject(f'name must be kebab-case, at most {MAX_NAME_LENGTH} characters')
    description = fields.text('description', f'{name} MCP server')
    tools = fields.objects('tools')
    if not tools:
        reject('at least one tool is required')
    root_source = fields.choice('root_source', ROOT_SOURCES, 'cwd')
    return {
        **document,
        'name': name,
        'package': fields.identifier('package', name.replace('-', '_')),
        'description': description,
        'instructions': fields.text('instructions', description),
        'reach': fields.choice('reach', REACHES, 'local'),
        'root_source': root_source,
        'always_load': fields.flag('always_load', default=False),
        'binaries': fields.strings('binaries'),
        'resources': [normalize_resource(item) for item in fields.objects('resources')],
        'prompts': [normalize_prompt(item) for item in fields.objects('prompts')],
        'tools': [normalize_tool(root_source, tool) for tool in tools],
    }


def normalize_tool(root_source: str, tool: Fields) -> Spec:
    name = tool.identifier('name')
    inputs = tool.objects('inputs')
    if root_source == 'parameter' and all(item.source.get('name') != 'root' for item in inputs):
        inputs = [Fields(dict(ROOT_PARAMETER), f'{tool.where}inputs[root].'), *inputs]
    outputs = tool.objects('outputs') or [Fields(dict(DEFAULT_OUTPUT), f'{tool.where}outputs[0].')]
    if 'max_result_chars' in tool.source:
        check_result_size(tool)
    return {
        **tool.source,
        'name': name,
        'description': tool.text('description', name.replace('_', ' ')),
        'binary': tool.text('binary'),
        'arguments': tool.strings('arguments'),
        'side_effects': tool.choice('side_effects', SIDE_EFFECTS, 'read_only'),
        'confirm': tool.flag('confirm', default=False),
        'inputs': [normalize_parameter(item, is_input=True) for item in inputs],
        'outputs': [normalize_parameter(item, is_input=False) for item in outputs],
    }


def check_result_size(tool: Fields) -> None:
    size = tool.get('max_result_chars', int, 0)
    if not 0 < size <= MAX_RESULT_CHARS:
        reject(f'{tool.where}max_result_chars must be from 1 to {MAX_RESULT_CHARS}')


def normalize_parameter(parameter: Fields, *, is_input: bool) -> Spec:
    if is_input and PROPERTY_NAME.fullmatch(parameter.text('name')) is None:
        reject(f'{parameter.where}name must be 1 to 64 characters of letters, digits, _, . and -')
    name = parameter.identifier('name')
    kind = parameter.choice('type', PYTHON_TYPES, 'str')
    default = parameter.source.get('default')
    if default is not None and not isinstance(default, str | int | float | bool | list | dict):
        reject(f'{parameter.where}default must be a JSON value')
    return {
        **parameter.source,
        'name': name,
        'type': kind,
        'description': parameter.text('description', name.replace('_', ' ')),
        'required': parameter.flag('required', default=True),
    }


def normalize_resource(resource: Fields) -> Spec:
    uri = resource.text('uri')
    leftover = PLACEHOLDER.sub('', uri)
    if not uri or '{' in leftover or '}' in leftover:
        reject(f'{resource.where}uri must be non-empty with placeholders of the form {{name}}')
    if not all(is_identifier(item) for item in PLACEHOLDER.findall(uri)):
        reject(f'{resource.where}uri placeholders must be snake_case Python identifiers')
    name = resource.identifier('name', re.sub(r'\W+', '_', uri).strip('_').lower())
    return {
        **resource.source,
        'uri': uri,
        'name': name,
        'description': resource.text('description', name),
        'mime_type': resource.text('mime_type', 'text/plain'),
    }


def normalize_prompt(prompt: Fields) -> Spec:
    name = prompt.identifier('name')
    arguments = prompt.objects('arguments')
    names = [argument.identifier('name') for argument in arguments]
    template = prompt.text('template', f'{name}: ' + ' '.join(f'{{{item}}}' for item in names))
    leftover = PLACEHOLDER.sub(lambda match: '' if match[1] in names else '{', template)
    if '{' in leftover or '}' in leftover:
        reject(f'{prompt.where}template may only hold {{argument}} placeholders of its own')
    return {
        **prompt.source,
        'name': name,
        'arguments': [argument.source for argument in arguments],
        'template': template,
        'description': prompt.text('description', name),
    }


def spec_warnings(spec: Spec) -> list[str]:
    length = len(spec['instructions'])
    if length <= INSTRUCTIONS_LIMIT:
        return []
    return [
        (
            f"instructions is {length} characters; Claude Code truncates a server's instructions "
            f'at {INSTRUCTIONS_LIMIT}, so keep the text short and put the critical details first'
        )
    ]
