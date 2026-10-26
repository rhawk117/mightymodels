"""The twelve workers of the plugin and the agent type each one is dispatched under.

A worker's type is `mightymodels:<folder>:<name>`, the folder being the one its agent file is in.
A target is a worker under its type or under its bare name.
"""

from enum import StrEnum, auto
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

PLUGIN_PREFIX = 'mightymodels:'


class Worker(StrEnum):
    CODE_SCOUT = 'code-scout'
    WEB_SCOUT = 'web-scout'
    QUALITYLENS = 'qualitylens'
    FACT_CHECKER = 'fact-checker'
    ENGINEER = 'engineer'
    ARCHITECT = 'architect'
    INTERN = 'intern'
    GITTY_UP = 'gitty-up'
    WINGMAN = 'wingman'
    TERRY_TOOLCHAIN = 'terry-toolchain'
    MERGE_VADER = 'merge-vader'
    UNCLE_BOB = 'uncle-bob'


class Folder(StrEnum):
    REVIEW = auto()
    WORKERS = auto()
    TRIAGE = auto()


FOLDERS: Mapping[Worker, Folder] = MappingProxyType({
    Worker.CODE_SCOUT: Folder.TRIAGE,
    Worker.WEB_SCOUT: Folder.TRIAGE,
    Worker.QUALITYLENS: Folder.REVIEW,
    Worker.FACT_CHECKER: Folder.REVIEW,
    Worker.ENGINEER: Folder.WORKERS,
    Worker.ARCHITECT: Folder.WORKERS,
    Worker.INTERN: Folder.WORKERS,
    Worker.GITTY_UP: Folder.WORKERS,
    Worker.WINGMAN: Folder.TRIAGE,
    Worker.TERRY_TOOLCHAIN: Folder.TRIAGE,
    Worker.MERGE_VADER: Folder.REVIEW,
    Worker.UNCLE_BOB: Folder.REVIEW,
})


def agent_type(worker: Worker) -> str:
    return f'{PLUGIN_PREFIX}{FOLDERS[worker]}:{worker}'


def worker_named(name: str) -> Worker | None:
    return next((worker for worker in Worker if name in {worker, agent_type(worker)}), None)
