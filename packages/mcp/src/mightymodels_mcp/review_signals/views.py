"""The review_signals results: the analysis names, each signal and the report that carries them."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

type Analysis = Literal['code-churn', 'change-coupling', 'code-hotspots']


class ScannedHistory(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    since: str | None
    baseline_ref: str | None
    max_commits: int | None
    commits_scanned: int
    truncated: bool


class Report[Signal](BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    analysis: Analysis
    target: str
    history: ScannedHistory
    signals: list[Signal]
    limitations: list[str]


class ChurnSignal(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    subject: str
    commits: int
    lines_added: int
    lines_deleted: int


class CouplingSignal(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    subject: str
    shared_commits: int
    degree: float


class HotspotSignal(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    subject: str
    commits: int
    loc: int
    indentation: int
    hotspot: int
