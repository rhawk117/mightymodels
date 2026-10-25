import hashlib
import string
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import msgspec
import pytest
from hypothesis import example, given
from hypothesis import strategies as st
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


SLUG = ValueType(
    name='slug',
    parse=parse_slug,
    text_type=SlugText,
    longest='a' * 64,
    over_limit='a',
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
    over_limit='7',
    limit=7,
    pattern_miss='X1',
    error_type=InvalidTaskIdError,
)
REPOSITORY_KEY = ValueType(
    name='repository-key',
    parse=parse_repository_key,
    text_type=RepositoryKeyText,
    longest=LONGEST_KEY,
    over_limit='b',
    limit=140,
    pattern_miss='Owner/Name',
    error_type=InvalidRepositoryKeyError,
)


VALUE_TYPES = (SLUG, RUN_ID, TASK_ID, REPOSITORY_KEY)
LIMITED_VALUE_TYPES = (SLUG, TASK_ID, REPOSITORY_KEY)
NAME_CHARACTERS = string.ascii_letters + string.digits
NAME_TAIL_CHARACTERS = NAME_CHARACTERS + '_-'
MAX_EXCESS = 500


def assert_decode_round_trips(text_type: object, value: str) -> None:
    assert msgspec.json.decode(msgspec.json.encode(value), type=text_type) == value


def assert_decode_refuses(text_type: object, raw: str) -> None:
    with pytest.raises(msgspec.ValidationError):
        msgspec.json.decode(msgspec.json.encode(raw), type=text_type)


def value_type_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'value_type', [pytest.param(value_type, id=value_type.name) for value_type in VALUE_TYPES]
    )


class TestValueTypes:
    value_types = st.sampled_from(VALUE_TYPES)
    limited_value_types = st.sampled_from(LIMITED_VALUE_TYPES)
    excesses = st.integers(min_value=1, max_value=MAX_EXCESS)

    @value_type_cases()
    def test_longest_valid_value_is_accepted(self, value_type: ValueType) -> None:
        assert value_type.parse(value_type.longest) == value_type.longest
        assert_decode_round_trips(value_type.text_type, value_type.longest)

    @given(value_type=limited_value_types, excess=excesses)
    @example(value_type=SLUG, excess=1)
    @example(value_type=TASK_ID, excess=1)
    @example(value_type=REPOSITORY_KEY, excess=1)
    def test_value_over_the_limit_is_refused(self, value_type: ValueType, excess: int) -> None:
        over_limit = value_type.longest + value_type.over_limit * excess
        refusal = value_type.parse(over_limit)

        assert isinstance(refusal, value_type.error_type)
        assert isinstance(refusal, LIMITED_REFUSALS)
        assert refusal.raw == over_limit
        assert refusal.limit == value_type.limit
        assert_decode_refuses(value_type.text_type, over_limit)

    @given(value_type=value_types)
    @example(value_type=SLUG)
    @example(value_type=RUN_ID)
    @example(value_type=TASK_ID)
    @example(value_type=REPOSITORY_KEY)
    def test_value_missing_the_pattern_is_refused(self, value_type: ValueType) -> None:
        refusal = value_type.parse(value_type.pattern_miss)

        assert isinstance(refusal, value_type.error_type)
        assert isinstance(refusal, REFUSALS)
        assert refusal.raw == value_type.pattern_miss
        assert_decode_refuses(value_type.text_type, value_type.pattern_miss)

    @given(value_type=value_types)
    @example(value_type=SLUG)
    @example(value_type=RUN_ID)
    @example(value_type=TASK_ID)
    @example(value_type=REPOSITORY_KEY)
    def test_trailing_newline_is_refused(self, value_type: ValueType) -> None:
        with_newline = f'{value_type.longest}\n'
        refusal = value_type.parse(with_newline)

        assert isinstance(refusal, value_type.error_type)
        assert isinstance(refusal, REFUSALS)
        assert refusal.raw == with_newline
        assert_decode_refuses(value_type.text_type, with_newline)


class TestSlug:
    def test_archives_is_reserved(self) -> None:
        refusal = parse_slug('archives')

        assert isinstance(refusal, ReservedSlugError)
        assert refusal.raw == 'archives'
        assert_decode_refuses(SlugText, 'archives')

    def test_name_that_only_starts_with_archives_is_accepted(self) -> None:
        assert parse_slug('archives-2') == 'archives-2'
        assert_decode_round_trips(SlugText, 'archives-2')


def origin_url_without_key_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'url',
        [
            pytest.param('/srv/git/owner/name', id='local-path'),
            pytest.param('file:///srv/git/owner/name', id='file-url'),
            pytest.param('https://github.com/owner/name\n', id='trailing-newline'),
        ],
    )


URL_FORMS = (
    'https://github.com/{path}',
    'git@github.com:{path}',
    'ssh://git@example.com:22/{path}',
)


class TestRepositoryKey:
    toplevel = Path('/work/project')
    digest = hashlib.sha256(b'/work/project').hexdigest()
    url_forms = st.sampled_from(URL_FORMS)
    git_suffixes = st.sampled_from(('', '.git'))
    names = st.tuples(
        st.sampled_from(NAME_CHARACTERS),
        st.text(alphabet=NAME_TAIL_CHARACTERS, max_size=60),
    ).map(''.join)
    unkeyed_paths = st.one_of(
        st.lists(names, min_size=1, max_size=1),
        st.lists(names, min_size=3, max_size=5),
    )

    def test_local_key_is_the_prefix_and_the_path_digest(self) -> None:
        assert local_key(self.toplevel) == f'local:{self.digest}'
        assert parse_repository_key(local_key(self.toplevel)) == local_key(self.toplevel)

    @given(form=url_forms, owner=names, name=names, suffix=git_suffixes)
    @example(form=URL_FORMS[0], owner='Owner', name='Name', suffix='.git')
    @example(form=URL_FORMS[1], owner='Owner', name='Name', suffix='.git')
    @example(form=URL_FORMS[2], owner='owner', name='name', suffix='')
    def test_origin_key_is_the_lowercased_owner_and_name(
        self, form: str, owner: str, name: str, suffix: str
    ) -> None:
        url = form.format(path=f'{owner}/{name}{suffix}')

        assert origin_key(url) == f'{owner}/{name}'.lower()

    @given(form=url_forms, segments=unkeyed_paths)
    @example(form=URL_FORMS[0], segments=['group', 'sub', 'name'])
    @example(form=URL_FORMS[0], segments=['name'])
    def test_origin_that_is_not_an_owner_and_a_name_has_no_key(
        self, form: str, segments: list[str]
    ) -> None:
        assert origin_key(form.format(path='/'.join(segments))) is None

    @origin_url_without_key_cases()
    def test_non_hosted_origin_has_no_key(self, url: str) -> None:
        assert origin_key(url) is None
