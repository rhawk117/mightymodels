"""The `closings` table: one row per closed ticket, holding what the user said as it closed."""

from sqlalchemy.orm import Mapped

from mightymodels_plugin.declarative import Base, Key, Texts


class ClosingRow(Base):
    __tablename__ = 'closings'

    repository_key: Mapped[Key]
    slug: Mapped[Key]
    closed_at: Mapped[str]
    head: Mapped[str | None]
    shipped: Mapped[str]
    pr: Mapped[str | None]
    gotchas: Mapped[Texts]
    archive: Mapped[str]
