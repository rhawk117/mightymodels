"""Search a version's symbol catalog with tier-labeled matches."""

from python_harness.documentation.matching import match_symbols
from python_harness.documentation.services import DocumentationService
from python_harness.tools.search_python_docs.schema import SearchRequest, SearchResult


async def run(service: DocumentationService, request: SearchRequest) -> SearchResult:
    catalog = await service.catalog(request.version)
    matches = match_symbols(catalog, request.query, service.settings.fuzzy_score_cutoff)
    return SearchResult(
        python_version=request.version,
        documentation_version=catalog.index.documentation_version,
        query=request.query,
        total_matches=len(matches),
        matches=matches[: request.limit],
    )
