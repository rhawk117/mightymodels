import io
import json

import pytest
from mightymodels_core.primitives import create_routing_table
from mightymodels_hooks.payloads import SessionStartPayload
from mightymodels_hooks.phase_directive import phase_directive
from mightymodels_hooks.session_start import SessionStartHandler
from mightymodels_hooks.workers import PHASE_AGENTS, PLUGIN_PREFIX, create_phase_skills

from tests.core.primitives.clock import create_fake_clock
from tests.hooks.session_start.session_start_builders import NOW

pytestmark = pytest.mark.unit

PHASE_SKILLS = create_phase_skills().skills

BOUNDARY = "End the phase with mightymodels:baton-pass; never invoke the next phase's skill."


def context_of(output: str | None) -> str:
    assert output is not None
    body = json.loads(output)['hookSpecificOutput']
    assert body['hookEventName'] == 'SessionStart'
    return body['additionalContext']


class TestPhaseDirective:
    @pytest.mark.parametrize('source', ['startup', 'clear', 'compact'])
    @pytest.mark.parametrize('phase', PHASE_AGENTS)
    def test_phase_gets_its_skills_and_boundary(self, phase: str, source: str) -> None:
        context = context_of(phase_directive(f'{PLUGIN_PREFIX}{phase}', source))

        assert phase in context
        assert PHASE_SKILLS[phase] in context
        assert BOUNDARY in context

    def test_skills_are_the_agreed_ones(self) -> None:
        assert set(PHASE_SKILLS) == set(PHASE_AGENTS)
        assert 'mightymodels:lets-investigate' in PHASE_SKILLS['investigation']
        assert 'mightymodels:one-shot' in PHASE_SKILLS['planning']
        assert 'mightymodels:stick-the-landing' in PHASE_SKILLS['implementation']
        assert 'mightymodels:review-circus' in PHASE_SKILLS['review']

    @pytest.mark.parametrize('source', ['resume', 'fork', None])
    def test_resume_and_fork_get_nothing(self, source: str | None) -> None:
        assert phase_directive('mightymodels:planning', source) is None

    @pytest.mark.parametrize(
        'agent_type', [None, 'Explore', 'mightymodels:workers:engineer', 'mightymodels:other']
    )
    def test_other_agents_get_nothing(self, agent_type: str | None) -> None:
        assert phase_directive(agent_type, 'startup') is None

    def test_no_worker_name_appears(self) -> None:
        for phase in PHASE_AGENTS:
            context = context_of(phase_directive(f'{PLUGIN_PREFIX}{phase}', 'startup'))

            assert not [name for name in create_routing_table().folders if name in context]


class TestHandlerEmission:
    async def test_directive_is_emitted_when_the_export_fails(self) -> None:
        handler = SessionStartHandler(
            environ={}, stderr=io.StringIO(), clock=create_fake_clock(NOW)
        )
        payload = SessionStartPayload(agent_type='mightymodels:review', source='startup')

        assert 'review' in context_of(await handler.handle(payload))
