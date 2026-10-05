"""One unit of work against a repository: its root for files and git, and an open transaction."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from mightymodels_plugin.db.repository import open_repository


@dataclass(slots=True, kw_only=True, frozen=True)
class Checkout:
    root: Path
    session: Session


@contextmanager
def open_checkout(root: Path) -> Generator[Checkout]:
    engine = open_repository(root)
    try:
        with Session(engine) as session, session.begin():
            yield Checkout(root=root, session=session)
    finally:
        engine.dispose()
