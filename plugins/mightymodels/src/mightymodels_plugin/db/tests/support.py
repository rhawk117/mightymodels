from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum, auto
from pathlib import Path

import pytest
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session, SessionTransaction

from mightymodels_plugin.database import open_database
from mightymodels_plugin.db.checkout import Checkouts
from mightymodels_plugin.workspace import workspace_at


class ActivityKind(StrEnum):
    TRANSACTION_OPENED = auto()
    ENGINE_DISPOSED = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class DatabaseEvent:
    kind: ActivityKind
    engine: Engine


@dataclass(slots=True, kw_only=True, frozen=True)
class DatabaseActivity:
    events: list[DatabaseEvent] = field(default_factory=list)

    def record_transaction(self, session: Session, transaction: SessionTransaction) -> None:
        if transaction.parent is not None:
            return
        engine = session.get_bind().engine
        self.events.append(DatabaseEvent(kind=ActivityKind.TRANSACTION_OPENED, engine=engine))

    def record_disposal(self, engine: Engine) -> None:
        self.events.append(DatabaseEvent(kind=ActivityKind.ENGINE_DISPOSED, engine=engine))

    def kinds(self) -> list[ActivityKind]:
        return [recorded.kind for recorded in self.events]

    def engines(self) -> set[Engine]:
        return {recorded.engine for recorded in self.events}


@contextmanager
def checkouts_at(root: Path) -> Generator[Checkouts]:
    workspace = workspace_at(root)
    workspace.exclude_state_from_git()
    with open_database(workspace.database_file()) as database:
        yield Checkouts(workspace=workspace, database=database)


@pytest.fixture
def checkouts(repository: Path) -> Generator[Checkouts]:
    with checkouts_at(repository) as opened:
        yield opened


@pytest.fixture
def database_activity() -> Generator[DatabaseActivity]:
    activity = DatabaseActivity()
    event.listen(Session, 'after_transaction_create', activity.record_transaction)
    event.listen(Engine, 'engine_disposed', activity.record_disposal)
    yield activity
    event.remove(Session, 'after_transaction_create', activity.record_transaction)
    event.remove(Engine, 'engine_disposed', activity.record_disposal)
