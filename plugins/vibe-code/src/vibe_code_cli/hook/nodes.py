from dataclasses import dataclass
from typing import get_args

import msgspec
from msgspec import UnsetType

from vibe_code_cli.findings import Finding, error, warning
from vibe_code_cli.hook.schema import EventName, HookHandler, MatcherGroup
from vibe_code_cli.jsondoc import JsonObject


@dataclass(frozen=True)
class SchemaFinding:
    """A finding of the schema pass and the location it names, as the built-in writes it."""

    where: str
    finding: Finding


@dataclass(frozen=True)
class Handler:
    event: str
    where: str
    hook: HookHandler


@dataclass(frozen=True)
class Group:
    event: str
    where: str
    matcher: str | UnsetType
    handlers: tuple[Handler, ...]


@dataclass(frozen=True)
class Event:
    name: str
    empty: bool
    groups: tuple[Group, ...]


@dataclass(frozen=True)
class DecodedHooks:
    """What the schema pass made of a file's `hooks` value.

    `events` is None when the file has no `hooks` object to read.
    """

    events: tuple[Event, ...] | None
    findings: tuple[SchemaFinding, ...]


def decode_hooks(config: JsonObject | None) -> DecodedHooks:
    """The schema pass. Malformed JSON and a missing `hooks` key are the built-in's to report."""
    if config is None or 'hooks' not in config:
        return DecodedHooks(None, ())
    try:
        entries_by_event = msgspec.convert(config['hooks'], dict[str, object])
    except msgspec.ValidationError as problem:
        return DecodedHooks(None, (schema_finding('hooks', problem),))
    events = []
    findings = []
    for name, entries in entries_by_event.items():
        event, event_findings = decode_event(name, entries)
        events.append(event)
        findings.extend(event_findings)
    return DecodedHooks(tuple(events), tuple(findings))


def schema_finding(where: str, problem: msgspec.ValidationError) -> SchemaFinding:
    return SchemaFinding(where, error(f'{where}: {problem}'))


def decode_event(name: str, entries: object) -> tuple[Event, list[SchemaFinding]]:
    where = f'hooks.{name}'
    findings = event_name_findings(name, where)
    try:
        raw_groups = msgspec.convert(entries, list[object])
    except msgspec.ValidationError as problem:
        return Event(name, empty=False, groups=()), [*findings, schema_finding(where, problem)]
    groups = []
    for index, raw_group in enumerate(raw_groups):
        group, group_findings = decode_group(name, f'{where}.{index}', raw_group)
        findings.extend(group_findings)
        if group is not None:
            groups.append(group)
    return Event(name, empty=not raw_groups, groups=tuple(groups)), findings


def event_name_findings(name: str, where: str) -> list[SchemaFinding]:
    """Row CH-A24, and the warning the built-in also gives for an event that does not exist."""
    try:
        msgspec.convert(name, EventName)
    except msgspec.ValidationError as problem:
        pascal_case = name[:1].upper() + name[1:]
        if pascal_case in get_args(EventName):
            message = f'{where}: event names are PascalCase; spell it {pascal_case}'
            return [SchemaFinding(where, error(message))]
        return [SchemaFinding(where, warning(f'{where}: {problem}'))]
    return []


def decode_group(
    event: str, where: str, raw_group: object
) -> tuple[Group | None, list[SchemaFinding]]:
    try:
        group = msgspec.convert(raw_group, MatcherGroup)
    except msgspec.ValidationError as problem:
        return None, [schema_finding(where, problem)]
    handlers = []
    findings = []
    for index, raw_handler in enumerate(group.hooks):
        handler_where = f'{where}.hooks.{index}'
        try:
            hook = msgspec.convert(raw_handler, HookHandler)
        except msgspec.ValidationError as problem:
            findings.append(schema_finding(handler_where, problem))
            continue
        handlers.append(Handler(event, handler_where, hook))
    return Group(event, where, group.matcher, tuple(handlers)), findings
