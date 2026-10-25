from dataclasses import dataclass

import pytest

TEST_BODY = 'def test_it() -> None:\n    assert True\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class TierProject:
    pytester: pytest.Pytester


class TestTierHook:
    @pytest.fixture
    def project(self, pytester: pytest.Pytester, request: pytest.FixtureRequest) -> TierProject:
        root_conftest = request.config.rootpath.joinpath('conftest.py')
        pytester.makeconftest(root_conftest.read_text('utf-8'))
        pytester.makeini('[pytest]\nmarkers =\n    unit: unit tier\n')
        return TierProject(pytester=pytester)

    def write_module(self, project: TierProject, *parts: str) -> None:
        project.pytester.makepyfile(**{'/'.join(parts).removesuffix('.py'): TEST_BODY})

    def test_stray_module_is_a_usage_error_naming_the_tiers(self, project: TierProject) -> None:
        self.write_module(project, 'tests', 'core', 'concept', 'test_stray.py')

        result = project.pytester.runpytest_subprocess()

        assert result.ret == pytest.ExitCode.INTERRUPTED
        result.stdout.fnmatch_lines(['*pytest.UsageError*integration, smoke, unit*'])

    def test_module_in_a_tier_directory_gets_the_tier_marker(self, project: TierProject) -> None:
        self.write_module(project, 'tests', 'core', 'concept', 'unit', 'test_tiered.py')

        result = project.pytester.runpytest_subprocess('-m', 'unit')

        assert result.ret == pytest.ExitCode.OK
        result.assert_outcomes(passed=1)
