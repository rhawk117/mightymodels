from types import MappingProxyType
from typing import get_args

from hypothesis import example, given
from hypothesis import strategies as st
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
    fixed_models = MappingProxyType({
        'code-scout': 'haiku',
        'web-scout': 'haiku',
        'qualitylens': 'haiku',
        'fact-checker': 'haiku',
        'intern': 'haiku',
        'gitty-up': 'haiku',
        'engineer': 'sonnet',
        'terry-toolchain': 'sonnet',
        'architect': 'opus',
        'merge-vader': 'opus',
        'uncle-bob': 'opus',
        'wingman': 'fable',
    })
    efforts = MappingProxyType({
        'haiku': 'high',
        'sonnet': 'medium',
        'opus': 'medium',
        'fable': 'high',
    })
    reviewer_models = MappingProxyType({'quick': 'sonnet', 'standard': 'opus', 'deep': 'opus'})
    agents = st.sampled_from(AGENTS)
    models = st.sampled_from(MODELS)
    depths = st.sampled_from(DEPTHS)

    @given(agent=agents)
    @example(agent='code-scout')
    @example(agent='engineer')
    @example(agent='architect')
    @example(agent='wingman')
    def test_each_agent_has_its_fixed_model(self, agent: AgentName) -> None:
        assert table.fixed_model(agent) == self.fixed_models[agent]

    @given(model=models)
    @example(model='haiku')
    @example(model='sonnet')
    @example(model='opus')
    @example(model='fable')
    def test_effort_per_model(self, model: Model) -> None:
        assert table.effort_of(model) == self.efforts[model]

    @given(depth=depths)
    @example(depth='quick')
    @example(depth='standard')
    @example(depth='deep')
    def test_reviewer_model_per_depth(self, depth: Depth) -> None:
        assert table.reviewer_model(depth) == self.reviewer_models[depth]

    def test_folders_match_the_agents_directories(self) -> None:
        assert table.folders['engineer'] == 'workers'
        assert table.folders['merge-vader'] == 'review'
        assert table.folders['wingman'] == 'triage'

    def test_override_and_default_scope(self) -> None:
        assert table.override_model == 'fable'
        assert table.default_scope == 'med'
