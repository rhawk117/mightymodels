"""Dispose pages and the reasons form: how the user decides a review's findings.

A dispose page shows at most ten findings, one unchecked box each; a checked finding is fixed.
Each finding left unchecked then gets a reasons form entry: whether to defer, accept the risk or
dismiss it, and why. Finding keys need not be valid identifiers, so a form's fields are named by
the finding's position on its page and the form maps each field back to its finding.
"""

from dataclasses import dataclass
from itertools import batched
from typing import TYPE_CHECKING, Any, Literal

from mcp.server.mcpserver.resolve import Elicit
from pydantic import BaseModel, Field, create_model

from .choices import Choice, ChoiceQuestion

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mightymodels_core.reviews.records import FindingRecord

PAGE_SIZE = 10
PAGE_MODEL_NAME = 'DisposePage'
REASONS_MODEL_NAME = 'DisposeReasons'
LABEL_SEPARATOR = ' · '
REASON_CHOICES = (
    Choice(value='defer', title='Defer'),
    Choice(value='accept-risk', title='Accept the risk'),
    Choice(value='dismiss', title='Dismiss'),
)

type ReasonedDecision = Literal['defer', 'accept-risk', 'dismiss']


def label_finding(finding: FindingRecord) -> str:
    reviewers = ', '.join(finding.sources)
    return LABEL_SEPARATOR.join((reviewers, finding.severity, finding.title))


def describe_finding(finding: FindingRecord) -> str:
    return f'{finding.location}{LABEL_SEPARATOR}fix: {finding.fix}'


def name_finding_fields(prefix: str, findings: tuple[FindingRecord, ...]) -> tuple[str, ...]:
    return tuple(f'{prefix}_{position}' for position in range(1, len(findings) + 1))


@dataclass(slots=True, kw_only=True, frozen=True)
class DisposePage:
    message: str
    findings: tuple[FindingRecord, ...]

    @property
    def field_names(self) -> tuple[str, ...]:
        return name_finding_fields('finding', self.findings)

    def create_schema(self) -> type[BaseModel]:
        fields: dict[str, Any] = {
            name: (
                bool,
                Field(
                    default=False,
                    title=label_finding(finding),
                    description=describe_finding(finding),
                ),
            )
            for name, finding in zip(self.field_names, self.findings, strict=True)
        }
        return create_model(PAGE_MODEL_NAME, __base__=BaseModel, **fields)

    def ask(self) -> Elicit[BaseModel]:
        return Elicit(self.message, self.create_schema())

    def checked_findings(self, answers: BaseModel) -> tuple[FindingRecord, ...]:
        return tuple(finding for finding, ticked in self.answered(answers) if ticked)

    def unchecked_findings(self, answers: BaseModel) -> tuple[FindingRecord, ...]:
        return tuple(finding for finding, ticked in self.answered(answers) if not ticked)

    def answered(self, answers: BaseModel) -> tuple[tuple[FindingRecord, bool], ...]:
        pairs = zip(self.field_names, self.findings, strict=True)
        return tuple((finding, getattr(answers, name) is True) for name, finding in pairs)


def create_dispose_pages(
    message: str, findings: Iterable[FindingRecord]
) -> tuple[DisposePage, ...]:
    chunks = tuple(batched(findings, PAGE_SIZE, strict=False))
    total = len(chunks)
    return tuple(
        DisposePage(message=f'{message} (page {number} of {total})', findings=chunk)
        for number, chunk in enumerate(chunks, start=1)
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ReasonedFinding:
    finding_key: str
    decision: ReasonedDecision
    reason: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ReasonsForm:
    message: str
    findings: tuple[FindingRecord, ...]

    @property
    def decision_names(self) -> tuple[str, ...]:
        return name_finding_fields('decision', self.findings)

    @property
    def reason_names(self) -> tuple[str, ...]:
        return name_finding_fields('reason', self.findings)

    def create_decision_question(self, name: str, finding: FindingRecord) -> ChoiceQuestion:
        return ChoiceQuestion(
            argument=name,
            title=label_finding(finding),
            description=describe_finding(finding),
            choices=REASON_CHOICES,
        )

    def create_schema(self) -> type[BaseModel]:
        fields: dict[str, Any] = {}
        entries = zip(self.decision_names, self.reason_names, self.findings, strict=True)
        for decision_name, reason_name, finding in entries:
            question = self.create_decision_question(decision_name, finding)
            fields[decision_name] = question.create_field()
            fields[reason_name] = (str, Field(min_length=1, title=f'Why: {finding.title}'))

        return create_model(REASONS_MODEL_NAME, __base__=BaseModel, **fields)

    def ask(self) -> Elicit[BaseModel]:
        return Elicit(self.message, self.create_schema())

    def read(self, answers: BaseModel) -> tuple[ReasonedFinding, ...]:
        entries = zip(self.decision_names, self.reason_names, self.findings, strict=True)
        return tuple(
            ReasonedFinding(
                finding_key=finding.key,
                decision=getattr(answers, decision_name),
                reason=getattr(answers, reason_name),
            )
            for decision_name, reason_name, finding in entries
        )
