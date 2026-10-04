import keyword
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, NoReturn

import msgspec
from msgspec import UNSET, UnsetType

from vibe_code_cli.findings import CannotCheckError
from vibe_code_cli.jsondoc import JsonObject, as_object

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
# C0 controls other than tab, newline and carriage return, and U+007F, would reach generated
# source, TOML and docstrings; msgspec rejects a lone surrogate while it reads the JSON.
CONTROL_FREE = r'\A[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]*\Z'
Text = Annotated[str, msgspec.Meta(pattern=CONTROL_FREE)]
NonEmptyText = Annotated[str, msgspec.Meta(pattern=CONTROL_FREE, min_length=1)]
ResultSize = Annotated[int, msgspec.Meta(gt=0, le=MAX_RESULT_CHARS)]


class ParameterEntry(msgspec.Struct):
    """A tool input or output as the spec file writes it; an unset key takes a default."""

    name: str = ''
    type: str = 'str'
    description: Text | UnsetType = UNSET
    required: bool = True
    default: object = UNSET


class ToolEntry(msgspec.Struct):
    name: str = ''
    description: Text | UnsetType = UNSET
    binary: Text = ''
    arguments: list[NonEmptyText] = []
    side_effects: str = 'read_only'
    confirm: bool = False
    inputs: list[ParameterEntry] = []
    outputs: list[ParameterEntry] = []
    max_result_chars: ResultSize | UnsetType = UNSET


class ResourceEntry(msgspec.Struct):
    uri: Text = ''
    name: str | UnsetType = UNSET
    description: Text | UnsetType = UNSET
    mime_type: Text = 'text/plain'


class ArgumentEntry(msgspec.Struct):
    name: str = ''


class PromptEntry(msgspec.Struct):
    name: str = ''
    arguments: list[ArgumentEntry] = []
    template: Text | UnsetType = UNSET
    description: Text | UnsetType = UNSET


class SpecEntry(msgspec.Struct):
    """The interview spec as the file writes it; keys it does not list are kept in the record."""

    name: str = ''
    package: str | UnsetType = UNSET
    description: Text | UnsetType = UNSET
    instructions: Text | UnsetType = UNSET
    reach: str = 'local'
    root_source: str = 'cwd'
    always_load: bool = False
    binaries: list[NonEmptyText] = []
    resources: list[ResourceEntry] = []
    prompts: list[PromptEntry] = []
    tools: list[ToolEntry] = []


class Parameter(msgspec.Struct, frozen=True):
    name: str
    type: str
    description: str
    required: bool
    default: object = UNSET


class Tool(msgspec.Struct, frozen=True):
    name: str
    description: str
    binary: str
    arguments: list[str]
    side_effects: str
    confirm: bool
    inputs: list[Parameter]
    outputs: list[Parameter]
    max_result_chars: int | UnsetType = UNSET


class Resource(msgspec.Struct, frozen=True):
    uri: str
    name: str
    description: str
    mime_type: str


class Argument(msgspec.Struct, frozen=True):
    name: str


class Prompt(msgspec.Struct, frozen=True):
    name: str
    arguments: list[Argument]
    template: str
    description: str


class Spec(msgspec.Struct, frozen=True):
    """The spec with every default filled in and every choice checked; render reads this."""

    name: str
    package: str
    description: str
    instructions: str
    reach: str
    root_source: str
    always_load: bool
    binaries: list[str]
    resources: list[Resource]
    prompts: list[Prompt]
    tools: list[Tool]


@dataclass(frozen=True)
class LoadedSpec:
    spec: Spec
    record: JsonObject


ROOT_PARAMETER = Parameter(
    name='root',
    type='str',
    description=(
        'Absolute path of the repository the session is working in; '
        'pass the current working directory.'
    ),
    required=True,
)
DEFAULT_OUTPUT = Parameter(
    name='summary',
    type='str',
    description='What happened, for the model to read.',
    required=True,
)


def reject(message: str) -> NoReturn:
    raise CannotCheckError(message)


def is_identifier(text: str) -> bool:
    return (
        IDENTIFIER.fullmatch(text) is not None
        and len(text) <= MAX_NAME_LENGTH
        and not keyword.iskeyword(text)
    )


def given[T](value: T | UnsetType, fallback: T) -> T:
    return fallback if isinstance(value, UnsetType) else value


def choice(label: str, value: str, choices: tuple[str, ...]) -> str:
    if value not in choices:
        reject(f'{label} must be one of {", ".join(choices)}')
    return value


def identifier(label: str, value: str) -> str:
    if not is_identifier(value):
        reject(f'{label} must be a lowercase snake_case Python identifier')
    return value


def load_spec(path: Path) -> LoadedSpec:
    """Read and normalize a spec file; raise CannotCheckError for anything it rejects."""
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as problem:
        reject(f'cannot read the spec {path}: {type(problem).__name__}')
    try:
        written = msgspec.json.decode(text)
    except msgspec.DecodeError as problem:
        reject(f'{path} is not valid JSON: {problem}')
    try:
        entry = msgspec.convert(written, SpecEntry)
    except msgspec.ValidationError as problem:
        reject(str(problem))
    spec = normalize_spec(entry)
    return LoadedSpec(spec, record_of(written, spec))


def normalize_spec(entry: SpecEntry) -> Spec:
    name = entry.name
    if NAME_PATTERN.fullmatch(name) is None or len(name) > MAX_NAME_LENGTH:
        reject(f'name must be kebab-case, at most {MAX_NAME_LENGTH} characters')
    description = given(entry.description, f'{name} MCP server')
    if not entry.tools:
        reject('at least one tool is required')
    root_source = choice('root_source', entry.root_source, ROOT_SOURCES)
    return Spec(
        name=name,
        package=identifier('package', given(entry.package, name.replace('-', '_'))),
        description=description,
        instructions=given(entry.instructions, description),
        reach=choice('reach', entry.reach, REACHES),
        root_source=root_source,
        always_load=entry.always_load,
        binaries=entry.binaries,
        resources=[
            normalize_resource(item, f'resources[{index}].')
            for index, item in enumerate(entry.resources)
        ],
        prompts=[
            normalize_prompt(item, f'prompts[{index}].') for index, item in enumerate(entry.prompts)
        ],
        tools=[
            normalize_tool(root_source, item, f'tools[{index}].')
            for index, item in enumerate(entry.tools)
        ],
    )


def normalize_tool(root_source: str, entry: ToolEntry, where: str) -> Tool:
    name = identifier(f'{where}name', entry.name)
    inputs = [
        normalize_parameter(item, f'{where}inputs[{index}].', is_input=True)
        for index, item in enumerate(entry.inputs)
    ]
    if root_source == 'parameter' and all(item.name != 'root' for item in inputs):
        inputs = [ROOT_PARAMETER, *inputs]
    outputs = [
        normalize_parameter(item, f'{where}outputs[{index}].', is_input=False)
        for index, item in enumerate(entry.outputs)
    ] or [DEFAULT_OUTPUT]
    return Tool(
        name=name,
        description=given(entry.description, name.replace('_', ' ')),
        binary=entry.binary,
        arguments=entry.arguments,
        side_effects=choice(f'{where}side_effects', entry.side_effects, SIDE_EFFECTS),
        confirm=entry.confirm,
        inputs=inputs,
        outputs=outputs,
        max_result_chars=entry.max_result_chars,
    )


def normalize_parameter(entry: ParameterEntry, where: str, *, is_input: bool) -> Parameter:
    if is_input and PROPERTY_NAME.fullmatch(entry.name) is None:
        reject(f'{where}name must be 1 to 64 characters of letters, digits, _, . and -')
    name = identifier(f'{where}name', entry.name)
    return Parameter(
        name=name,
        type=choice(f'{where}type', entry.type, PYTHON_TYPES),
        description=given(entry.description, name.replace('_', ' ')),
        required=entry.required,
        default=entry.default,
    )


def normalize_resource(entry: ResourceEntry, where: str) -> Resource:
    uri = entry.uri
    leftover = PLACEHOLDER.sub('', uri)
    if not uri or '{' in leftover or '}' in leftover:
        reject(f'{where}uri must be non-empty with placeholders of the form {{name}}')
    if not all(is_identifier(item) for item in PLACEHOLDER.findall(uri)):
        reject(f'{where}uri placeholders must be snake_case Python identifiers')
    name = identifier(
        f'{where}name', given(entry.name, re.sub(r'\W+', '_', uri).strip('_').lower())
    )
    return Resource(
        uri=uri,
        name=name,
        description=given(entry.description, name),
        mime_type=entry.mime_type,
    )


def normalize_prompt(entry: PromptEntry, where: str) -> Prompt:
    name = identifier(f'{where}name', entry.name)
    names = [
        identifier(f'{where}arguments[{index}].name', argument.name)
        for index, argument in enumerate(entry.arguments)
    ]
    template = given(entry.template, f'{name}: ' + ' '.join(f'{{{item}}}' for item in names))
    leftover = PLACEHOLDER.sub(lambda match: '' if match[1] in names else '{', template)
    if '{' in leftover or '}' in leftover:
        reject(f'{where}template may only hold {{argument}} placeholders of its own')
    return Prompt(
        name=name,
        arguments=[Argument(item) for item in names],
        template=template,
        description=given(entry.description, name),
    )


def record_of(written: object, resolved: msgspec.Struct) -> JsonObject:
    """The spec as written with the resolved values in place and each default added after it.

    This is the `mcp-spec.json` interview record: keys the spec does not list stay, in the order
    the file wrote them.
    """
    record = as_object(written) or {}
    for field in msgspec.structs.fields(resolved):
        value = getattr(resolved, field.name)
        if not isinstance(value, UnsetType):
            record[field.name] = merged_value(record.get(field.name), value)
    return record


def merged_value(written: object, value: object) -> object:
    structs = (
        [item for item in value if isinstance(item, msgspec.Struct)]
        if isinstance(value, list)
        else []
    )
    if not structs:
        return msgspec.to_builtins(value)
    # A resolved list may lead with items the file did not write, such as the root input.
    written_items = written if isinstance(written, list) else []
    unwritten = len(structs) - len(written_items)
    return [
        *msgspec.to_builtins(structs[:unwritten]),
        *(
            record_of(item, resolved)
            for item, resolved in zip(written_items, structs[unwritten:], strict=True)
        ),
    ]


def spec_warnings(spec: Spec) -> list[str]:
    length = len(spec.instructions)
    if length <= INSTRUCTIONS_LIMIT:
        return []
    return [
        (
            f"instructions is {length} characters; Claude Code truncates a server's instructions "
            f'at {INSTRUCTIONS_LIMIT}, so keep the text short and put the critical details first'
        )
    ]
