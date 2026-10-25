"""What the snapshot tool returns: the Markdown, the JSON record and where each is to be written."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import encode_indented
from mightymodels_core.snapshot import snapshot_markdown
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from mightymodels_core.snapshot import SnapshotRecord


class SnapshotView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    record: str
    markdown_path: str
    record_path: str


def render_snapshot(
    record: SnapshotRecord, *, markdown_path: str, record_path: str
) -> SnapshotView:
    return SnapshotView(
        text=snapshot_markdown(record),
        record=encode_indented(record).decode('utf-8'),
        markdown_path=markdown_path,
        record_path=record_path,
    )
