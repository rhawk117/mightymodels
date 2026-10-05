"""The tables of `.mightymodels/mightymodels.db` that have not moved to a domain package yet."""

from sqlalchemy.orm import Mapped

from mightymodels_plugin.declarative import Base, Indexed, Key, Models, Serial, Texts, Weights


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
