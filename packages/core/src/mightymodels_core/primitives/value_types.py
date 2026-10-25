"""The text values the state carries, each with a parse function and a msgspec type.

A parse function returns the value or its error, and the call site raises. The msgspec
types carry the same pattern and limit, and their patterns end in the end-of-string anchor
because msgspec searches a pattern and `$` would accept a trailing newline.

A repository key says which repository a row belongs to. A repository with an origin remote is
keyed by that remote's `owner/name`, lowercased and without its host, so the https and the ssh
form of one origin share a key. A repository with no origin is keyed by `LOCAL_PREFIX` and the
SHA-256 of its toplevel path; the prefix holds a colon, which no `owner/name` may, so the two
never meet. An origin that is not exactly an owner and a name on a host has no key of its own,
and `origin_key` answers `None` for it, because the URL is text the plugin does not control and
may carry a credential.
"""

import hashlib
import os
import re
from typing import TYPE_CHECKING, Annotated, NewType

from msgspec import Meta

from .errors import (
    InvalidRepositoryKeyError,
    InvalidRunIdError,
    InvalidSlugError,
    InvalidTaskIdError,
    ReservedSlugError,
)

if TYPE_CHECKING:
    from pathlib import Path

ARCHIVES_DIRECTORY = 'archives'
SLUG_LIMIT = 64
SLUG_PATTERN = rf'^(?!{ARCHIVES_DIRECTORY}\Z)[A-Za-z0-9][A-Za-z0-9_-]*\Z'
RUN_ID_PATTERN = r'^[0-9]{8}-[0-9]{6}\Z'
TASK_ID_LIMIT = 7
TASK_ID_PATTERN = r'^[TCR][0-9]{1,6}\Z'
LOCAL_PREFIX = 'local:'
REPOSITORY_KEY_LIMIT = 140
NAME_PATTERN = r'[._-]*[a-z0-9][a-z0-9._-]*'
REPOSITORY_KEY_PATTERN = rf'^(?:{NAME_PATTERN}/{NAME_PATTERN}|{LOCAL_PREFIX}[0-9a-f]{{64}})\Z'
HOSTED_REPOSITORY = re.compile(
    r'(?:(?:https?|ssh|git)://(?:[^/@]*@)?[^/@:]+(?::[0-9]+)?/|(?:[^/@:]+@)?[^/@:]+:(?!//))'
    r'(?P<path>[^:]+)'
)
GIT_SUFFIX = '.git'

Slug = NewType('Slug', str)
RunId = NewType('RunId', str)
TaskId = NewType('TaskId', str)
RepositoryKey = NewType('RepositoryKey', str)

type SlugText = Annotated[str, Meta(pattern=SLUG_PATTERN, max_length=SLUG_LIMIT)]
type RunIdText = Annotated[str, Meta(pattern=RUN_ID_PATTERN)]
type TaskIdText = Annotated[str, Meta(pattern=TASK_ID_PATTERN, max_length=TASK_ID_LIMIT)]
type RepositoryKeyText = Annotated[
    str, Meta(pattern=REPOSITORY_KEY_PATTERN, max_length=REPOSITORY_KEY_LIMIT)
]


def parse_slug(raw: str) -> Slug | InvalidSlugError | ReservedSlugError:
    if raw == ARCHIVES_DIRECTORY:
        return ReservedSlugError(raw=raw)

    if len(raw) > SLUG_LIMIT or not re.fullmatch(SLUG_PATTERN, raw):
        return InvalidSlugError(raw=raw, limit=SLUG_LIMIT)

    return Slug(raw)


def parse_run_id(raw: str) -> RunId | InvalidRunIdError:
    if not re.fullmatch(RUN_ID_PATTERN, raw):
        return InvalidRunIdError(raw=raw)

    return RunId(raw)


def parse_task_id(raw: str) -> TaskId | InvalidTaskIdError:
    if len(raw) > TASK_ID_LIMIT or not re.fullmatch(TASK_ID_PATTERN, raw):
        return InvalidTaskIdError(raw=raw, limit=TASK_ID_LIMIT)

    return TaskId(raw)


def parse_repository_key(raw: str) -> RepositoryKey | InvalidRepositoryKeyError:
    if len(raw) > REPOSITORY_KEY_LIMIT or not re.fullmatch(REPOSITORY_KEY_PATTERN, raw):
        return InvalidRepositoryKeyError(raw=raw, limit=REPOSITORY_KEY_LIMIT)

    return RepositoryKey(raw)


def origin_key(url: str) -> RepositoryKey | None:
    hosted = HOSTED_REPOSITORY.fullmatch(url)
    if hosted is None:
        return None

    owner_and_name = hosted['path'].strip('/').removesuffix(GIT_SUFFIX).lower()
    key = parse_repository_key(owner_and_name)
    if isinstance(key, InvalidRepositoryKeyError):
        return None

    return key


def local_key(toplevel: Path) -> RepositoryKey:
    digest = hashlib.sha256(os.fsencode(toplevel)).hexdigest()
    return RepositoryKey(f'{LOCAL_PREFIX}{digest}')
