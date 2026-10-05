"""Validated documentation versions, official URLs, and the per-version symbol index."""

import re
from typing import Annotated
from urllib.parse import urldefrag, urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, RootModel, StringConstraints

from python_harness.documentation.errors import (
    AmbiguousUrlError,
    DocumentationError,
    ForeignUrlError,
    UnversionedUrlError,
)

DOCUMENTATION_HOST = 'docs.python.org'
VERSION_PATTERN = r'3\.(0|[1-9][0-9]?)'

type VersionText = Annotated[str, StringConstraints(strict=True, pattern=f'^{VERSION_PATTERN}$')]


def has_unsafe_characters(url: str) -> bool:
    return not url.isprintable() or any(map(str.isspace, url)) or '\\' in url


def has_ambiguous_path(path: str) -> bool:
    return '%' in path or not {'.', '..'}.isdisjoint(path.split('/'))


def ambiguous_url_violation(url: str) -> AmbiguousUrlError | None:
    if has_unsafe_characters(url) or has_ambiguous_path(urlsplit(url).path):
        return AmbiguousUrlError()
    return None


def is_official_origin(url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == 'https'
        and parsed.netloc == DOCUMENTATION_HOST
        and '?' not in url.partition('#')[0]
    )


def documentation_url_violation(url: str) -> DocumentationError | None:
    if (ambiguity := ambiguous_url_violation(url)) is not None:
        return ambiguity
    if not is_official_origin(url):
        return ForeignUrlError()
    version_text, _, page = urlsplit(url).path.removeprefix('/').partition('/')
    if not page or re.fullmatch(VERSION_PATTERN, version_text) is None:
        return UnversionedUrlError()
    return None


def checked_documentation_url(url: str) -> str:
    if (violation := documentation_url_violation(url)) is not None:
        raise violation
    return url


type DocumentationUrlText = Annotated[
    str, StringConstraints(strict=True), AfterValidator(checked_documentation_url)
]


class PythonVersion(RootModel[VersionText]):
    """Python minor version such as 3.13.

    Read requires-python in pyproject.toml or .python-version first; do not guess.
    """

    model_config = ConfigDict(frozen=True)

    @property
    def base_url(self) -> str:
        return f'https://{DOCUMENTATION_HOST}/{self.root}/'


class DocumentationUrl(RootModel[DocumentationUrlText]):
    """An official, versioned docs.python.org URL."""

    model_config = ConfigDict(frozen=True)

    @property
    def path(self) -> str:
        return urlsplit(self.root).path

    @property
    def version(self) -> PythonVersion:
        return PythonVersion.model_validate(self.path.split('/')[1])

    @property
    def page_path(self) -> str:
        return self.path.removeprefix('/').partition('/')[2]

    @property
    def fragment(self) -> str:
        return urldefrag(self.root).fragment

    @property
    def page_url(self) -> 'DocumentationUrl':
        return DocumentationUrl.model_validate(urldefrag(self.root).url)


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)


class Symbol(Model):
    name: str
    kind: str
    source_url: DocumentationUrl


class SymbolIndex(Model):
    documentation_version: str
    symbols: dict[str, Symbol]
