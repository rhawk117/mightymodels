"""The one routing table: which model alias each worker runs on at each ticket scope."""

from collections.abc import Mapping
from enum import StrEnum, auto
from types import MappingProxyType


class Model(StrEnum):
    HAIKU = auto()
    SONNET = auto()
    OPUS = auto()
    FABLE = auto()


class Scope(StrEnum):
    SM = auto()
    MED = auto()
    LARGE = auto()


class Worker(StrEnum):
    CODE_SCOUT = 'code-scout'
    WEB_SCOUT = 'web-scout'
    QUALITYLENS = 'qualitylens'
    ENGINEER = 'engineer'
    ARCHITECT = 'architect'
    GITTY_UP = 'gitty-up'
    WINGMAN = 'wingman'
    MERGE_VADER_REVIEWER = 'merge-vader-reviewer'
    UNCLE_BOB_REVIEWER = 'uncle-bob-reviewer'


type ScopeRouting = Mapping[Scope, Model]


def at_every_scope(model: Model) -> ScopeRouting:
    return MappingProxyType(dict.fromkeys(Scope, model))


ROUTING: Mapping[Worker, ScopeRouting] = MappingProxyType(
    {
        Worker.CODE_SCOUT: at_every_scope(Model.HAIKU),
        Worker.WEB_SCOUT: at_every_scope(Model.HAIKU),
        Worker.QUALITYLENS: at_every_scope(Model.HAIKU),
        Worker.ENGINEER: at_every_scope(Model.SONNET),
        Worker.ARCHITECT: MappingProxyType(
            {Scope.SM: Model.SONNET, Scope.MED: Model.SONNET, Scope.LARGE: Model.OPUS}
        ),
        Worker.GITTY_UP: at_every_scope(Model.HAIKU),
        Worker.WINGMAN: at_every_scope(Model.OPUS),
        Worker.MERGE_VADER_REVIEWER: at_every_scope(Model.OPUS),
        Worker.UNCLE_BOB_REVIEWER: at_every_scope(Model.SONNET),
    }
)


def models_at(scope: Scope) -> dict[Worker, Model]:
    return {worker: by_scope[scope] for worker, by_scope in ROUTING.items()}
