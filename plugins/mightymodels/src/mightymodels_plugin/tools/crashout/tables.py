"""The `crashouts` table: one row per journaled crashout, numbered in the order it was added."""

from sqlalchemy.orm import Mapped

from mightymodels_plugin.declarative import Base, Serial, Texts


class CrashoutRow(Base):
    __tablename__ = 'crashouts'

    id: Mapped[Serial]
    at: Mapped[str]
    ticket: Mapped[str | None]
    branch: Mapped[str | None]
    severity: Mapped[str]
    verdict: Mapped[str]
    rant: Mapped[str]
    failures: Mapped[Texts]
    root_cause: Mapped[str]
    corrective_action: Mapped[str]
    barked_back: Mapped[bool]
