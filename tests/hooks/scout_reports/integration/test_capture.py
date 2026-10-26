from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from tests.hooks.scout_reports.scout_reports_builders import (
    AGENT_ID,
    CLOSING_TEXT,
    CODE_SCOUT,
    REPORT,
    WEB_SCOUT,
    StoredRow,
    handback_payload,
    stop_payload,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tests.hooks.scout_reports.scout_reports_builders import ScoutHarness

OTHER_AGENTS = ('mightymodels:workers:engineer', 'general-purpose', 'code-scout')
BLANK_MESSAGES = (None, '', '   ', 7)
SCOUT_AGENTS = {CODE_SCOUT: 'code-scout', WEB_SCOUT: 'web-scout'}


def scout_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('agent_type', 'scout'), [pytest.param(a, s, id=s) for a, s in SCOUT_AGENTS.items()]
    )


def scout_agent_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'agent_type', [pytest.param(a, id=s) for a, s in SCOUT_AGENTS.items()]
    )


def other_agent_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('agent_type', OTHER_AGENTS)


def blank_message_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('message', [pytest.param(m, id=repr(m)) for m in BLANK_MESSAGES])


class TestHandback:
    @scout_cases()
    async def test_a_handback_lands_one_row_targeted_by_scout_and_agent(
        self, harness: ScoutHarness, agent_type: str, scout: str
    ) -> None:
        output = await harness.hand_back(handback_payload(agent_type))

        assert output is None
        assert harness.rows() == [
            StoredRow(scout=scout, target=f'{scout} {AGENT_ID}', report=REPORT)
        ]
        assert harness.stderr.getvalue() == ''

    async def test_a_handback_without_an_agent_id_is_targeted_by_the_bare_scout(
        self, harness: ScoutHarness
    ) -> None:
        payload = handback_payload(CODE_SCOUT)
        del payload['agent_id']

        await harness.hand_back(payload)

        assert [row.target for row in harness.rows()] == ['code-scout']

    @other_agent_cases()
    async def test_another_agent_type_writes_nothing(
        self, harness: ScoutHarness, agent_type: str
    ) -> None:
        await harness.hand_back(handback_payload(agent_type))

        assert (harness.rows(), harness.stderr.getvalue()) == ([], '')

    @blank_message_cases()
    async def test_a_missing_or_blank_message_writes_nothing_and_says_why(
        self, harness: ScoutHarness, message: object
    ) -> None:
        await harness.hand_back(handback_payload(CODE_SCOUT, message))

        assert harness.rows() == []
        assert 'no report to keep' in harness.stderr.getvalue()


class TestStop:
    @scout_cases()
    async def test_a_stop_with_a_final_message_and_no_handback_lands_one_row(
        self, harness: ScoutHarness, agent_type: str, scout: str
    ) -> None:
        await harness.stop(stop_payload(agent_type))

        assert harness.rows() == [
            StoredRow(scout=scout, target=f'{scout} {AGENT_ID}', report=REPORT)
        ]

    @scout_agent_cases()
    async def test_a_stop_after_a_handback_for_the_same_target_adds_no_row(
        self, harness: ScoutHarness, agent_type: str
    ) -> None:
        await harness.hand_back(handback_payload(agent_type))
        await harness.stop(stop_payload(agent_type, last_assistant_message=CLOSING_TEXT))

        assert [row.report for row in harness.rows()] == [REPORT]

    async def test_a_stop_for_another_agent_id_adds_its_own_row(
        self, harness: ScoutHarness
    ) -> None:
        await harness.hand_back(handback_payload(CODE_SCOUT))
        await harness.stop(stop_payload(CODE_SCOUT, agent_id='c3d4'))

        assert len(harness.rows()) == 2

    async def test_a_stop_for_the_other_scout_adds_its_own_row(self, harness: ScoutHarness) -> None:
        await harness.hand_back(handback_payload(CODE_SCOUT))
        await harness.stop(stop_payload(WEB_SCOUT))

        assert [row.scout for row in harness.rows()] == ['code-scout', 'web-scout']

    @blank_message_cases()
    async def test_a_stop_without_a_final_message_writes_nothing_and_exits_quietly(
        self, harness: ScoutHarness, message: object
    ) -> None:
        output = await harness.stop(stop_payload(CODE_SCOUT, last_assistant_message=message))

        assert (output, harness.rows()) == (None, [])
        assert 'no report to keep' in harness.stderr.getvalue()

    @other_agent_cases()
    async def test_another_agent_type_writes_nothing(
        self, harness: ScoutHarness, agent_type: str
    ) -> None:
        await harness.stop(stop_payload(agent_type))

        assert (harness.rows(), harness.stderr.getvalue()) == ([], '')


class TestFailures:
    async def test_a_refused_redaction_writes_nothing_and_says_why(
        self, harness: ScoutHarness
    ) -> None:
        oversized = 'x' * 60001

        await harness.stop(stop_payload(CODE_SCOUT, last_assistant_message=oversized))

        assert harness.rows() == []
        assert 'subagent-record' in harness.stderr.getvalue()

    async def test_no_git_work_tree_writes_nothing_and_says_why(
        self, harness: ScoutHarness, bare_directory: Path
    ) -> None:
        elsewhere = replace(harness, checkout=bare_directory)

        await elsewhere.hand_back(handback_payload(CODE_SCOUT))

        assert elsewhere.rows() == []
        assert elsewhere.stderr.getvalue().startswith('mightymodels-hooks: subagent-handback:')

    async def test_an_unreadable_database_says_why_and_exits_quietly(
        self, harness: ScoutHarness
    ) -> None:
        harness.data_directory.mkdir()
        harness.data_directory.joinpath('mightymodels.db').write_text('not a database')

        output = await harness.stop(stop_payload(CODE_SCOUT))

        assert output is None
        assert harness.stderr.getvalue().startswith('mightymodels-hooks: subagent-record:')
