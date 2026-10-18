from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import (
    DuplicateBlockError,
    DuplicateDeclarationError,
    EmptyBlockError,
    MissingBlockError,
    UndeclaredBlockError,
    bind_catalogue,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Command, DatabaseError, Query

    from .conftest import NamePart, NameRow

pytestmark = pytest.mark.integration

BOTH_BLOCKS = """
-- A preamble comment before any block is ignored.
-- name: find_name
SELECT json_object('name', name) AS row FROM people WHERE name = :name;

-- name: rename
-- Comments inside a block belong to it.
UPDATE people SET name = :name;
"""


@dataclass(slots=True, kw_only=True, frozen=True)
class RejectedCatalogue:
    name: str
    text: str
    error_type: type[DatabaseError]
    offending_name: str
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


def rejected_catalogue_cases() -> pytest.MarkDecorator:
    duplicate = RejectedCatalogue(
        name='duplicate-block',
        text=BOTH_BLOCKS + '\n-- name: rename\nDELETE FROM people;\n',
        error_type=DuplicateBlockError,
        offending_name='rename',
    )
    empty = RejectedCatalogue(
        name='empty-block',
        text='-- name: find_name\nSELECT 1;\n-- name: rename\n',
        error_type=EmptyBlockError,
        offending_name='rename',
    )
    comment_only = RejectedCatalogue(
        name='comment-only-block',
        text='-- name: find_name\n-- nothing here\n-- name: rename\nSELECT 1;\n',
        error_type=EmptyBlockError,
        offending_name='find_name',
    )
    missing = RejectedCatalogue(
        name='declared-without-block',
        text=BOTH_BLOCKS.split('-- name: rename', maxsplit=1)[0],
        error_type=MissingBlockError,
        offending_name='rename',
    )
    undeclared = RejectedCatalogue(
        name='block-without-declaration',
        text=BOTH_BLOCKS + '\n-- name: purge\nDELETE FROM people;\n',
        error_type=UndeclaredBlockError,
        offending_name='purge',
    )
    cases = [duplicate, empty, comment_only, missing, undeclared]
    return pytest.mark.parametrize('rejected', [case.param for case in cases])


class TestBindCatalogue:
    def test_each_declaration_gets_the_sql_of_its_block(
        self, find_name: Query[NamePart, NameRow], rename: Command[NamePart]
    ) -> None:
        catalogue = bind_catalogue(BOTH_BLOCKS, [find_name, rename])

        assert catalogue.sql_for(find_name).startswith('SELECT json_object')
        assert catalogue.sql_for(find_name).endswith('name = :name;')
        assert catalogue.sql_for(rename).startswith('-- Comments inside a block')
        assert catalogue.sql_for(rename).endswith('SET name = :name;')

    @rejected_catalogue_cases()
    def test_a_malformed_catalogue_raises_its_own_error(
        self,
        rejected: RejectedCatalogue,
        find_name: Query[NamePart, NameRow],
        rename: Command[NamePart],
    ) -> None:
        with pytest.raises(rejected.error_type) as raised:
            bind_catalogue(rejected.text, [find_name, rename])

        assert type(raised.value) is rejected.error_type
        assert repr(rejected.offending_name) in str(raised.value)

    def test_a_name_declared_twice_is_rejected(self, rename: Command[NamePart]) -> None:
        with pytest.raises(DuplicateDeclarationError):
            bind_catalogue(BOTH_BLOCKS, [rename, rename])
