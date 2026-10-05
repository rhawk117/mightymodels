"""One unit of work: the workspace for contained paths and git, and an open transaction."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from mightymodels_plugin.database import Database
from mightymodels_plugin.workspace import Workspace


@dataclass(slots=True, kw_only=True, frozen=True)
class Checkout:
    workspace: Workspace
    session: Session


@dataclass(slots=True, kw_only=True, frozen=True)
class Checkouts:
    workspace: Workspace
    database: Database

    @contextmanager
    def begin(self) -> Generator[Checkout]:
        with self.database.transaction() as session:
            yield Checkout(workspace=self.workspace, session=session)
