"""The `contract_commands` and `receipts` tables: a ticket's approved commands and their runs."""

from sqlalchemy.orm import Mapped

from mightymodels_plugin.declarative import Base, Indexed, Key, Serial, Texts


class CommandRow(Base):
    __tablename__ = 'contract_commands'

    repository_key: Mapped[Key]
    slug: Mapped[Key]
    command_id: Mapped[Key]
    task_id: Mapped[str | None]
    argv: Mapped[Texts]
    expect_exit: Mapped[int]
    timeout: Mapped[int]
    approved_by: Mapped[str]
    approved_at: Mapped[str]
    head: Mapped[str | None]


class ReceiptRow(Base):
    __tablename__ = 'receipts'

    id: Mapped[Serial]
    repository_key: Mapped[str]
    slug: Mapped[Indexed]
    command_id: Mapped[str]
    argv: Mapped[Texts]
    outcome: Mapped[str]
    exit: Mapped[int | None]
    duration_ms: Mapped[int]
    stdout_tail: Mapped[str]
    stderr_tail: Mapped[str]
    digest: Mapped[str]
    head: Mapped[str | None]
    phase: Mapped[str]
    at: Mapped[str]
