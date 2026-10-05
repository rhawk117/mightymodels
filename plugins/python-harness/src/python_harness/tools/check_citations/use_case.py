"""Check the citations of one document: a file inside the project, or inline text."""

from python_harness.citations.domain import CitationReport
from python_harness.citations.services import check_citations, check_citations_in_text
from python_harness.core.workspace import Workspace
from python_harness.tools.check_citations.schema import INLINE_DOCUMENT_NAME, CitationsRequest
from python_harness.tools.errors import DocumentChoiceError


def run(workspace: Workspace, request: CitationsRequest) -> CitationReport:
    path, text = request.path, request.text
    if path is not None and text is None:
        return check_citations(workspace, workspace.resolve(path))
    if text is not None and path is None:
        return check_citations_in_text(workspace, text, INLINE_DOCUMENT_NAME)
    raise DocumentChoiceError
