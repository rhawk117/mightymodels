"""The `tasks`, `task_attempts` and `task_transitions` tables: a task, who tried it, each move."""

from sqlalchemy.orm import Mapped

from mightymodels_plugin.declarative import Base, Indexed, Key, Serial, Texts


class TaskRow(Base):
    __tablename__ = 'tasks'

    repository_key: Mapped[Key]
    slug: Mapped[Key]
    task_id: Mapped[Key]
    status: Mapped[str]
    owned: Mapped[Texts]
    base: Mapped[str | None]
    commit: Mapped[str | None]
    reasons: Mapped[Texts]
    updated_at: Mapped[str]


class AttemptRow(Base):
    __tablename__ = 'task_attempts'

    id: Mapped[Serial]
    repository_key: Mapped[str]
    slug: Mapped[Indexed]
    task_id: Mapped[str]
    worker: Mapped[str]
    mode: Mapped[str | None]
    at: Mapped[str]


class TransitionRow(Base):
    __tablename__ = 'task_transitions'

    id: Mapped[Serial]
    repository_key: Mapped[str]
    slug: Mapped[Indexed]
    task_id: Mapped[str]
    before: Mapped[str]
    after: Mapped[str]
    reasons: Mapped[Texts]
    head: Mapped[str | None]
    at: Mapped[str]
