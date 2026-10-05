"""Search a version's symbol catalog with tier-labeled matches."""

from python_harness.documentation.domain import PythonVersion
from python_harness.documentation.matching import SymbolMatch, match_symbols
from python_harness.documentation.services import DocumentationService
from python_harness.tools.search_python_docs.schema import SearchMatch, SearchRequest, SearchResult


def search_match(match: SymbolMatch) -> SearchMatch:
    return SearchMatch(
        name=match.name, kind=match.kind, source_url=match.source_url.text, match=match.match
    )


async def run(service: DocumentationService, request: SearchRequest) -> SearchResult:
    catalog = await service.catalog(PythonVersion(text=request.version))
    matches = match_symbols(catalog, request.query, service.settings.fuzzy_score_cutoff)
    return SearchResult(
        python_version=request.version,
        documentation_version=catalog.index.documentation_version,
        query=request.query,
        total_matches=len(matches),
        matches=list(map(search_match, matches[: request.limit])),
    )
