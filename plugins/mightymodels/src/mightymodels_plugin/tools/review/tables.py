"""The `review_runs`, `review_findings`, `review_dispositions` and `review_outcomes` tables.

A run, the findings recorded for it, the user's decision per finding and the outcome of each fix.
"""

from sqlalchemy.orm import Mapped

from mightymodels_plugin.declarative import Base, Key, Models, Texts, Weights


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
