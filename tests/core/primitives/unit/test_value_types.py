import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import msgspec
import pytest
from mightymodels_core.primitives import (
    InvalidRepositoryKeyError,
    InvalidRunIdError,
    InvalidSlugError,
    InvalidTaskIdError,
    ReservedSlugError,
    RunIdText,
    SlugText,
    TaskIdText,
    local_key,
    origin_key,
    parse_repository_key,
    parse_run_id,
    parse_slug,
    parse_task_id,
)
from mightymodels_core.primitives.value_types import RepositoryKeyText

if TYPE_CHECKING:
    from collections.abc import Callable

    from _pytest.mark import ParameterSet
    from mightymodels_core.primitives import StateError

LONGEST_KEY = f'{"a" * 69}/{"b" * 70}'


REFUSALS = InvalidSlugError | InvalidRunIdError | InvalidTaskIdError | InvalidRepositoryKeyError
LIMITED_REFUSALS = InvalidSlugError | InvalidTaskIdError | InvalidRepositoryKeyError


@dataclass(slots=True, kw_only=True, frozen=True)
class ValueType:
    name: str
    parse: Callable[[str], object]
    text_type: object
    longest: str
    over_limit: str = ''
    limit: int = 0
    pattern_miss: str
    error_type: type[StateError]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


SLUG = ValueType(
    name='slug',
    parse=parse_slug,
    text_type=SlugText,
    longest='a' * 64,
    over_limit='a' * 65,
    limit=64,
    pattern_miss='-leading-dash',
    error_type=InvalidSlugError,
)
RUN_ID = ValueType(
    name='run-id',
    parse=parse_run_id,
    text_type=RunIdText,
    longest='20260102-030405',
    pattern_miss='2026-01-02',
    error_type=InvalidRunIdError,
)
TASK_ID = ValueType(
    name='task-id',
    parse=parse_task_id,
    text_type=TaskIdText,
    longest='T123456',
    over_limit='T1234567',
    limit=7,
    pattern_miss='X1',
    error_type=InvalidTaskIdError,
)
REPOSITORY_KEY = ValueType(
    name='repository-key',
    parse=parse_repository_key,
    text_type=RepositoryKeyText,
    longest=LONGEST_KEY,
    over_limit=f'{"a" * 70}/{"b" * 70}',
    limit=140,
    pattern_miss='Owner/Name',
    error_type=InvalidRepositoryKeyError,
)


def value_type_cases() -> pytest.MarkDecorator:
    scenarios = (SLUG, RUN_ID, TASK_ID, REPOSITORY_KEY)
    return pytest.mark.parametrize('value_type', [scenario.param for scenario in scenarios])


def limited_value_type_cases() -> pytest.MarkDecorator:
    scenarios = (SLUG, TASK_ID, REPOSITORY_KEY)
    return pytest.mark.parametrize('value_type', [scenario.param for scenario in scenarios])


def decodes(text_type: object, raw: str) -> bool:
    try:
        msgspec.json.decode(msgspec.json.encode(raw), type=text_type)
    except msgspec.ValidationError:
        return False
    return True


class TestValueTypes:
    @value_type_cases()
    def test_longest_valid_value_is_accepted(self, value_type: ValueType) -> None:
        assert value_type.parse(value_type.longest) == value_type.longest
        assert decodes(value_type.text_type, value_type.longest)

    @limited_value_type_cases()
    def test_value_over_the_limit_is_refused(self, value_type: ValueType) -> None:
        refusal = value_type.parse(value_type.over_limit)

        assert isinstance(refusal, value_type.error_type)
        assert isinstance(refusal, LIMITED_REFUSALS)
        assert refusal.raw == value_type.over_limit
        assert refusal.limit == value_type.limit
        assert not decodes(value_type.text_type, value_type.over_limit)

    @value_type_cases()
    def test_value_missing_the_pattern_is_refused(self, value_type: ValueType) -> None:
        refusal = value_type.parse(value_type.pattern_miss)

        assert isinstance(refusal, value_type.error_type)
        assert isinstance(refusal, REFUSALS)
        assert refusal.raw == value_type.pattern_miss
        assert not decodes(value_type.text_type, value_type.pattern_miss)

    @value_type_cases()
    def test_trailing_newline_is_refused(self, value_type: ValueType) -> None:
        with_newline = f'{value_type.longest}\n'
        refusal = value_type.parse(with_newline)

        assert isinstance(refusal, value_type.error_type)
        assert isinstance(refusal, REFUSALS)
        assert refusal.raw == with_newline
        assert not decodes(value_type.text_type, with_newline)


class TestSlug:
    def test_archives_is_reserved(self) -> None:
        refusal = parse_slug('archives')

        assert isinstance(refusal, ReservedSlugError)
        assert refusal.raw == 'archives'
        assert not decodes(SlugText, 'archives')

    def test_name_that_only_starts_with_archives_is_accepted(self) -> None:
        assert parse_slug('archives-2') == 'archives-2'
        assert decodes(SlugText, 'archives-2')


def origin_url_key_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'url',
        [
            pytest.param('https://github.com/Owner/Name.git', id='https'),
            pytest.param('git@github.com:Owner/Name.git', id='scp'),
            pytest.param('ssh://git@example.com:22/owner/name', id='ssh-with-port'),
        ],
    )


def origin_url_without_key_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'url',
        [
            pytest.param('https://github.com/group/sub/name', id='subgroup'),
            pytest.param('https://github.com/name', id='one-name'),
            pytest.param('/srv/git/owner/name', id='local-path'),
            pytest.param('file:///srv/git/owner/name', id='file-url'),
            pytest.param('https://github.com/owner/name\n', id='trailing-newline'),
        ],
    )


class TestRepositoryKey:
    toplevel = Path('/work/project')
    digest = hashlib.sha256(b'/work/project').hexdigest()

    def test_local_key_is_the_prefix_and_the_path_digest(self) -> None:
        assert local_key(self.toplevel) == f'local:{self.digest}'
        assert parse_repository_key(local_key(self.toplevel)) == local_key(self.toplevel)

    @origin_url_key_cases()
    def test_origin_key_is_the_lowercased_owner_and_name(self, url: str) -> None:
        assert origin_key(url) == 'owner/name'

    @origin_url_without_key_cases()
    def test_origin_that_is_not_an_owner_and_a_name_has_no_key(self, url: str) -> None:
        assert origin_key(url) is None
