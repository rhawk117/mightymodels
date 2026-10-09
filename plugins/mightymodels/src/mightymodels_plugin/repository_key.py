"""The key every row of the state database carries: which repository the row belongs to.

One database serves every repository, so a row is found only under the key it was written with.
A repository with an origin remote is keyed by that remote's `owner/name`, lowercased and without
its host, so the https and the ssh form of one origin share a key and so does the same owner and
name on another host. A repository with no origin is keyed by `LOCAL_PREFIX` and the SHA-256 of
its toplevel path; the prefix holds a colon, which no `owner/name` may, so the two never meet.

The remote URL is text the plugin does not control. `origin_key` takes the path of a hosted URL,
in the URL form or the scp form, and a path with a colon in it is no path, so no origin spells the
local prefix. The key type then refuses anything but two plain names: no other separator, no
parent reference, no encoded character, nothing over `REPOSITORY_KEY_LIMIT`. The refusal does not
repeat the URL, which may carry a credential.

A key is a column value. It is not a `str` and not a path, and nothing joins one onto a directory.
"""

import hashlib
import os
import re
from pathlib import Path
from typing import Annotated, override

from pydantic import ConfigDict, RootModel, StringConstraints, ValidationError

from mightymodels_plugin.errors import StateError

LOCAL_PREFIX = 'local:'
REPOSITORY_KEY_LIMIT = 140
NAME_PATTERN = r'[._-]*[a-z0-9][a-z0-9._-]*'
REPOSITORY_KEY_PATTERN = rf'^(?:{NAME_PATTERN}/{NAME_PATTERN}|{LOCAL_PREFIX}[0-9a-f]{{64}})$'
HOSTED_REPOSITORY = re.compile(
    r'(?:(?:https?|ssh|git)://(?:[^/@]*@)?[^/@:]+(?::[0-9]+)?/|(?:[^/@:]+@)?[^/@:]+:(?!//))'
    r'(?P<path>[^:]+)'
)
GIT_SUFFIX = '.git'

type RepositoryKeyText = Annotated[
    str, StringConstraints(pattern=REPOSITORY_KEY_PATTERN, max_length=REPOSITORY_KEY_LIMIT)
]


class UnusableOriginError(StateError):
    def __init__(self, url: str) -> None:
        super().__init__(
            'the origin remote does not name a repository as owner/name on a host, so this '
            'repository has no key to keep its state under; `git remote get-url origin` shows '
            'the URL'
        )
        self.url = url


class RepositoryKey(RootModel[RepositoryKeyText]):
    model_config = ConfigDict(frozen=True)

    @override
    def __str__(self) -> str:
        return self.root


def origin_key(url: str) -> RepositoryKey | UnusableOriginError:
    hosted = HOSTED_REPOSITORY.fullmatch(url)
    if hosted is None:
        return UnusableOriginError(url)
    owner_and_name = hosted['path'].strip('/').removesuffix(GIT_SUFFIX).lower()
    try:
        return RepositoryKey(owner_and_name)
    except ValidationError:
        return UnusableOriginError(url)


def local_key(toplevel: Path) -> RepositoryKey:
    digest = hashlib.sha256(os.fsencode(toplevel)).hexdigest()
    return RepositoryKey(f'{LOCAL_PREFIX}{digest}')
