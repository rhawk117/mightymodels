import msgspec
from msgspec import UNSET, UnsetType

from vibe_code_cli.jsondoc import as_object
from vibe_code_cli.plugin.kinds import Kinds

PLUGIN_KINDS = ('ecosystem', 'domain', 'workflow', 'integration')
AUDIENCE_HOW = ('solo', 'team', 'org', 'public')
CHANNELS = ('marketplace', 'local')
STATUSES = ('planned', 'built')
DECISIONS = ('as planned', 'switched')


class Author(msgspec.Struct, frozen=True, kw_only=True):
    name: str = ''
    email: str | UnsetType = UNSET
    url: str | UnsetType = UNSET


class Audience(msgspec.Struct, frozen=True, kw_only=True):
    who: str = ''
    how: str = ''


class Distribution(msgspec.Struct, frozen=True, kw_only=True):
    channel: str = ''
    install: str | UnsetType = UNSET


class Advice(msgspec.Struct, frozen=True, kw_only=True):
    mechanism: str = ''
    reason: str = ''


class Component(msgspec.Struct, frozen=True, kw_only=True):
    kind: str = ''
    name: str = ''
    purpose: str = ''
    status: str = 'planned'
    builder: str | UnsetType | None = UNSET
    answers: dict[str, object] = {}
    facts: list[str] = []
    advice: Advice | None = None
    decision: str = 'as planned'
    files: list[str] = []


class OutsideItem(msgspec.Struct, frozen=True, kw_only=True):
    need: str = ''
    what: str = ''
    mechanism: str = ''
    where: str | UnsetType = UNSET


class UserConfigOption(msgspec.Struct, frozen=True, kw_only=True):
    type: str = ''
    title: str = ''
    description: str = ''
    required: bool | UnsetType = UNSET
    default: str | float | bool | list[str] | UnsetType = UNSET
    options: list[str] | UnsetType = UNSET
    multiple: bool | UnsetType = UNSET
    sensitive: bool | UnsetType = UNSET
    minimum: float | UnsetType = msgspec.field(name='min', default=UNSET)
    maximum: float | UnsetType = msgspec.field(name='max', default=UNSET)


class Dependency(msgspec.Struct, frozen=True, kw_only=True):
    name: str
    marketplace: str | UnsetType = UNSET
    version: str | UnsetType = UNSET


class Plan(msgspec.Struct, frozen=True, kw_only=True):
    name: str = ''
    version: str = '0.1.0'
    description: str = ''
    keywords: list[str] = []
    license: str | None = None
    problem: str = ''
    audience: Audience | None = None
    kinds: list[str] = []
    ecosystem: str = ''
    distribution: Distribution | None = None
    components: list[Component] = []
    open_questions: list[str] = []
    outside_plugin: list[OutsideItem] = []
    author: Author | None = None
    homepage: str | None = None
    repository: str | None = None
    user_config: dict[str, UserConfigOption] = msgspec.field(
        name='userConfig', default_factory=dict
    )
    dependencies: list[str | Dependency] = []


def audience_of(plan: Plan) -> Audience:
    return plan.audience or Audience()


def distribution_of(plan: Plan) -> Distribution:
    return plan.distribution or Distribution()


def decode_plan(document: object) -> Plan:
    return msgspec.convert(document, Plan)


def unknown_keys(document: object) -> list[str]:
    plan = as_object(document)
    if plan is None:
        return []
    found = [f'unknown key {key!r}' for key in plan if key not in field_names(Plan)]
    components = plan.get('components')
    for index, component in enumerate(components if isinstance(components, list) else []):
        entry = as_object(component) or {}
        found.extend(
            f'unknown key {key!r} in components[{index}]'
            for key in entry
            if key not in field_names(Component)
        )
    return found


def field_names(record: type[msgspec.Struct]) -> set[str]:
    return {field.encode_name for field in msgspec.structs.fields(record)}


def normalise(plan: Plan) -> Plan:
    license_name = plan.license.strip() or None if plan.license is not None else None
    return msgspec.structs.replace(
        plan,
        components=[with_builder(component) for component in plan.components],
        license=license_name,
    )


def with_builder(component: Component) -> Component:
    if not isinstance(component.builder, UnsetType):
        return component
    spec = Kinds().specs.get(component.kind)
    return msgspec.structs.replace(component, builder=spec.builder if spec else None)
