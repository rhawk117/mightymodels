import pytest
from mightymodels_core.similarity import IncomingReport
from mightymodels_hooks.payloads import PostToolUsePayload
from mightymodels_hooks.scout_reports import (
    NoReportError,
    handback_message_of,
    scout_report_of,
)

from tests.hooks.scout_reports.scout_reports_builders import (
    AGENT_ID,
    CODE_SCOUT,
    REPORT,
    handback_event,
    stop_event,
)

NAME_LIMIT = 255


def missing_agent_id_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('agent_id', [pytest.param(None, id='none'), ''])


def blank_report_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('report', [None, '', '  \n'])


def other_agent_type_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('agent_type', ['mightymodels:workers:engineer', 'code-scout'])


def non_text_message_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('message', [None, 7, ['text']])


class TestScoutReportOf:
    def test_a_scout_report_is_targeted_by_scout_and_agent_id(self) -> None:
        incoming = scout_report_of(stop_event(CODE_SCOUT), REPORT)

        assert incoming == IncomingReport(
            scout='code-scout', target=f'code-scout {AGENT_ID}', report=REPORT
        )

    @missing_agent_id_cases()
    def test_without_an_agent_id_the_target_is_the_bare_scout(self, agent_id: object) -> None:
        incoming = scout_report_of(stop_event(CODE_SCOUT, agent_id=agent_id), REPORT)

        assert isinstance(incoming, IncomingReport)
        assert incoming.target == 'code-scout'

    def test_a_long_agent_id_is_cut_to_the_name_limit(self) -> None:
        incoming = scout_report_of(stop_event(CODE_SCOUT, agent_id='z' * 400), REPORT)

        assert isinstance(incoming, IncomingReport)
        assert len(incoming.target) == NAME_LIMIT

    @blank_report_cases()
    def test_a_missing_or_blank_report_is_no_report(self, report: str | None) -> None:
        assert isinstance(scout_report_of(stop_event(CODE_SCOUT), report), NoReportError)

    @other_agent_type_cases()
    def test_another_agent_type_is_none(self, agent_type: str) -> None:
        assert scout_report_of(stop_event(agent_type), REPORT) is None


class TestHandbackMessageOf:
    def test_it_reads_the_tool_input_message(self) -> None:
        assert handback_message_of(handback_event(CODE_SCOUT)) == REPORT

    @non_text_message_cases()
    def test_a_message_that_is_not_text_is_none(self, message: object) -> None:
        assert handback_message_of(handback_event(CODE_SCOUT, message)) is None

    def test_a_payload_without_tool_input_has_no_message(self) -> None:
        assert handback_message_of(PostToolUsePayload()) is None
