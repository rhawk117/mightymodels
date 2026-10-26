from typing import TYPE_CHECKING

import pytest
from mightymodels_core.similarity import IncomingReport
from mightymodels_hooks.scout_reports import (
    NoReportError,
    handback_message_of,
    scout_report_of,
)

from tests.hooks.scout_reports.scout_reports_builders import (
    AGENT_ID,
    CODE_SCOUT,
    REPORT,
    handback_payload,
    stop_payload,
)

if TYPE_CHECKING:
    from mightymodels_hooks.cli import HookPayload

NAME_LIMIT = 255


def missing_agent_id_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('agent_id', [pytest.param(None, id='none'), ''])


class TestScoutReportOf:
    def test_a_scout_report_is_targeted_by_scout_and_agent_id(self) -> None:
        incoming = scout_report_of(stop_payload(CODE_SCOUT), REPORT)

        assert incoming == IncomingReport(
            scout='code-scout', target=f'code-scout {AGENT_ID}', report=REPORT
        )

    @missing_agent_id_cases()
    def test_without_an_agent_id_the_target_is_the_bare_scout(self, agent_id: object) -> None:
        incoming = scout_report_of(stop_payload(CODE_SCOUT, agent_id=agent_id), REPORT)

        assert isinstance(incoming, IncomingReport)
        assert incoming.target == 'code-scout'

    def test_a_long_agent_id_is_cut_to_the_name_limit(self) -> None:
        incoming = scout_report_of(stop_payload(CODE_SCOUT, agent_id='z' * 400), REPORT)

        assert isinstance(incoming, IncomingReport)
        assert len(incoming.target) == NAME_LIMIT

    @pytest.mark.parametrize('report', [None, '', '  \n', 3])
    def test_a_missing_or_blank_report_is_no_report(self, report: object) -> None:
        assert isinstance(scout_report_of(stop_payload(CODE_SCOUT), report), NoReportError)

    @pytest.mark.parametrize('agent_type', ['mightymodels:workers:engineer', 'code-scout', 7])
    def test_another_agent_type_is_none(self, agent_type: object) -> None:
        payload: HookPayload = {**stop_payload(CODE_SCOUT), 'agent_type': agent_type}

        assert scout_report_of(payload, REPORT) is None


class TestHandbackMessageOf:
    def test_it_reads_the_tool_input_message(self) -> None:
        assert handback_message_of(handback_payload(CODE_SCOUT)) == REPORT

    @pytest.mark.parametrize('tool_input', [None, 'text', [1]])
    def test_a_tool_input_that_is_not_an_object_has_no_message(self, tool_input: object) -> None:
        payload: HookPayload = handback_payload(CODE_SCOUT, tool_input=tool_input)

        assert handback_message_of(payload) is None
