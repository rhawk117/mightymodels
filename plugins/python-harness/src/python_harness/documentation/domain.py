"""Validated documentation versions, official URLs, and the per-version symbol index."""

import re
from dataclasses import dataclass
from urllib.parse import urldefrag, urlsplit

from python_harness.documentation.errors import (
    AmbiguousUrlError,
    DocumentationError,
    ForeignUrlError,
    InvalidVersionError,
    UnversionedUrlError,
)

DOCUMENTATION_HOST = 'docs.python.org'
VERSION_PATTERN = r'3\.(0|[1-9][0-9]?)'


def python_version_violation(text: str) -> InvalidVersionError | None:
    if re.fullmatch(VERSION_PATTERN, text) is None:
        return InvalidVersionError(text)
    return None


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


@dataclass(frozen=True, slots=True, kw_only=True)
class PythonVersion:
    text: str

    def __post_init__(self) -> None:
        if (violation := python_version_violation(self.text)) is not None:
            raise violation

    @property
    def base_url(self) -> str:
        return f'https://{DOCUMENTATION_HOST}/{self.text}/'


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentationUrl:
    text: str

    def __post_init__(self) -> None:
        if (violation := documentation_url_violation(self.text)) is not None:
            raise violation

    @property
    def path(self) -> str:
        return urlsplit(self.text).path

    @property
    def version(self) -> PythonVersion:
        return PythonVersion(text=self.path.split('/')[1])

    @property
    def page_path(self) -> str:
        return self.path.removeprefix('/').partition('/')[2]

    @property
    def fragment(self) -> str:
        return urldefrag(self.text).fragment

    @property
    def page_url(self) -> 'DocumentationUrl':
        return DocumentationUrl(text=urldefrag(self.text).url)


@dataclass(frozen=True, slots=True, kw_only=True)
class Symbol:
    name: str
    kind: str
    source_url: DocumentationUrl


@dataclass(frozen=True, slots=True, kw_only=True)
class SymbolIndex:
    documentation_version: str
    symbols: dict[str, Symbol]
