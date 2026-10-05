"""Resolve an exact symbol and render one page of its documentation section."""

from python_harness.documentation.errors import OffsetOutOfRangeError, UnknownSymbolError
from python_harness.documentation.matching import SymbolCatalog, match_symbols
from python_harness.documentation.services import DocumentationService
from python_harness.documentation.settings import Settings
from python_harness.tools.read_python_docs.schema import ReadRequest, SectionPage


def suggested_names(catalog: SymbolCatalog, symbol: str, settings: Settings) -> list[str]:
    matches = match_symbols(catalog, symbol, settings.fuzzy_score_cutoff)
    return [match.name for match in matches[: settings.suggestion_count]]


async def run(service: DocumentationService, request: ReadRequest) -> str:
    catalog = await service.catalog(request.version)
    symbol = catalog.index.symbols.get(request.symbol)
    if symbol is None:
        suggestions = suggested_names(catalog, request.symbol, service.settings)
        raise UnknownSymbolError(request.symbol, suggestions)
    text = await service.section(symbol)
    if request.offset > len(text):
        raise OffsetOutOfRangeError(request.offset, len(text))
    page = SectionPage(
        symbol=symbol,
        documentation_version=catalog.index.documentation_version,
        text=text,
        offset=request.offset,
        max_chars=request.max_chars,
    )
    return page.render()
