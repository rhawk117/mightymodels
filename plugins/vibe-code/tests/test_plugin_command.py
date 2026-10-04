import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from vibe_code_cli.cli import main
from vibe_code_cli.plugin.kinds import Kinds
from vibe_code_cli.plugin.tests.support import EXAMPLE, PlanFiles, component, errors_of, validate


class TestUsage:
    def test_validate_help_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['plugin', 'validate', '--help'])

        assert exit_info.value.code == 0
        assert 'PLAN' in capsys.readouterr().out

    def test_plugin_without_a_command_prints_usage_and_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['plugin']) == 2
        assert 'usage: vibe-code' in capsys.readouterr().err


class TestValidPlan:
    EXAMPLE_KINDS = frozenset({'hook', 'skill', 'agent', 'lsp'})

    def test_a_valid_plan_passes(
        self, plugin_plans: PlanFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate(plugin_plans.write(), '--strict') == 0
        assert 'PASS' in capsys.readouterr().out

    def test_pp_a47_the_shipped_example_passes_strict(self) -> None:
        assert validate(EXAMPLE, '--strict') == 0
        kinds = {item['kind'] for item in json.loads(EXAMPLE.read_text())['components']}
        assert kinds >= self.EXAMPLE_KINDS


class TestKindTable:
    EIGHT_KINDS = frozenset(
        {'skill', 'command', 'agent', 'hook', 'mcp', 'lsp', 'executable', 'output-style'}
    )

    def test_pp_a1_a8_the_kind_table_holds_the_eight_claude_kinds(self) -> None:
        assert set(Kinds().specs) == self.EIGHT_KINDS

    def test_pp_a2_a14_the_hook_builder_is_create_hooks(self) -> None:
        assert Kinds().specs['hook'].builder == 'create-hooks'

    def test_pp_a7_a_command_renders_a_skill(self) -> None:
        assert Kinds().specs['command'].files == Kinds().specs['skill'].files

    def test_pp_a4_an_lsp_server_has_no_builder_and_no_directory(self) -> None:
        assert Kinds().specs['lsp'].builder is None
        assert Kinds().specs['lsp'].directory is None
        assert Kinds().specs['lsp'].files == ('.lsp.json',)


class TestComponentKinds:
    @pytest.mark.parametrize(
        'kind', [pytest.param('rule', id='rule'), pytest.param('extension', id='extension')]
    )
    def test_pp_a1_a5_a_kind_a_plugin_cannot_ship_names_outside_plugin(
        self, kind: str, plugin_plans: PlanFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate(plugin_plans.write(components=[component(kind=kind)])) == 1

        assert any('outside_plugin' in line for line in errors_of(capsys))

    def test_pp_a8_a_worker_component_names_agent(
        self, plugin_plans: PlanFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate(plugin_plans.write(components=[component(kind='worker')])) == 1

        assert any('agent' in line for line in errors_of(capsys))

    def test_pp_a14_a_hook_with_the_old_builder_name_fails(
        self, plugin_plans: PlanFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        hook = component(kind='hook', name='lint', builder='create-hook')
        assert validate(plugin_plans.write(components=[hook])) == 1

        assert any('create-hooks' in line for line in errors_of(capsys))


class TestPluginName:
    @pytest.mark.parametrize(
        'name',
        [
            pytest.param('', id=''),
            pytest.param('Py_Harness', id='Py_Harness'),
            pytest.param('py.harness', id='py.harness'),
            pytest.param('py harness', id='py harness'),
            pytest.param('py@market', id='py@market'),
            pytest.param('py:harness', id='py:harness'),
            pytest.param('a/b', id='a/b'),
            pytest.param('a\\b', id='a\\b'),
            pytest.param('claude-x', id='claude-x'),
        ],
    )
    def test_pp_a16_a_plugin_name_outside_the_claude_rule_fails(
        self, name: str, plugin_plans: PlanFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate(plugin_plans.write(name=name)) == 1

        assert any(line.startswith('error: name') for line in errors_of(capsys))


class TestAuthor:
    @pytest.fixture
    def plan_with_author_without_a_name(self, plugin_plans: PlanFiles) -> Path:
        return plugin_plans.write(author={'email': 'a@example.com'})

    @pytest.fixture
    def plan_without_author(self, plugin_plans: PlanFiles) -> Path:
        return plugin_plans.write(author=None)

    def test_pp_b11_an_author_without_a_name_is_an_error(
        self, plan_with_author_without_a_name: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate(plan_with_author_without_a_name) == 1

        assert 'error: author needs a name' in errors_of(capsys)

    def test_pp_b11_a_missing_author_is_a_warning(
        self, plan_without_author: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate(plan_without_author) == 0
        assert 'warning: author is missing' in capsys.readouterr().out
        assert validate(plan_without_author, '--strict') == 1


class TestLinks:
    @pytest.mark.parametrize(
        'homepage',
        [
            pytest.param('example.com/docs', id='example.com/docs'),
            pytest.param('https://', id='https://'),
            pytest.param('/docs', id='/docs'),
            pytest.param('', id=''),
        ],
    )
    def test_pp_b12_a_homepage_without_a_scheme_and_host_fails(
        self, homepage: str, plugin_plans: PlanFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate(plugin_plans.write(homepage=homepage)) == 1

        assert any(line.startswith('error: homepage') for line in errors_of(capsys))

    def test_pp_b13_a_repository_is_carried_unchecked(self, plugin_plans: PlanFiles) -> None:
        assert validate(plugin_plans.write(repository='not a url'), '--strict') == 0


class TestUserConfig:
    @pytest.fixture
    def plan_with_option_missing_its_description(self, plugin_plans: PlanFiles) -> Path:
        return plugin_plans.write(userConfig={'token': {'type': 'string', 'title': 'Token'}})

    @pytest.fixture
    def plan_with_complete_option(self, plugin_plans: PlanFiles) -> Path:
        option = {'type': 'string', 'title': 'Token', 'description': 'API token', 'sensitive': True}
        return plugin_plans.write(userConfig={'token': option})

    def test_pp_b3_a_user_config_option_needs_type_title_and_description(
        self, plan_with_option_missing_its_description: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate(plan_with_option_missing_its_description) == 1

        assert 'error: userConfig.token needs description' in errors_of(capsys)

    def test_pp_b3_a_complete_user_config_option_passes(
        self, plan_with_complete_option: Path
    ) -> None:
        assert validate(plan_with_complete_option, '--strict') == 0


class TestDependencies:
    @pytest.fixture
    def plan_with_names_and_objects(self, plugin_plans: PlanFiles) -> Path:
        dependencies = ['secrets-vault', 'tools@market', {'name': 'ci', 'marketplace': 'market'}]
        return plugin_plans.write(dependencies=dependencies)

    @pytest.fixture
    def plan_with_a_dependency_without_a_name(self, plugin_plans: PlanFiles) -> Path:
        return plugin_plans.write(dependencies=['@market'])

    def test_pp_b4_dependencies_take_names_and_objects(
        self, plan_with_names_and_objects: Path
    ) -> None:
        assert validate(plan_with_names_and_objects, '--strict') == 0

    def test_pp_b4_a_dependency_without_a_name_fails(
        self, plan_with_a_dependency_without_a_name: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate(plan_with_a_dependency_without_a_name) == 1

        assert 'error: dependencies entries must name a plugin' in errors_of(capsys)


class TestPlanContent:
    @pytest.fixture
    def plan_with_a_wrong_type(self, plugin_plans: PlanFiles) -> Path:
        return plugin_plans.write(components=[component(), component(name=3)])

    @pytest.fixture
    def plan_with_an_unknown_component_key(self, plugin_plans: PlanFiles) -> Path:
        return plugin_plans.write(components=[component(colour='red')])

    @pytest.fixture
    def plan_with_a_duplicate_component(self, plugin_plans: PlanFiles) -> Path:
        return plugin_plans.write(components=[component(), component()])

    def test_a_wrong_type_prints_one_error_with_its_path(
        self, plan_with_a_wrong_type: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate(plan_with_a_wrong_type) == 1

        assert errors_of(capsys) == ['error: Expected `str`, got `int` - at `$.components[1].name`']

    def test_an_unknown_top_level_key_is_a_warning_that_names_it(
        self, plugin_plans: PlanFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = plugin_plans.write(colour='red')

        assert validate(path) == 0
        assert "warning: unknown key 'colour'" in capsys.readouterr().out
        assert validate(path, '--strict') == 1

    def test_an_unknown_component_key_is_a_warning_that_names_it(
        self, plan_with_an_unknown_component_key: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate(plan_with_an_unknown_component_key) == 0

        assert "warning: unknown key 'colour' in components[0]" in capsys.readouterr().out

    def test_a_duplicate_component_is_an_error(
        self, plan_with_a_duplicate_component: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate(plan_with_a_duplicate_component) == 1

        assert 'error: component add-route: duplicate skill' in errors_of(capsys)


class TestUnreadablePlan:
    NOT_JSON = '{not json'

    def test_a_missing_file_exits_two_with_one_error_line(
        self, plugin_plans: PlanFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate(plugin_plans.directory / 'missing.json') == 2

        captured = capsys.readouterr()
        assert captured.out == ''
        assert captured.err.startswith('error: could not read')
        assert len(captured.err.splitlines()) == 1

    def test_text_that_is_not_json_exits_two(
        self, plugin_plans: PlanFiles, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = plugin_plans.directory / 'plan.json'
        path.write_text(self.NOT_JSON)

        assert validate(path) == 2
        assert capsys.readouterr().err.startswith('error: ')


class TestEachPlanCheck:
    @pytest.mark.parametrize(
        ('changes', 'message'),
        [
            pytest.param(
                {'description': ''},
                'description is required',
                id='changes0-description is required',
            ),
            pytest.param({'problem': ''}, 'problem is required', id='changes1-problem is required'),
            pytest.param(
                {'audience': {'who': 'us', 'how': 'everyone'}},
                'audience needs who and how',
                id='changes2-audience needs who and how',
            ),
            pytest.param(
                {'kinds': ['plugin']},
                'kinds must be a non-empty subset',
                id='changes3-kinds must be a non-empty subset',
            ),
            pytest.param(
                {'ecosystem': ''},
                'an ecosystem plugin names its ecosystem',
                id='changes4-an ecosystem plugin names its ecosystem',
            ),
            pytest.param(
                {'distribution': {'channel': 'git'}},
                'distribution.channel must be one of',
                id='changes5-distribution.channel must be one of',
            ),
            pytest.param(
                {'keywords': []},
                'keywords is a non-empty list',
                id='changes6-keywords is a non-empty list',
            ),
            pytest.param(
                {'components': []}, 'at least one component', id='changes7-at least one component'
            ),
            pytest.param(
                {'outside_plugin': [{'need': 'x'}]},
                'outside_plugin entries need',
                id='changes8-outside_plugin entries need',
            ),
            pytest.param(
                {'components': [component(name='Bad Name')]},
                'component Bad Name: name must be',
                id='changes9-component Bad Name: name must be',
            ),
            pytest.param(
                {'components': [component(purpose='')]},
                'component add-route: purpose is required',
                id='changes10-component add-route: purpose is required',
            ),
            pytest.param(
                {'components': [component(status='done')]},
                'status must be planned or built',
                id='changes11-status must be planned or built',
            ),
            pytest.param(
                {'components': [component(decision='x')]},
                'decision must be one of',
                id='changes12-decision must be one of',
            ),
            pytest.param(
                {'components': [component(advice={'mechanism': 'hook'})]},
                'advice must be null',
                id='changes13-advice must be null',
            ),
            pytest.param(
                {'components': [component(kind='plugin')]},
                'kind must be one of',
                id='changes14-kind must be one of',
            ),
        ],
    )
    def test_each_plan_check_reports_its_error(
        self,
        changes: Mapping[str, object],
        message: str,
        plugin_plans: PlanFiles,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert validate(plugin_plans.write(**changes)) == 1

        assert any(message in line for line in errors_of(capsys))
