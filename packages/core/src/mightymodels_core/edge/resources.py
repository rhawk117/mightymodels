"""What both edges do first: find the repository, name it, and open the database for it.

The server's lifespan and `verify run` start in whatever directory the session did. `open_state`
takes that directory and the plugin data directory the edge read from its environment, and hands
out, for the length of an `async with` block, the checkout at the git toplevel, the git that
answers there and the database opened beside the data directory's other files. The block's exit
closes the database. So the two edges of one session open the same file.

Every refusal comes before anything is created: no data directory, no git executable, no work
tree. A database file of another schema version is refused when it is opened, before
`.mightymodels/` is excluded from git. Each is a `StateError` naming what is missing.
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.resources import files
from typing import TYPE_CHECKING

from mightymodels_core.database import DatabaseSpec, open_database
from mightymodels_core.git import Checkout, create_git
from mightymodels_core.primitives import SystemClock
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.workspace import exclude_state

from .errors import DataDirectoryMissingError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from mightymodels_core.database import Database
    from mightymodels_core.git import Git
    from mightymodels_core.primitives import Clock

    from .data_directory import DataDirectory

DATABASE_NAME = 'mightymodels.db'


@dataclass(slots=True, kw_only=True, frozen=True)
class OpenState:
    checkout: Checkout
    git: Git
    database: Database


def create_database_spec() -> DatabaseSpec:
    sql = files('mightymodels_core.sql')
    return DatabaseSpec(
        schema=sql.joinpath('schema.sql'),
        statements=sql.joinpath('statements.sql'),
        declarations=DECLARATIONS,
    )


def create_clock() -> Clock:
    return SystemClock()


async def exclude_state_from_git(git: Git) -> None:
    common_directory = await git.common_directory()
    if common_directory is None:
        return

    exclude_state(common_directory)


@asynccontextmanager
async def open_state(data_directory: DataDirectory, start: Path) -> AsyncGenerator[OpenState]:
    if isinstance(data_directory, DataDirectoryMissingError):
        raise data_directory

    checkout = await create_git(start).checkout()
    if not isinstance(checkout, Checkout):
        raise checkout

    git = create_git(checkout.toplevel)
    data_directory.mkdir(parents=True, exist_ok=True)
    database = open_database(data_directory.joinpath(DATABASE_NAME), create_database_spec())
    try:
        await exclude_state_from_git(git)
        yield OpenState(checkout=checkout, git=git, database=database)
    finally:
        database.close()
