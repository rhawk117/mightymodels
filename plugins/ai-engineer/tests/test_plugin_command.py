import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from ai_engineer_cli.cli import main
from ai_engineer_cli.plugin.kinds import KIND_SPECS

EXAMPLE = Path(__file__).parent.parent / 'skills' / 'plan-plugin' / 'assets' / 'plan.example.json'

PLAN = {
    'name': 'py-harness',
    'description': 'Python conventions for Claude Code sessions.',
    'keywords': ['python'],
    'problem': 'Agents skip ruff.',
    'audience': {'who': 'the team', 'how': 'team'},
    'kinds': ['ecosystem'],
    'ecosystem': 'python',
    'distribution': {'channel': 'local'},
    'author': {'name': 'Platform Team'},
    'components': [{'kind': 'skill', 'name': 'add-route', 'purpose': 'Add a route.'}],
}


def write_plan(directory: Path, changes: Mapping[str, object] | None = None) -> Path:
    path = directory / 'plan.json'
    path.write_text(json.dumps({**PLAN, **(changes or {})}))
    return path


def component(**changes: object) -> dict[str, object]:
    return {'kind': 'skill', 'name': 'add-route', 'purpose': 'Add a route.', **changes}


def validate(path: Path, *options: str) -> int:
    return main(['plugin', 'validate', str(path), *options])


def errors_of(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [line for line in capsys.readouterr().out.splitlines() if line.startswith('error:')]


def test_validate_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['plugin', 'validate', '--help'])

    assert exit_info.value.code == 0
    assert 'PLAN' in capsys.readouterr().out


def test_render_is_not_a_command_yet() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['plugin', 'render', '--help'])

    assert exit_info.value.code == 2


def test_plugin_without_a_command_prints_usage_and_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(['plugin']) == 2
    assert 'usage: ai-engineer' in capsys.readouterr().err


def test_a_valid_plan_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert validate(write_plan(tmp_path), '--strict') == 0
    assert 'PASS' in capsys.readouterr().out


def test_pp_a47_the_shipped_example_passes_strict() -> None:
    assert validate(EXAMPLE, '--strict') == 0
    kinds = {item['kind'] for item in json.loads(EXAMPLE.read_text())['components']}
    assert {'hook', 'skill', 'agent', 'lsp'} <= kinds


def test_pp_a1_a8_the_kind_table_holds_the_eight_claude_kinds() -> None:
    assert set(KIND_SPECS) == {
        'skill',
        'command',
        'agent',
        'hook',
        'mcp',
        'lsp',
        'executable',
        'output-style',
    }


def test_pp_a2_a14_the_hook_builder_is_create_hooks() -> None:
    assert KIND_SPECS['hook'].builder == 'create-hooks'


def test_pp_a7_a_command_renders_a_skill() -> None:
    assert KIND_SPECS['command'].files == KIND_SPECS['skill'].files


def test_pp_a4_an_lsp_server_has_no_builder_and_no_directory() -> None:
    assert KIND_SPECS['lsp'].builder is None
    assert KIND_SPECS['lsp'].directory is None
    assert KIND_SPECS['lsp'].files == ('.lsp.json',)


@pytest.mark.parametrize('kind', ['rule', 'extension'])
def test_pp_a1_a5_a_kind_a_plugin_cannot_ship_names_outside_plugin(
    kind: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert validate(write_plan(tmp_path, {'components': [component(kind=kind)]})) == 1

    assert any('outside_plugin' in line for line in errors_of(capsys))


def test_pp_a8_a_worker_component_names_agent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert validate(write_plan(tmp_path, {'components': [component(kind='worker')]})) == 1

    assert any('agent' in line for line in errors_of(capsys))


def test_pp_a14_a_hook_with_the_old_builder_name_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hook = component(kind='hook', name='lint', builder='create-hook')
    assert validate(write_plan(tmp_path, {'components': [hook]})) == 1

    assert any('create-hooks' in line for line in errors_of(capsys))


@pytest.mark.parametrize(
    'name',
    [
        '',
        'Py_Harness',
        'py.harness',
        'py harness',
        'py@market',
        'py:harness',
        'a/b',
        'a\\b',
        'claude-x',
    ],
)
def test_pp_a16_a_plugin_name_outside_the_claude_rule_fails(
    name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert validate(write_plan(tmp_path, {'name': name})) == 1

    assert any(line.startswith('error: name') for line in errors_of(capsys))


def test_pp_b11_an_author_without_a_name_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert validate(write_plan(tmp_path, {'author': {'email': 'a@example.com'}})) == 1

    assert 'error: author needs a name' in errors_of(capsys)


def test_pp_b11_a_missing_author_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_plan(tmp_path, {'author': None})

    assert validate(path) == 0
    assert 'warning: author is missing' in capsys.readouterr().out
    assert validate(path, '--strict') == 1


@pytest.mark.parametrize('homepage', ['example.com/docs', 'https://', '/docs', ''])
def test_pp_b12_a_homepage_without_a_scheme_and_host_fails(
    homepage: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert validate(write_plan(tmp_path, {'homepage': homepage})) == 1

    assert any(line.startswith('error: homepage') for line in errors_of(capsys))


def test_pp_b13_a_repository_is_carried_unchecked(tmp_path: Path) -> None:
    assert validate(write_plan(tmp_path, {'repository': 'not a url'}), '--strict') == 0


def test_pp_b3_a_user_config_option_needs_type_title_and_description(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    option = {'type': 'string', 'title': 'Token'}
    assert validate(write_plan(tmp_path, {'userConfig': {'token': option}})) == 1

    assert 'error: userConfig.token needs description' in errors_of(capsys)


def test_pp_b3_a_complete_user_config_option_passes(tmp_path: Path) -> None:
    option = {'type': 'string', 'title': 'Token', 'description': 'API token', 'sensitive': True}
    assert validate(write_plan(tmp_path, {'userConfig': {'token': option}}), '--strict') == 0


def test_pp_b4_dependencies_take_names_and_objects(tmp_path: Path) -> None:
    dependencies = ['secrets-vault', 'tools@market', {'name': 'ci', 'marketplace': 'market'}]
    assert validate(write_plan(tmp_path, {'dependencies': dependencies}), '--strict') == 0


def test_pp_b4_a_dependency_without_a_name_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert validate(write_plan(tmp_path, {'dependencies': ['@market']})) == 1

    assert 'error: dependencies entries must name a plugin' in errors_of(capsys)


def test_a_wrong_type_prints_one_error_with_its_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    changes = {'components': [component(), component(name=3)]}
    assert validate(write_plan(tmp_path, changes)) == 1

    assert errors_of(capsys) == ['error: Expected `str`, got `int` - at `$.components[1].name`']


def test_an_unknown_top_level_key_is_a_warning_that_names_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_plan(tmp_path, {'colour': 'red'})

    assert validate(path) == 0
    assert "warning: unknown key 'colour'" in capsys.readouterr().out
    assert validate(path, '--strict') == 1


def test_an_unknown_component_key_is_a_warning_that_names_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert validate(write_plan(tmp_path, {'components': [component(colour='red')]})) == 0

    assert "warning: unknown key 'colour' in components[0]" in capsys.readouterr().out


def test_a_repeated_key_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps(PLAN).replace('{', '{"name": "other", ', 1))

    assert validate(path) == 1
    assert "error: duplicate JSON key 'name'; the last one wins" in errors_of(capsys)


def test_a_duplicate_component_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert validate(write_plan(tmp_path, {'components': [component(), component()]})) == 1

    assert 'error: component add-route: duplicate skill' in errors_of(capsys)


def test_a_missing_file_exits_two_with_one_error_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert validate(tmp_path / 'missing.json') == 2

    captured = capsys.readouterr()
    assert captured.out == ''
    assert captured.err.startswith('error: could not read')
    assert len(captured.err.splitlines()) == 1


def test_text_that_is_not_json_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / 'plan.json'
    path.write_text('{not json')

    assert validate(path) == 2
    assert capsys.readouterr().err.startswith('error: ')


@pytest.mark.parametrize(
    ('changes', 'message'),
    [
        ({'description': ''}, 'description is required'),
        ({'problem': ''}, 'problem is required'),
        ({'audience': {'who': 'us', 'how': 'everyone'}}, 'audience needs who and how'),
        ({'kinds': ['plugin']}, 'kinds must be a non-empty subset'),
        ({'ecosystem': ''}, 'an ecosystem plugin names its ecosystem'),
        ({'distribution': {'channel': 'git'}}, 'distribution.channel must be one of'),
        ({'keywords': []}, 'keywords is a non-empty list'),
        ({'components': []}, 'at least one component'),
        ({'outside_plugin': [{'need': 'x'}]}, 'outside_plugin entries need'),
        ({'components': [component(name='Bad Name')]}, 'component Bad Name: name must be'),
        ({'components': [component(purpose='')]}, 'component add-route: purpose is required'),
        ({'components': [component(status='done')]}, 'status must be planned or built'),
        ({'components': [component(decision='x')]}, 'decision must be one of'),
        ({'components': [component(advice={'mechanism': 'hook'})]}, 'advice must be null'),
        ({'components': [component(kind='plugin')]}, 'kind must be one of'),
    ],
)
def test_each_plan_check_reports_its_error(
    changes: Mapping[str, object],
    message: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert validate(write_plan(tmp_path, changes)) == 1

    assert any(message in line for line in errors_of(capsys))
