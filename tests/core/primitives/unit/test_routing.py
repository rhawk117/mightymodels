from typing import get_args

import pytest
from mightymodels_core.primitives import (
    AgentFolder,
    AgentName,
    Effort,
    Model,
    create_routing_table,
)
from mightymodels_core.schemas.reviews import Depth

AGENTS = get_args(AgentName.__value__)
MODELS = get_args(Model.__value__)
DEPTHS = get_args(Depth.__value__)
table = create_routing_table()


class TestCoverage:
    def test_folders_cover_every_agent(self) -> None:
        assert set(table.folders) == set(AGENTS)
        assert set(table.folders.values()) <= set(get_args(AgentFolder.__value__))

    def test_models_cover_every_agent(self) -> None:
        assert set(table.models) == set(AGENTS)
        assert set(table.models.values()) <= set(MODELS)

    def test_efforts_cover_every_model(self) -> None:
        assert set(table.efforts) == set(MODELS)
        assert set(table.efforts.values()) <= set(get_args(Effort.__value__))

    def test_depth_models_cover_every_depth(self) -> None:
        assert set(table.depth_models) == set(DEPTHS)


class TestValues:
    @pytest.mark.parametrize(
        ('model', 'agents'),
        [
            (
                'haiku',
                ['code-scout', 'web-scout', 'qualitylens', 'fact-checker', 'intern', 'gitty-up'],
            ),
            ('sonnet', ['engineer', 'terry-toolchain']),
            ('opus', ['architect', 'merge-vader', 'uncle-bob']),
            ('fable', ['wingman']),
        ],
    )
    def test_each_agent_has_its_fixed_model(self, model: Model, agents: list[AgentName]) -> None:
        assert [table.fixed_model(agent) for agent in agents] == [model] * len(agents)

    @pytest.mark.parametrize(
        ('model', 'effort'),
        [('haiku', 'high'), ('sonnet', 'medium'), ('opus', 'medium'), ('fable', 'high')],
    )
    def test_effort_per_model(self, model: Model, effort: Effort) -> None:
        assert table.effort_of(model) == effort

    @pytest.mark.parametrize(
        ('depth', 'model'), [('quick', 'sonnet'), ('standard', 'opus'), ('deep', 'opus')]
    )
    def test_reviewer_model_per_depth(self, depth: Depth, model: Model) -> None:
        assert table.reviewer_model(depth) == model

    def test_folders_match_the_agents_directories(self) -> None:
        assert table.folders['engineer'] == 'workers'
        assert table.folders['merge-vader'] == 'review'
        assert table.folders['wingman'] == 'triage'

    def test_override_and_default_scope(self) -> None:
        assert table.override_model == 'fable'
        assert table.default_scope == 'med'
