"""Documentation failures whose messages are safe to show the calling model."""


class DocumentationError(Exception):
    """An actionable retrieval or request failure, safe to expose to the caller."""


class PermanentMissError(DocumentationError):
    """A failure that repeats until the upstream changes, so it may be remembered."""


class AmbiguousUrlError(DocumentationError, ValueError):
    def __init__(self) -> None:
        super().__init__(
            'Encoded, ambiguous, whitespace, or control characters are not allowed'
            ' in documentation URLs.'
        )


class ForeignUrlError(DocumentationError, ValueError):
    def __init__(self) -> None:
        super().__init__('URL must use https://docs.python.org without a query.')


class UnversionedUrlError(DocumentationError, ValueError):
    def __init__(self) -> None:
        super().__init__('A versioned documentation page path is required.')


class InvalidVersionError(DocumentationError, ValueError):
    def __init__(self, version: str) -> None:
        super().__init__(f'{version!r} is not a Python 3 minor version such as 3.13.')


class UnsupportedInventoryError(DocumentationError):
    def __init__(self) -> None:
        super().__init__('Unsupported or malformed Sphinx inventory header.')


class CorruptInventoryError(DocumentationError):
    def __init__(self) -> None:
        super().__init__('The documentation inventory is corrupt or incomplete.')


class InventoryTooLargeError(DocumentationError):
    def __init__(self, limit: int) -> None:
        super().__init__(f'Expanded inventory exceeds {limit} bytes.')


class InventoryEntryLimitError(DocumentationError):
    def __init__(self, limit: int) -> None:
        super().__init__(f'Documentation inventory exceeds {limit} entries.')


class UnparseableInventoryError(DocumentationError):
    def __init__(self) -> None:
        super().__init__('Could not parse the official Python inventory.')


class MalformedInventoryError(DocumentationError):
    def __init__(self, malformed: int, total: int) -> None:
        super().__init__(f'{malformed} of {total} Python inventory entries have unusable URLs.')


class EmptyInventoryError(DocumentationError):
    def __init__(self) -> None:
        super().__init__('The inventory contains no standard-library symbols.')


class MissingDefinitionBodyError(DocumentationError):
    def __init__(self) -> None:
        super().__init__('The documented symbol has no definition body.')


class MissingAnchorError(DocumentationError):
    def __init__(self, fragment: str) -> None:
        super().__init__(f'Anchor {fragment!r} is missing from the official page.')


class MissingSectionError(DocumentationError):
    def __init__(self) -> None:
        super().__init__("The symbol's documentation section is missing.")


class EmptyExtractionError(DocumentationError):
    def __init__(self) -> None:
        super().__init__('The extracted documentation is empty.')


class DownloadTooLargeError(DocumentationError):
    def __init__(self, limit: int) -> None:
        super().__init__(f'Documentation response exceeds {limit} bytes.')


class UpstreamStatusError(DocumentationError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f'Official documentation returned HTTP {status_code}.')


class PageNotFoundError(DocumentationError):
    def __init__(self, url: str) -> None:
        super().__init__(f'Official documentation has no page at {url}.')


class VersionNotPublishedError(PermanentMissError):
    def __init__(self, version: str) -> None:
        super().__init__(
            f'Python {version} documentation is not published. Read requires-python'
            ' in pyproject.toml or .python-version for the project version.'
        )


class RetrievalFailedError(DocumentationError):
    def __init__(self, url: str) -> None:
        super().__init__(f'Could not reach the official documentation at {url}.')


class FillTimeoutError(DocumentationError):
    def __init__(self, seconds: float) -> None:
        super().__init__(f'Documentation retrieval exceeded its {seconds:g}s deadline.')


class FillInterruptedError(DocumentationError):
    def __init__(self) -> None:
        super().__init__('Documentation retrieval was interrupted; retry the call.')


class CallDeadlineExceededError(DocumentationError):
    def __init__(self, seconds: float) -> None:
        super().__init__(f'The call exceeded its {seconds:g}s deadline; retry shortly.')


class UnknownSymbolError(DocumentationError):
    def __init__(self, symbol: str, suggestions: list[str]) -> None:
        hint = f' Closest names: {", ".join(suggestions)}.' if suggestions else ''
        super().__init__(
            f'Unknown symbol {symbol!r} for this Python version.{hint}'
            ' Use search_python_docs to find exact names.'
        )


class OffsetOutOfRangeError(DocumentationError):
    def __init__(self, offset: int, length: int) -> None:
        super().__init__(f'Offset {offset} exceeds the section length ({length}).')
