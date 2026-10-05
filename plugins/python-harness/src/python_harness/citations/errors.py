"""Failures checking a document's citations, reported as messages, not tracebacks."""

from pathlib import Path

from python_harness.core.errors import PythonHarnessError


class CitationDocumentMissingError(PythonHarnessError):
    def __init__(self, document: Path) -> None:
        super().__init__(f'citation document {document} is not a file')
        self.document = document


class CitationDocumentUnreadableError(PythonHarnessError):
    def __init__(self, document: str, reason: str) -> None:
        super().__init__(f'citation document {document} is not readable text: {reason}')
        self.document = document
        self.reason = reason
