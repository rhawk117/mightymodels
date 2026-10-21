"""The persona report parser: each persona's findings read field for field, each shape refused."""

from dataclasses import dataclass
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.reviews import (
    EvidenceKindError,
    ForeignSourceError,
    IncomingEvidence,
    IncomingFinding,
    NoFindingsSectionError,
    UnknownDimensionError,
    UnknownSeverityHeadingError,
    UnplacedFindingError,
    UnreadableHeadingError,
    parse_report,
)
from mightymodels_core.reviews.policy.review import create_persona_specs

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.reviews import Persona
    from mightymodels_core.schemas.reviews import FindingKind


def merge_vader_report(*blocks: str, severity: str = 'High') -> str:
    return (
        '# Review\n\n## Findings\n\n'
        + f'### {severity}\n\n'
        + '\n'.join(blocks)
        + '\n\n## Verdict\n'
    )


def merge_vader_block(
    *, dimension: str = 'security', evidence: str = 'Evidence: `src/a.py:10` unchecked'
) -> str:
    return dedent(f"""\
        #### MV-1 | {dimension} | Unchecked input
        - {evidence}
        - Fix: check it
          before use
        - Verify: run the tests
        """)


def uncle_bob_block() -> str:
    return dedent("""\
        #### UB-1 | [SRP] Mixed duties \u2014 `src/b.py:5-9`
        - Evidence (metric): fan-out 14
        - Fix: split it
        - Verify: run the tests
        """)


def read_report(text: str, persona: Persona) -> list[IncomingFinding]:
    return parse_report(text, persona, create_persona_specs())


@dataclass(slots=True, kw_only=True, frozen=True)
class DimensionCase:
    name: str
    dimension: str
    kind: FindingKind
    security: bool

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def dimension_cases() -> pytest.MarkDecorator:
    cases = [
        DimensionCase(name='security', dimension='security', kind='defect', security=True),
        DimensionCase(name='sdlc', dimension='SDLC', kind='defect', security=False),
        DimensionCase(name='docs', dimension='docs', kind='defect', security=False),
        DimensionCase(name='plan', dimension='plan', kind='defect', security=False),
        DimensionCase(name='quality', dimension='quality', kind='quality', security=False),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


class TestParseReport:
    def parse_merge_vader(self, *blocks: str, severity: str = 'High') -> list[IncomingFinding]:
        return read_report(merge_vader_report(*blocks, severity=severity), 'merge-vader')

    def test_merge_vader_finding_is_read_field_for_field(self) -> None:
        findings = self.parse_merge_vader(merge_vader_block())

        assert findings == [
            IncomingFinding(
                sources=('MV-1',),
                severity='High',
                kind='defect',
                security=True,
                title='Unchecked input',
                location='src/a.py:10',
                fix='check it before use',
                verify='run the tests',
                evidence=None,
            )
        ]

    def test_uncle_bob_finding_is_read_field_for_field(self) -> None:
        report = merge_vader_report(uncle_bob_block(), severity='Medium')

        findings = read_report(report, 'uncle-bob')

        assert findings == [
            IncomingFinding(
                sources=('UB-1',),
                severity='Medium',
                kind='quality',
                security=False,
                title='Mixed duties',
                location='src/b.py:5-9',
                fix='split it',
                verify='run the tests',
                evidence=IncomingEvidence(kind='metric', cite='fan-out 14'),
            )
        ]

    @dimension_cases()
    def test_dimension_sets_kind_and_security(self, case: DimensionCase) -> None:
        [finding] = self.parse_merge_vader(merge_vader_block(dimension=case.dimension))

        assert (finding.kind, finding.security) == (case.kind, case.security)

    def test_uncle_bob_heading_without_location_leaves_it_empty(self) -> None:
        block = '#### UB-2 | Mixed duties\n'

        [finding] = read_report(merge_vader_report(block), 'uncle-bob')

        assert finding.location == ''

    def test_typed_evidence_kind_is_case_insensitive(self) -> None:
        block = merge_vader_block(evidence='Evidence (Idiom): prefer a guard')

        [finding] = self.parse_merge_vader(block)

        assert finding.evidence == IncomingEvidence(kind='idiom', cite='prefer a guard')

    def test_each_block_is_read_under_its_own_severity(self) -> None:
        report = (
            '## Findings\n### Low\n#### MV-1 | sdlc | One\n### blocker\n#### MV-2 | sdlc | Two\n'
        )

        findings = read_report(report, 'merge-vader')

        assert [finding.severity for finding in findings] == ['Low', 'Blocker']

    def test_only_the_findings_section_is_read(self) -> None:
        report = (
            '## Summary\n#### not a finding\n## Findings\n### High\n## Verdict\n#### MV-9 | x\n'
        )

        assert read_report(report, 'merge-vader') == []


class TestRefusedReports:
    def refusal(self, report: str, persona: Persona = 'merge-vader') -> Exception:
        with pytest.raises(Exception, match='nothing was written') as caught:
            read_report(report, persona)
        return caught.value

    def test_report_without_a_findings_section_is_refused(self) -> None:
        assert isinstance(self.refusal('# Review\n## Verdict\n'), NoFindingsSectionError)

    def test_unknown_severity_heading_is_refused(self) -> None:
        error = self.refusal('## Findings\n### Urgent\n')

        assert isinstance(error, UnknownSeverityHeadingError)
        assert error.heading == '### Urgent'

    def test_finding_before_any_severity_is_refused(self) -> None:
        error = self.refusal('## Findings\n#### MV-1 | sdlc | Early\n')

        assert isinstance(error, UnplacedFindingError)
        assert error.heading == '#### MV-1 | sdlc | Early'

    def test_unreadable_finding_heading_is_refused(self) -> None:
        error = self.refusal('## Findings\n### High\n#### Early thoughts\n')

        assert isinstance(error, UnreadableHeadingError)
        assert error.heading == '#### Early thoughts'

    def test_merge_vader_heading_without_a_dimension_is_refused(self) -> None:
        error = self.refusal('## Findings\n### High\n#### MV-1 | Unchecked input\n')

        assert isinstance(error, UnreadableHeadingError)
        assert error.heading == '#### MV-1 | Unchecked input'

    def test_unknown_dimension_is_refused(self) -> None:
        report = merge_vader_report(merge_vader_block(dimension='Style'))

        error = self.refusal(report)

        assert isinstance(error, UnknownDimensionError)
        assert (error.index, error.sources, error.dimension) == (0, ('MV-1',), 'style')

    def test_id_outside_the_personas_prefix_is_refused(self) -> None:
        error = self.refusal(merge_vader_report(uncle_bob_block()))

        assert isinstance(error, ForeignSourceError)
        assert (error.index, error.sources, error.persona) == (0, ('UB-1',), 'merge-vader')

    def test_unknown_evidence_kind_is_refused_as_written(self) -> None:
        block = merge_vader_block(evidence='Evidence (Vibes): feels off')
        report = merge_vader_report(merge_vader_block(), block.replace('MV-1', 'MV-2'))

        error = self.refusal(report)

        assert isinstance(error, EvidenceKindError)
        assert (error.index, error.sources, error.kind) == (1, ('MV-2',), 'Vibes')
