"""The state database under `.mightymodels/`: one engine and one session factory per owner.

Whoever opens it holds it for as long as it runs, the server for its lifespan and `verify run`
for its one command, and the engine is disposed when that owner lets go. The owner's workspace
says where the file is. Deleting the file resets the state.

`open_database` is the only way to a `Database`, and it creates the table of every row type in
`ROW_TYPES` by name, whatever else the owner has imported. So no owner opens a database with a
table missing, and a domain's `tables.py` adds a table only by adding its row type here.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from mightymodels_plugin.db.tables import (
    AttemptRow,
    ReviewDispositionRow,
    ReviewFindingRow,
    ReviewOutcomeRow,
    ReviewRunRow,
    TaskRow,
    TransitionRow,
)
from mightymodels_plugin.declarative import Base
from mightymodels_plugin.tools.contract.tables import CommandRow, ReceiptRow
from mightymodels_plugin.tools.ticket.tables import TicketRow

ROW_TYPES: tuple[type[Base], ...] = (
    TicketRow,
    TaskRow,
    AttemptRow,
    TransitionRow,
    CommandRow,
    ReceiptRow,
    ReviewRunRow,
    ReviewFindingRow,
    ReviewDispositionRow,
    ReviewOutcomeRow,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class Database:
    engine: Engine
    sessions: sessionmaker[Session]

    @contextmanager
    def transaction(self) -> Generator[Session]:
        with self.sessions.begin() as session:
            yield session


@contextmanager
def open_database(database_file: Path) -> Generator[Database]:
    database_file.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create('sqlite', database=str(database_file)))
    tables = [Base.metadata.tables[row_type.__tablename__] for row_type in ROW_TYPES]
    try:
        Base.metadata.create_all(engine, tables=tables)
        yield Database(engine=engine, sessions=sessionmaker(engine))
    finally:
        engine.dispose()
