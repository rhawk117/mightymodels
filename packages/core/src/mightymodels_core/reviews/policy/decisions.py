"""Every rule a disposition or a fix outcome is refused by.

The caller fetches the run's finding keys and the finding's disposition and asks a policy; the
policy reads no repository and no clock, and the moment is a value passed in. A disposition batch is
refused for a finding the run does not hold, then for a decision that needs a reason and has none.
An outcome is refused for an unknown finding, then for a finding the user did not choose to fix,
then for a commit that is not a plain revision, a fixed result with no commit, and a failed or
blocked result with no reason.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.git import revision_error
from mightymodels_core.primitives import redact_within
from mightymodels_core.reviews.errors import (
    CommitRequiredError,
    NotChosenError,
    ReasonRequiredError,
    ResultReasonError,
    UnknownFindingError,
)
from mightymodels_core.reviews.records import DecidedFinding, ResolvedFinding

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping
    from datetime import datetime

    from mightymodels_core.git import UnsafeRevisionError
    from mightymodels_core.primitives import RunId
    from mightymodels_core.schemas.reviews import Decision, Result

type DisposeIssue = UnknownFindingError | ReasonRequiredError
type ChoiceIssue = UnknownFindingError | NotChosenError
type ResultIssue = UnsafeRevisionError | CommitRequiredError | ResultReasonError
type ResolveIssue = ChoiceIssue | ResultIssue


@dataclass(slots=True, kw_only=True, frozen=True)
class DecisionOptions:
    reason_decisions: tuple[Decision, ...] = ('accept-risk', 'dismiss')
    chosen_decision: Decision = 'fix'
    fixed_result: Result = 'fixed'
    prose_limit: int = 4000
    name_limit: int = 255


@dataclass(slots=True, kw_only=True, frozen=True)
class IncomingDisposition:
    decision: Decision
    reason: str = ''


@dataclass(slots=True, kw_only=True, frozen=True)
class ResolveRequest:
    finding_key: str
    result: Result
    commit: str | None = None
    reason: str | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class DisposePolicy:
    run: RunId
    finding_keys: Collection[str]
    decisions: Mapping[str, IncomingDisposition]
    options: DecisionOptions = field(default_factory=DecisionOptions)

    @property
    def unknown_key(self) -> str | None:
        return next((key for key in self.decisions if key not in self.finding_keys), None)

    @property
    def reasonless_key(self) -> str | None:
        return next(
            (key for key, entry in self.decisions.items() if self.lacks_reason(entry)), None
        )

    def lacks_reason(self, entry: IncomingDisposition) -> bool:
        return entry.decision in self.options.reason_decisions and not entry.reason.strip()

    def get_dispose_problem(self) -> DisposeIssue | None:
        if (unknown := self.unknown_key) is not None:
            return UnknownFindingError(run=self.run, finding_key=unknown)

        if (reasonless := self.reasonless_key) is not None:
            decision = self.decisions[reasonless].decision
            return ReasonRequiredError(finding_key=reasonless, decision=decision)

        return None

    def decided_for(self, key: str, by: str, at: datetime) -> DecidedFinding:
        entry = self.decisions[key]
        reason = redact_within(entry.reason.strip(), 'reason', self.options.prose_limit)
        return DecidedFinding(
            finding_key=key,
            decision=entry.decision,
            reason=reason,
            by=redact_within(by, 'by', self.options.name_limit),
            at=at,
        )

    def decided_records(self, by: str, at: datetime) -> list[DecidedFinding]:
        return [self.decided_for(key, by, at) for key in self.decisions]


@dataclass(slots=True, kw_only=True, frozen=True)
class ResolvePolicy:
    run: RunId
    request: ResolveRequest
    finding_keys: Collection[str]
    chosen: DecidedFinding | None
    options: DecisionOptions = field(default_factory=DecisionOptions)

    @property
    def is_fixed(self) -> bool:
        return self.request.result == self.options.fixed_result

    @property
    def is_chosen(self) -> bool:
        return self.chosen is not None and self.chosen.decision == self.options.chosen_decision

    @property
    def has_reason(self) -> bool:
        return bool(self.request.reason and self.request.reason.strip())

    def get_choice_problem(self) -> ChoiceIssue | None:
        key = self.request.finding_key
        if key not in self.finding_keys:
            return UnknownFindingError(run=self.run, finding_key=key)

        if not self.is_chosen:
            return NotChosenError(finding_key=key)

        return None

    def get_result_problem(self) -> ResultIssue | None:
        key = self.request.finding_key
        if self.request.commit is not None and (unsafe := revision_error(self.request.commit)):
            return unsafe

        if self.is_fixed and self.request.commit is None:
            return CommitRequiredError(finding_key=key)

        if not self.is_fixed and not self.has_reason:
            return ResultReasonError(finding_key=key, result=self.request.result)

        return None

    def get_resolve_problem(self) -> ResolveIssue | None:
        return self.get_choice_problem() or self.get_result_problem()

    def resolved_at(self, at: datetime) -> ResolvedFinding:
        reason = redact_within(
            (self.request.reason or '').strip(), 'reason', self.options.prose_limit
        )
        return ResolvedFinding(
            finding_key=self.request.finding_key,
            result=self.request.result,
            commit=self.request.commit or '',
            reason=reason,
            at=at,
        )
