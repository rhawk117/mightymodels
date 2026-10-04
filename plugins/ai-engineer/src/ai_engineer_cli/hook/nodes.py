from collections.abc import Iterator
from dataclasses import dataclass

from ai_engineer_cli.jsondoc import JsonObject, as_object


@dataclass(frozen=True)
class Group:
    """A matcher group: the object in an event's array that holds `matcher` and `hooks`."""

    event: str
    where: str
    fields: JsonObject


@dataclass(frozen=True)
class Handler:
    group: Group
    where: str
    fields: JsonObject

    @property
    def event(self) -> str:
        return self.group.event


def iter_groups(hooks: JsonObject) -> Iterator[Group]:
    """The matcher groups of a hooks object; malformed parts are the built-in's to report."""
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if (fields := as_object(entry)) is not None:
                yield Group(event, f'hooks.{event}.{index}', fields)


def iter_handlers(group: Group) -> Iterator[Handler]:
    handlers = group.fields.get('hooks')
    if not isinstance(handlers, list):
        return
    for index, handler in enumerate(handlers):
        if (fields := as_object(handler)) is not None:
            yield Handler(group, f'{group.where}.hooks.{index}', fields)
