from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

TEST_BODY = 'def test_it() -> None:\n    assert True\n'
ROOT = Path('/repo')
ROOT_CONFTEST = Path(__file__).parent.parent.joinpath('conftest.py')


def load_root_conftest() -> ModuleType:
    spec = spec_from_file_location('root_conftest_under_test', ROOT_CONFTEST)
    assert spec
    assert spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT_CONFTEST_MODULE = load_root_conftest()
TIER_NAMES_BY_TREE = ROOT_CONFTEST_MODULE.TIER_NAMES_BY_TREE
get_tier_tree = ROOT_CONFTEST_MODULE.get_tier_tree
has_tier_directory = ROOT_CONFTEST_MODULE.has_tier_directory


@pytest.mark.unit
class TestGetTierTree:
    @pytest.mark.parametrize('tree', sorted(TIER_NAMES_BY_TREE))
    def test_path_under_a_tree_is_located_with_its_relative_parts(self, tree: str) -> None:
        path = ROOT.joinpath('tests', tree, 'concept', 'unit', 'test_a.py')

        assert get_tier_tree(ROOT, path) == (tree, ('concept', 'unit', 'test_a.py'))

    def test_path_outside_every_tree_is_not_located(self) -> None:
        assert get_tier_tree(ROOT, ROOT.joinpath('tests', 'test_tiers.py')) is None


@pytest.mark.unit
class TestHasTierDirectory:
    @pytest.mark.parametrize('tier', ['unit', 'integration', 'smoke'])
    def test_core_tier_directory_is_recognised(self, tier: str) -> None:
        assert has_tier_directory('core', ('concept', tier, 'test_a.py'))

    def test_e2e_belongs_to_mcp_only(self) -> None:
        parts = ('concept', 'e2e', 'test_a.py')

        assert has_tier_directory('mcp', parts)
        assert not has_tier_directory('core', parts)

    def test_module_directly_under_the_concept_has_no_tier(self) -> None:
        assert not has_tier_directory('mcp', ('concept', 'test_a.py'))

    def test_unknown_directory_is_not_a_tier(self) -> None:
        assert not has_tier_directory('mcp', ('concept', 'helpers', 'test_a.py'))


@pytest.mark.integration
class TestMcpTierCollection:
    @pytest.fixture
    def project(self, pytester: pytest.Pytester, request: pytest.FixtureRequest) -> pytest.Pytester:
        root_conftest = request.config.rootpath.joinpath('conftest.py')
        pytester.makeconftest(root_conftest.read_text('utf-8'))
        pytester.makeini('[pytest]\nmarkers =\n    unit: unit tier\n')
        return pytester

    def test_module_outside_a_tier_directory_fails_collection(
        self, project: pytest.Pytester
    ) -> None:
        project.makepyfile(**{'tests/mcp/concept/test_stray': TEST_BODY})

        result = project.runpytest_subprocess()

        assert result.ret == pytest.ExitCode.INTERRUPTED
        result.stdout.fnmatch_lines(['*pytest.UsageError*e2e, integration, smoke, unit*'])

    def test_module_in_a_tier_directory_gets_the_tier_marker(
        self, project: pytest.Pytester
    ) -> None:
        project.makepyfile(**{'tests/mcp/concept/unit/test_tiered': TEST_BODY})

        result = project.runpytest_subprocess('-m', 'unit')

        assert result.ret == pytest.ExitCode.OK
        result.assert_outcomes(passed=1)
