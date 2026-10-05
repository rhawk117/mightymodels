"""Reading cited sources and checking every citation in a Markdown document."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

from python_harness.citations.domain import (
    Citation,
    CitationFailure,
    CitationOptions,
    CitationProblem,
    CitationReport,
)
from python_harness.citations.errors import (
    CitationDocumentMissingError,
    CitationDocumentUnreadableError,
)
from python_harness.citations.policy import check_cited_lines
from python_harness.citations.util import find_uncited_rows, parse_citations
from python_harness.core.errors import PathOutsideWorkspaceError
from python_harness.core.sources import SourceFile, read_source
from python_harness.core.workspace import Workspace


def locate_document(workspace: Workspace, document: Path) -> Path:
    path = workspace.root.joinpath(document).resolve()
    if not path.is_file():
        raise CitationDocumentMissingError(path)
    return path


def describe_document(workspace: Workspace, path: Path) -> str:
    if path.is_relative_to(workspace.root):
        return path.relative_to(workspace.root).as_posix()
    return path.as_posix()


@contextmanager
def translate_read_errors(document_name: str) -> Generator[None]:
    try:
        yield
    except (OSError, UnicodeDecodeError) as error:
        raise CitationDocumentUnreadableError(document_name, str(error)) from error


def read_cited_source(workspace: Workspace, citation: Citation) -> SourceFile | CitationProblem:
    try:
        path = workspace.resolve(citation.path)
    except PathOutsideWorkspaceError:
        return CitationProblem.OUTSIDE_WORKSPACE
    if not path.is_file():
        return CitationProblem.MISSING_FILE
    return read_cited_file(workspace, path)


def read_cited_file(workspace: Workspace, path: Path) -> SourceFile | CitationProblem:
    try:
        return read_source(workspace, path)
    except OSError, SyntaxError, UnicodeDecodeError:
        return CitationProblem.UNREADABLE_FILE


def check_citation(
    workspace: Workspace, citation: Citation, *, options: CitationOptions | None = None
) -> CitationProblem | None:
    source = read_cited_source(workspace, citation)
    if isinstance(source, CitationProblem):
        return source
    return check_cited_lines(citation, source, options=options)


def check_citations_in_text(
    workspace: Workspace,
    text: str,
    document_name: str,
    *,
    options: CitationOptions | None = None,
) -> CitationReport:
    citations = parse_citations(text)
    problems = (
        (citation, check_citation(workspace, citation, options=options)) for citation in citations
    )
    failures = tuple(
        CitationFailure(citation, problem) for citation, problem in problems if problem is not None
    )
    uncited_rows = find_uncited_rows(text)
    return CitationReport(document_name, len(citations), failures, uncited_rows)


def check_citations_in_stream(
    workspace: Workspace,
    stream: TextIO,
    document_name: str,
    *,
    options: CitationOptions | None = None,
) -> CitationReport:
    with translate_read_errors(document_name):
        text = stream.read()
    return check_citations_in_text(workspace, text, document_name, options=options)


def check_citations(
    workspace: Workspace, document: Path, *, options: CitationOptions | None = None
) -> CitationReport:
    path = locate_document(workspace, document)
    name = describe_document(workspace, path)
    with translate_read_errors(name):
        text = path.read_text(encoding='utf-8')
    return check_citations_in_text(workspace, text, name, options=options)
