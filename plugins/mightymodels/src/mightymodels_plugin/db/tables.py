"""The tables of `.mightymodels/mightymodels.db`; deleting the file resets the state."""

from types import MappingProxyType
from typing import Annotated

from sqlalchemy import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

type Models = dict[str, str | None]
type Weights = dict[str, float]
type Texts = list[str]
type Key = Annotated[str, mapped_column(primary_key=True)]
type Serial = Annotated[int, mapped_column(primary_key=True)]
type Indexed = Annotated[str, mapped_column(index=True)]


class Base(DeclarativeBase):
    type_annotation_map = MappingProxyType({Models: JSON, Texts: JSON, Weights: JSON})


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


class TaskRow(Base):
    __tablename__ = 'tasks'

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
    slug: Mapped[Indexed]
    task_id: Mapped[str]
    worker: Mapped[str]
    mode: Mapped[str | None]
    at: Mapped[str]


class TransitionRow(Base):
    __tablename__ = 'task_transitions'

    id: Mapped[Serial]
    slug: Mapped[Indexed]
    task_id: Mapped[str]
    before: Mapped[str]
    after: Mapped[str]
    reasons: Mapped[Texts]
    head: Mapped[str | None]
    at: Mapped[str]


class CommandRow(Base):
    __tablename__ = 'contract_commands'

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


class ReviewRunRow(Base):
    __tablename__ = 'review_runs'

    run_id: Mapped[Key]
    slug: Mapped[str | None]
    scope: Mapped[str]
    base: Mapped[str | None]
    head: Mapped[str | None]
    depth: Mapped[str]
    emphasis: Mapped[str]
    weights: Mapped[Weights]
    personas: Mapped[Texts]
    models: Mapped[Models]
    created_at: Mapped[str]


class ReviewFindingRow(Base):
    __tablename__ = 'review_findings'

    run_id: Mapped[Key]
    finding_id: Mapped[Key]
    sources: Mapped[Texts]
    severity: Mapped[str]
    kind: Mapped[str]
    security: Mapped[bool]
    title: Mapped[str]
    location: Mapped[str]
    fix: Mapped[str]
    verify: Mapped[str]
    evidence_kind: Mapped[str | None]
    evidence_cite: Mapped[str | None]
    conflict: Mapped[str | None]


class ReviewDispositionRow(Base):
    __tablename__ = 'review_dispositions'

    run_id: Mapped[Key]
    finding_id: Mapped[Key]
    decision: Mapped[str]
    reason: Mapped[str]
    by: Mapped[str]
    at: Mapped[str]


class ReviewOutcomeRow(Base):
    __tablename__ = 'review_outcomes'

    run_id: Mapped[Key]
    finding_id: Mapped[Key]
    result: Mapped[str]
    commit: Mapped[str]
    reason: Mapped[str]
    at: Mapped[str]
