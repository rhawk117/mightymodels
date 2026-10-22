"""Every rule a review start or override is refused by, the reopened findings and the gate.

The caller fetches the run, its findings and its decisions and asks a policy; the policy reads no
repository and no clock, and HEAD and the moment are values passed in. A start is refused for its
target, then its weights, then a quick run whose weights tie. The gate orders findings by severity,
security first, the heaviest source weight, then the key number, and the verdict reads only the
findings still open.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from mightymodels_core.git import revision_error
from mightymodels_core.primitives import RunId
from mightymodels_core.reviews.errors import (
    BaseRequiredError,
    OverrideSpentError,
    PersonaChoiceError,
    SlugRequiredError,
    WeightRangeError,
    WeightsMissingError,
    WeightSumError,
)
from mightymodels_core.reviews.findings import FindingOptions, number_of
from mightymodels_core.reviews.records import ReviewRunRecord
from mightymodels_core.reviews.reports import MergeVaderBasis, PersonaSpec, UncleBobBasis

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence
    from datetime import datetime

    from mightymodels_core.git import UnsafeRevisionError
    from mightymodels_core.primitives import RoutingTable, Slug
    from mightymodels_core.reviews.records import DecidedFinding, FindingRecord, ResolvedFinding
    from mightymodels_core.vocabulary.reviews import (
        Decision,
        Depth,
        Emphasis,
        Persona,
        Result,
        Scope,
    )

type Verdict = Literal['BLOCK', 'MERGE WITH CONDITIONS', 'CLEAR']
type TargetIssue = BaseRequiredError | SlugRequiredError | UnsafeRevisionError
type WeightsIssue = WeightsMissingError | WeightRangeError | WeightSumError
type StartIssue = TargetIssue | WeightsIssue | PersonaChoiceError
type Presets = dict[Emphasis, dict[str, float]]
type SourcePersonas = dict[str, Persona]
type PersonaSpecs = dict[Persona, PersonaSpec]


def create_persona_specs() -> PersonaSpecs:
    return {
        'merge-vader': PersonaSpec(
            prefix='MV',
            parser=MergeVaderBasis(),
            weights={'release-readiness': 0.7, 'maintainability': 0.3, 'balanced': 0.5},
        ),
        'uncle-bob': PersonaSpec(
            prefix='UB',
            parser=UncleBobBasis(),
            weights={'release-readiness': 0.3, 'maintainability': 0.7, 'balanced': 0.5},
        ),
    }


def persona_of_source(source: str, personas: SourcePersonas) -> Persona:
    return personas[source.partition('-')[0]]


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewOptions:
    standard_threshold: float = 0.25
    weight_tolerance: float = 0.001
    run_id_format: str = '%Y%m%d-%H%M%S'
    personas: tuple[Persona, ...] = ('merge-vader', 'uncle-bob')
    scopes_needing_base: tuple[Scope, ...] = ('branch', 'ticket')
    closed_by_decision: tuple[Decision, ...] = ('dismiss',)
    specs: PersonaSpecs = field(default_factory=create_persona_specs)

    @property
    def presets(self) -> Presets:
        emphases: tuple[Emphasis, ...] = ('release-readiness', 'maintainability', 'balanced')
        return {e: {name: spec.weights[e] for name, spec in self.specs.items()} for e in emphases}

    @property
    def source_personas(self) -> SourcePersonas:
        return {spec.prefix: name for name, spec in self.specs.items()}

    @property
    def findings(self) -> FindingOptions:
        return FindingOptions(source_prefixes=tuple(s.prefix for s in self.specs.values()))


@dataclass(slots=True, kw_only=True, frozen=True)
class StartRequest:
    scope: Scope
    base: str | None
    slug: Slug | None
    depth: Depth
    emphasis: Emphasis
    weights: Mapping[str, float] | None = None
    persona: Persona | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class StartPolicy:
    request: StartRequest
    routing: RoutingTable
    options: ReviewOptions = field(default_factory=ReviewOptions)

    @property
    def needs_base(self) -> bool:
        return self.request.scope in self.options.scopes_needing_base

    @property
    def weights(self) -> dict[str, float]:
        if self.request.emphasis == 'custom':
            return dict(self.request.weights or {})

        return dict(self.options.presets[self.request.emphasis])

    @property
    def leaders(self) -> list[Persona]:
        weights = self.weights
        heaviest = max(weights.values())
        return [persona for persona in self.options.personas if weights[persona] == heaviest]

    @property
    def personas(self) -> list[Persona]:
        if self.request.depth == 'deep':
            return list(self.options.personas)

        if self.request.depth == 'standard':
            weights = self.weights
            floor = self.options.standard_threshold
            return [persona for persona in self.options.personas if weights[persona] >= floor]

        if self.request.persona is not None:
            return [self.request.persona]

        return self.leaders[:1]

    @property
    def reviewer_models(self) -> dict[str, str]:
        model = self.routing.reviewer_model(self.request.depth)
        return dict.fromkeys(self.personas, model)

    def get_target_problem(self) -> TargetIssue | None:
        request = self.request
        if self.needs_base and request.base is None:
            return BaseRequiredError(scope=request.scope)

        if request.scope == 'ticket' and request.slug is None:
            return SlugRequiredError()

        if request.base is None:
            return None

        return revision_error(request.base)

    def get_weights_problem(self) -> WeightsIssue | None:
        if self.request.emphasis != 'custom':
            return None

        weights = self.request.weights
        if weights is None:
            return WeightsMissingError()

        if set(weights) != set(self.options.personas):
            return WeightRangeError()

        if not all(0 <= weight <= 1 for weight in weights.values()):
            return WeightRangeError()

        if abs(sum(weights.values()) - 1) > self.options.weight_tolerance:
            return WeightSumError()

        return None

    def get_persona_problem(self) -> PersonaChoiceError | None:
        if self.request.depth != 'quick' or self.request.persona is not None:
            return None

        if len(self.leaders) > 1:
            return PersonaChoiceError()

        return None

    def get_start_problem(self) -> StartIssue | None:
        return self.get_target_problem() or self.get_weights_problem() or self.get_persona_problem()

    def record_for(self, head: str | None, moment: datetime) -> ReviewRunRecord:
        request = self.request
        return ReviewRunRecord(
            run_id=RunId(moment.strftime(self.options.run_id_format)),
            slug=request.slug,
            scope=request.scope,
            base=request.base,
            head=head,
            depth=request.depth,
            emphasis=request.emphasis,
            weights=self.weights,
            personas=tuple(self.personas),
            models=self.reviewer_models,
            created_at=moment,
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class OverridePolicy:
    run: ReviewRunRecord
    routing: RoutingTable

    @property
    def is_spent(self) -> bool:
        return self.routing.override_model in self.run.models.values()

    @property
    def heavier_persona(self) -> str:
        return max(self.run.personas, key=self.run.weights.__getitem__)

    @property
    def overridden_models(self) -> dict[str, str | None]:
        return {**self.run.models, self.heavier_persona: self.routing.override_model}

    def get_override_problem(self) -> OverrideSpentError | None:
        if self.is_spent:
            return OverrideSpentError(run=self.run.run_id)

        return None


def reopened_keys(
    recorded: Sequence[FindingRecord], changed: Sequence[FindingRecord], decided: Collection[str]
) -> list[str]:
    held = {finding.key: finding for finding in recorded}
    return [
        finding.key
        for finding in changed
        if finding.key in decided and held.get(finding.key) != finding
    ]


@dataclass(slots=True, kw_only=True, frozen=True)
class GatePolicy:
    weights: Mapping[str, float]
    decisions: Mapping[str, Decision]
    results: Mapping[str, Result]
    options: ReviewOptions = field(default_factory=ReviewOptions)

    def decision_of(self, finding: FindingRecord) -> Decision | None:
        return self.decisions.get(finding.key)

    def is_open(self, finding: FindingRecord) -> bool:
        if self.results.get(finding.key) == 'fixed':
            return False

        return self.decision_of(finding) not in self.options.closed_by_decision

    def is_blocking(self, finding: FindingRecord) -> bool:
        if finding.severity == 'Critical':
            return True

        return finding.severity == 'High' and self.decision_of(finding) != 'accept-risk'

    def heaviest_weight(self, finding: FindingRecord) -> float:
        table = self.options.source_personas
        personas = (persona_of_source(source, table) for source in finding.sources)
        return max(self.weights.get(persona, 0) for persona in personas)

    def gate_key(self, finding: FindingRecord) -> tuple[int, bool, float, int]:
        rank = self.options.findings.rank(finding.severity)
        return rank, not finding.security, -self.heaviest_weight(finding), number_of(finding)

    def ordered(self, findings: Sequence[FindingRecord]) -> list[FindingRecord]:
        return sorted(findings, key=self.gate_key)

    def verdict_of(self, findings: Sequence[FindingRecord]) -> Verdict:
        remaining = [finding for finding in findings if self.is_open(finding)]
        if any(map(self.is_blocking, remaining)):
            return 'BLOCK'

        conditions_rank = self.options.findings.rank('Medium')
        if any(self.options.findings.rank(item.severity) <= conditions_rank for item in remaining):
            return 'MERGE WITH CONDITIONS'

        return 'CLEAR'


def create_gate_policy(
    run: ReviewRunRecord,
    dispositions: Sequence[DecidedFinding],
    outcomes: Sequence[ResolvedFinding],
) -> GatePolicy:
    return GatePolicy(
        weights=run.weights,
        decisions={decided.finding_key: decided.decision for decided in dispositions},
        results={resolved.finding_key: resolved.result for resolved in outcomes},
    )
