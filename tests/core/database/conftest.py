"""Shared declarations and a tiny fixture database for the database adapter tests."""

import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, override

import pytest
from mightymodels_core.database import (
    Command,
    ConnectionOptions,
    DatabaseSpec,
    Query,
    open_database,
)
from msgspec import Struct

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database, Declaration

FIXTURE_VERSION = 7

FIXTURE_SCHEMA = f"""
CREATE TABLE teams (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
) STRICT;
CREATE TABLE people (
  id INTEGER PRIMARY KEY,
  team_id INTEGER REFERENCES teams (id),
  name TEXT NOT NULL UNIQUE,
  age INTEGER NOT NULL DEFAULT 0 CHECK (age >= 0)
) STRICT;
PRAGMA user_version = {FIXTURE_VERSION};
"""

FIXTURE_STATEMENTS = """
-- name: add_team
INSERT INTO teams (name) VALUES (:name);

-- name: add_person
INSERT INTO people (name, age, team_id) VALUES (:name, :age, :team_id);

-- name: add_nameless_person
INSERT INTO people (name) VALUES (NULL);

-- name: add_person_with_text_age
INSERT INTO people (name, age) VALUES ('ada', 'old');

-- name: find_person
SELECT json_object('name', name, 'age', age) FROM people WHERE name = :name;

-- name: all_people
SELECT json_object('name', name, 'age', age) FROM people ORDER BY id;

-- name: delete_from_missing_table
DELETE FROM missing_table;

-- name: foreign_keys
SELECT json_object('value', foreign_keys) FROM pragma_foreign_keys;

-- name: journal_mode
SELECT json_object('value', journal_mode) FROM pragma_journal_mode;

-- name: user_version
SELECT json_object('value', user_version) FROM pragma_user_version;
"""


class NamePart(Struct, frozen=True, kw_only=True):
    name: str


class NameRow(Struct, frozen=True, kw_only=True):
    name: str


class PersonPart(Struct, frozen=True, kw_only=True):
    name: str
    age: int = 0
    team_id: int | None = None


class PersonRow(Struct, frozen=True, kw_only=True):
    name: str
    age: int


class NoPart(Struct, frozen=True, kw_only=True):
    pass


class NumberRow(Struct, frozen=True, kw_only=True):
    value: int


class TextRow(Struct, frozen=True, kw_only=True):
    value: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Statements:
    add_team: Command[NamePart]
    add_person: Command[PersonPart]
    add_nameless_person: Command[NoPart]
    add_person_with_text_age: Command[NoPart]
    delete_from_missing_table: Command[NoPart]
    find_person: Query[NamePart, PersonRow]
    all_people: Query[NoPart, PersonRow]
    foreign_keys: Query[NoPart, NumberRow]
    journal_mode: Query[NoPart, TextRow]
    user_version: Query[NoPart, NumberRow]

    @property
    def declarations(self) -> tuple[Declaration, ...]:
        return (
            self.add_team,
            self.add_person,
            self.add_nameless_person,
            self.add_person_with_text_age,
            self.delete_from_missing_table,
            self.find_person,
            self.all_people,
            self.foreign_keys,
            self.journal_mode,
            self.user_version,
        )


def create_statements() -> Statements:
    return Statements(
        add_team=Command(name='add_team', params=NamePart),
        add_person=Command(name='add_person', params=PersonPart),
        add_nameless_person=Command(name='add_nameless_person', params=NoPart),
        add_person_with_text_age=Command(name='add_person_with_text_age', params=NoPart),
        delete_from_missing_table=Command(name='delete_from_missing_table', params=NoPart),
        find_person=Query(name='find_person', params=NamePart, row=PersonRow),
        all_people=Query(name='all_people', params=NoPart, row=PersonRow),
        foreign_keys=Query(name='foreign_keys', params=NoPart, row=NumberRow),
        journal_mode=Query(name='journal_mode', params=NoPart, row=TextRow),
        user_version=Query(name='user_version', params=NoPart, row=NumberRow),
    )


class RollbackFailingConnection(sqlite3.Connection):
    @override
    def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
        cursor = super().execute(sql, parameters)
        if sql == 'ROLLBACK':
            message = 'injected rollback failure'
            raise sqlite3.OperationalError(message)

        return cursor


class CloseFailingConnection(sqlite3.Connection):
    @override
    def close(self) -> None:
        message = 'injected close failure'
        raise sqlite3.OperationalError(message)


@pytest.fixture
def find_name() -> Query[NamePart, NameRow]:
    return Query(name='find_name', params=NamePart, row=NameRow)


@pytest.fixture
def rename() -> Command[NamePart]:
    return Command(name='rename', params=NamePart)


@pytest.fixture
def statements() -> Statements:
    return create_statements()


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path.joinpath('fixture.db')


@pytest.fixture
def database_spec(tmp_path: Path, statements: Statements) -> DatabaseSpec:
    schema = tmp_path.joinpath('schema.sql')
    schema.write_text(FIXTURE_SCHEMA, encoding='utf-8')
    statement_file = tmp_path.joinpath('statements.sql')
    statement_file.write_text(FIXTURE_STATEMENTS, encoding='utf-8')
    return DatabaseSpec(
        schema=schema,
        statements=statement_file,
        declarations=statements.declarations,
    )


@pytest.fixture
def database(database_path: Path, database_spec: DatabaseSpec) -> Generator[Database]:
    opened = open_database(database_path, database_spec, ConnectionOptions())
    yield opened
    opened.close()
