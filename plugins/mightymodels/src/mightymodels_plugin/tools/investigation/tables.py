"""The `ledger_entries` table: one row per entry of an investigation's ledger, the target first."""

from typing import Annotated

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from mightymodels_plugin.declarative import Base, Key, Serial

type EntryNumbers = Annotated[list[int], mapped_column(JSON)]


class LedgerEntryRow(Base):
    __tablename__ = 'ledger_entries'

    repository_key: Mapped[Key]
    investigation_id: Mapped[Key]
    seq: Mapped[Serial]
    round: Mapped[int]
    kind: Mapped[str]
    text: Mapped[str]
    source: Mapped[str]
    cite: Mapped[str | None]
    supersedes: Mapped[EntryNumbers]
    at: Mapped[str]
    head: Mapped[str | None]
