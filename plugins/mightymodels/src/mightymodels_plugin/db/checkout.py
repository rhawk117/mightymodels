"""One unit of work against a repository: its root for files and git, and an open transaction."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from mightymodels_plugin.database import Database


@dataclass(slots=True, kw_only=True, frozen=True)
class Checkout:
    root: Path
    session: Session


@dataclass(slots=True, kw_only=True, frozen=True)
class Checkouts:
    root: Path
    database: Database

    @contextmanager
    def begin(self) -> Generator[Checkout]:
        with self.database.transaction() as session:
            yield Checkout(root=self.root, session=session)
