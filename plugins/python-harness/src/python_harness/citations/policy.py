"""Whether a source file holds a citation's lines and its quoted code within them."""

from python_harness.citations.domain import Citation, CitationOptions, CitationProblem
from python_harness.core.sources import SourceFile
from python_harness.core.text import collapse_whitespace


def quote_matches(quote: str, lines: tuple[str, ...]) -> bool:
    return collapse_whitespace(quote) in collapse_whitespace(' '.join(lines))


def check_line_range(citation: Citation, source: SourceFile) -> CitationProblem | None:
    if 1 <= citation.start <= citation.end <= source.line_count:
        return None
    return CitationProblem.LINE_OUT_OF_RANGE


def check_quote(
    quote: str | None, cited: tuple[str, ...], options: CitationOptions
) -> CitationProblem | None:
    collapsed = collapse_whitespace(quote or '')
    if len(collapsed) < options.minimum_quote_characters:
        return CitationProblem.MISSING_QUOTE
    if quote_matches(collapsed, cited):
        return None
    return CitationProblem.QUOTE_NOT_FOUND


def check_cited_lines(
    citation: Citation, source: SourceFile, *, options: CitationOptions | None = None
) -> CitationProblem | None:
    chosen = CitationOptions() if options is None else options
    if (problem := check_line_range(citation, source)) is not None:
        return problem
    cited = source.line_range(citation.start, citation.end)
    return check_quote(citation.quote, cited, chosen)
