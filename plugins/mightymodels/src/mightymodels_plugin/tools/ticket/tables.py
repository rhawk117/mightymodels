"""The `tickets` table: one row per staged ticket."""

from sqlalchemy.orm import Mapped

from mightymodels_plugin.declarative import Base, Key, Models, Texts


class TicketRow(Base):
    __tablename__ = 'tickets'

    slug: Mapped[Key]
    status: Mapped[str]
    ticket: Mapped[str]
    summary: Mapped[str]
    branch: Mapped[str]
    scope: Mapped[str]
    plan_first: Mapped[bool]
    issue: Mapped[int | None]
    jira: Mapped[str | None]
    models: Mapped[Models]
    context: Mapped[Texts]
    investigations: Mapped[Texts]
    validated_at: Mapped[str]
