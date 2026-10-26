from mcp.server.elicitation import render_elicitation_schema
from mcp_types._v2025_11_25 import BooleanSchema, StringSchema, TitledSingleSelectEnumSchema
from mightymodels_mcp.forms.dispose import (
    PAGE_SIZE,
    REASON_CHOICES,
    ReasonedFinding,
    ReasonsForm,
    create_dispose_pages,
)

from tests.mcp.forms.form_probes import create_finding, create_findings


class TestDisposePages:
    findings = create_findings(PAGE_SIZE + 1)
    pages = create_dispose_pages('Choose the findings to fix', findings)

    def test_eleven_findings_give_a_page_of_ten_then_one(self) -> None:
        assert [len(page.findings) for page in self.pages] == [10, 1]
        assert [page.message for page in self.pages] == [
            'Choose the findings to fix (page 1 of 2)',
            'Choose the findings to fix (page 2 of 2)',
        ]

    def test_each_finding_is_an_unchecked_box(self) -> None:
        schema = render_elicitation_schema(self.pages[0].create_schema())

        boxes = [BooleanSchema.model_validate(box) for box in schema['properties'].values()]
        assert len(boxes) == PAGE_SIZE
        assert all(box.default is False for box in boxes)
        assert 'required' not in schema

    def test_box_names_the_reviewers_severity_and_summary(self) -> None:
        schema = render_elicitation_schema(self.pages[1].create_schema())

        (box,) = (BooleanSchema.model_validate(box) for box in schema['properties'].values())
        assert box.title == 'merge-vader, uncle-bob · High · finding 11 summary'
        assert box.description == 'src/module.py:11 · fix: apply fix 11'

    def test_checked_and_unchecked_findings_are_told_apart(self) -> None:
        page = self.pages[0]
        answers = page.create_schema().model_validate({'finding_2': True, 'finding_5': True})

        checked = page.checked_findings(answers)
        unchecked = page.unchecked_findings(answers)
        assert [finding.key for finding in checked] == ['MV-2', 'MV-5']
        assert len(unchecked) == PAGE_SIZE - 2


class TestReasonsForm:
    form = ReasonsForm(
        message='Say why each finding is not fixed',
        findings=(create_finding(1), create_finding(2, 'Low')),
    )

    def test_each_finding_gets_a_titled_decision_and_a_reason(self) -> None:
        properties = render_elicitation_schema(self.form.create_schema())['properties']

        decision = TitledSingleSelectEnumSchema.model_validate(properties['decision_2'])
        reason = StringSchema.model_validate(properties['reason_2'])
        assert [item.const for item in decision.one_of] == ['defer', 'accept-risk', 'dismiss']
        assert [item.title for item in decision.one_of] == [c.title for c in REASON_CHOICES]
        assert decision.title == 'merge-vader, uncle-bob · Low · finding 2 summary'
        assert reason.title == 'Why: finding 2 summary'
        assert len(properties) == 4

    def test_answers_read_back_per_finding_key(self) -> None:
        answers = self.form.create_schema().model_validate({
            'decision_1': 'defer',
            'reason_1': 'next sprint',
            'decision_2': 'dismiss',
            'reason_2': 'not reachable',
        })

        assert self.form.read(answers) == (
            ReasonedFinding(finding_key='MV-1', decision='defer', reason='next sprint'),
            ReasonedFinding(finding_key='MV-2', decision='dismiss', reason='not reachable'),
        )
