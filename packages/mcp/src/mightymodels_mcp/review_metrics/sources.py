"""The source files under a root and what each one measures.

Python is parsed with `ast`, so its numbers are exact. JavaScript and TypeScript are read with
patterns: the imports are reliable, the function numbers are approximate and each one says so.
"""

import logging
from typing import TYPE_CHECKING

from mightymodels_mcp.review_metrics.files import iter_source_files, language_of
from mightymodels_mcp.review_metrics.languages import SOURCE_LANGUAGES

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_mcp.review_metrics.domain import FileMetric

LOGGER = logging.getLogger(__name__)


def read_source(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError as error:
        LOGGER.debug('Unable to read source file %s', path, exc_info=error)
        return None


def analyze_source(path: Path, root: Path) -> FileMetric | None:
    language = language_of(path)
    text = read_source(path)
    if text is None or language is None:
        return None
    rel = path.relative_to(root)
    return SOURCE_LANGUAGES[language].analyze(rel, text)


def collect_metrics(root: Path) -> list[FileMetric]:
    analyzed = (analyze_source(path, root) for path in iter_source_files(root))
    return [metric for metric in analyzed if metric is not None]
