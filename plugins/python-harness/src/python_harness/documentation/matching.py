"""Layered symbol matching: exact and segment-prefix hits, then labeled approximations."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum, auto
from functools import partial
from itertools import chain
from typing import NamedTuple

from rapidfuzz import fuzz, process, utils

from python_harness.documentation.domain import DocumentationUrl, Model, SymbolIndex

SEGMENT_SEPARATORS = str.maketrans('._', '  ')


class MatchTier(StrEnum):
    EXACT = auto()
    PREFIX = auto()
    APPROXIMATE = auto()


class SymbolMatch(Model):
    name: str
    kind: str
    source_url: DocumentationUrl
    match: MatchTier


class SymbolRank(NamedTuple):
    not_exact_match: bool
    not_prefix_match: bool
    name_length: int
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SymbolCatalog:
    index: SymbolIndex
    segments: Mapping[str, tuple[str, ...]]
    fuzzy_keys: Mapping[str, str]
    namespaces: frozenset[str]


def name_segments(text: str) -> tuple[str, ...]:
    return tuple(text.casefold().translate(SEGMENT_SEPARATORS).split())


def dotted_scopes(name: str) -> Iterator[str]:
    parts = name.casefold().split('.')
    return ('.'.join(parts[:end]) for end in range(len(parts) - 1, 0, -1))


def catalog_symbols(index: SymbolIndex) -> SymbolCatalog:
    names = index.symbols.keys()
    return SymbolCatalog(
        index=index,
        segments={name: name_segments(name) for name in names},
        fuzzy_keys={name: utils.default_process(name) for name in names},
        namespaces=frozenset(chain.from_iterable(map(dotted_scopes, names))),
    )


def rank_name(name: str, *, query: str) -> SymbolRank:
    folded = name.casefold()
    return SymbolRank(folded != query, not folded.startswith(query), len(name), name)


def prefixes_any(token: str, segments: tuple[str, ...]) -> bool:
    return any(segment.startswith(token) for segment in segments)


def covers_query(segments: tuple[str, ...], query_segments: tuple[str, ...]) -> bool:
    return all(prefixes_any(token, segments) for token in query_segments)


def prefix_names(catalog: SymbolCatalog, query_segments: tuple[str, ...]) -> list[str]:
    return [
        name
        for name, segments in catalog.segments.items()
        if covers_query(segments, query_segments)
    ]


def query_forms(query: str) -> list[tuple[str, ...]]:
    segments = name_segments(query)
    if not segments:
        return []
    joined = (''.join(segments),)
    return [segments, joined] if len(segments) > 1 else [segments]


def precise_names(catalog: SymbolCatalog, query: str) -> list[str]:
    candidates = map(partial(prefix_names, catalog), query_forms(query))
    found = next((names for names in candidates if names), [])
    return sorted(found, key=partial(rank_name, query=query.casefold()))


def fuzzy_names(query: str, choices: Mapping[str, str], cutoff: float) -> list[str]:
    results = process.extract(
        utils.default_process(query),
        choices,
        scorer=fuzz.WRatio,
        processor=None,
        limit=None,
        score_cutoff=cutoff,
    )
    return [name for _, _, name in results]


def scoped_members(catalog: SymbolCatalog, scope: str) -> dict[str, str]:
    prefix = f'{scope}.'
    members = (
        (name, name[len(prefix) :])
        for name in catalog.segments
        if name.casefold().startswith(prefix)
    )
    return {name: utils.default_process(member) for name, member in members if '.' not in member}


def scoped_names(catalog: SymbolCatalog, query: str, cutoff: float) -> list[str]:
    scope = next((scope for scope in dotted_scopes(query) if scope in catalog.namespaces), None)
    if scope is None:
        return []
    return fuzzy_names(query[len(scope) + 1 :], scoped_members(catalog, scope), cutoff)


def approximate_names(catalog: SymbolCatalog, query: str, cutoff: float) -> list[str]:
    return scoped_names(catalog, query, cutoff) or fuzzy_names(query, catalog.fuzzy_keys, cutoff)


def symbol_match(catalog: SymbolCatalog, name: str, tier: MatchTier) -> SymbolMatch:
    symbol = catalog.index.symbols[name]
    return SymbolMatch(name=symbol.name, kind=symbol.kind, source_url=symbol.source_url, match=tier)


def precise_tier(name: str, query: str) -> MatchTier:
    return MatchTier.EXACT if name.casefold() == query.casefold() else MatchTier.PREFIX


def match_symbols(catalog: SymbolCatalog, query: str, cutoff: float) -> list[SymbolMatch]:
    if names := precise_names(catalog, query):
        return [symbol_match(catalog, name, precise_tier(name, query)) for name in names]
    return [
        symbol_match(catalog, name, MatchTier.APPROXIMATE)
        for name in approximate_names(catalog, query, cutoff)
    ]
