"""The state database under `.mightymodels/`: one engine and one session factory per owner.

Whoever opens it holds it for as long as it runs, the server for its lifespan and `verify run`
for its one command, and the engine is disposed when that owner lets go.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from mightymodels_plugin.db.repository import STATE_DIRECTORY
from mightymodels_plugin.db.tables import Base

DATABASE_NAME = 'mightymodels.db'


@dataclass(slots=True, kw_only=True, frozen=True)
class Database:
    engine: Engine
    sessions: sessionmaker[Session]

    @contextmanager
    def transaction(self) -> Generator[Session]:
        with self.sessions.begin() as session:
            yield session


@contextmanager
def open_database(root: Path) -> Generator[Database]:
    database_file = root.joinpath(STATE_DIRECTORY, DATABASE_NAME)
    database_file.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create('sqlite', database=str(database_file)))
    try:
        Base.metadata.create_all(engine)
        yield Database(engine=engine, sessions=sessionmaker(engine))
    finally:
        engine.dispose()
