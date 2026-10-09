"""The similarity service: search over everything the plugin has stored, and the scout-report spool.

`search` answers the stored rows that share a content word with a query, best BM25 rank first, at
most `CANDIDATE_CAP` of them, each with its overlap with the query, and it can be held to one kind.
It applies no threshold: a query is usually a part of what it looks for.

`take_in_spool` stores the scout reports waiting in the spool for this repository, each with its
similarity row in one transaction, and removes the file. A file for another repository stays. A
file that is not a report, or that redaction lengthens past its column, is set aside and the call
goes on. The spool and its file format are in `spool.py`.

The service reads and writes the database and the spool and nothing else.
"""

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from mightymodels_plugin.database import Database
from mightymodels_plugin.redaction import RedactedTextTooLongError
from mightymodels_plugin.tools.similarity.rendering import matches_text
from mightymodels_plugin.tools.similarity.repository import similarity_transaction
from mightymodels_plugin.tools.similarity.schema import (
    SimilarityKind,
    SimilarityView,
    SpooledReport,
)
from mightymodels_plugin.tools.similarity.spool import (
    set_aside,
    spooled_report,
    waiting_files,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class SimilarityService:
    database: Database
    spool: Path

    def search(self, query: str, kind: SimilarityKind | None) -> SimilarityView:
        with similarity_transaction(self.database) as repository:
            matches = tuple(repository.search(query, kind=kind))
        return SimilarityView(text=matches_text(matches), matches=matches)

    def store(self, report: SpooledReport) -> RedactedTextTooLongError | None:
        try:
            with similarity_transaction(self.database) as repository:
                repository.add_scout_report(report)
        except RedactedTextTooLongError as error:
            return error
        return None

    def take_in(self, file: Path) -> None:
        report = spooled_report(file)
        if report is None:
            set_aside(file, self.spool)
            return
        if report.repository_key != self.database.repository_key:
            return
        if self.store(report) is not None:
            set_aside(file, self.spool)
            return
        file.unlink()

    def take_in_spool(self) -> None:
        for file in waiting_files(self.spool):
            with suppress(FileNotFoundError):
                self.take_in(file)
