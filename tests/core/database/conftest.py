"""Shared declarations for the database adapter tests."""

import pytest
from mightymodels_core.database import Command, Query
from msgspec import Struct


class NamePart(Struct, frozen=True, kw_only=True):
    name: str


class NameRow(Struct, frozen=True, kw_only=True):
    name: str


@pytest.fixture
def find_name() -> Query[NamePart, NameRow]:
    return Query(name='find_name', params=NamePart, row=NameRow)


@pytest.fixture
def rename() -> Command[NamePart]:
    return Command(name='rename', params=NamePart)
