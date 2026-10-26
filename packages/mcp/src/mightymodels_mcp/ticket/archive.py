"""The archive files of a closed ticket: the free slot search and the two writes.

Core cannot own this yet, so the adapter keeps every archive file write here. The record is
written before the markdown, so a failed write never leaves a markdown without its record.
"""

from itertools import count
from typing import TYPE_CHECKING

from mightymodels_core.primitives.codec import encode_indented
from mightymodels_core.ticket_closing.archive_markdown import archive_markdown

if TYPE_CHECKING:
    from mightymodels_core.primitives import Slug
    from mightymodels_core.ticket_closing.archive import ArchiveRecord
    from mightymodels_core.workspace import RecordFiles, Workspace


def is_free(files: RecordFiles) -> bool:
    return not (files.markdown.exists() or files.record.exists())


def free_archive_files(workspace: Workspace, slug: Slug) -> RecordFiles:
    candidates = (workspace.handoffs.archive(slug, repeat) for repeat in count(1))
    return next(files for files in candidates if is_free(files))


def write_archive(files: RecordFiles, archive: ArchiveRecord, *, decision_limit: int) -> None:
    markdown = archive_markdown(archive, files.record.name, decision_limit)
    files.record.parent.mkdir(parents=True, exist_ok=True)
    files.record.write_bytes(encode_indented(archive))
    files.markdown.write_text(markdown, encoding='utf-8')
