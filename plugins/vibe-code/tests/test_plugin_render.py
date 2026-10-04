import json
import re
from pathlib import Path

import pytest
from vibe_code_cli.cli import main
from vibe_code_cli.plugin.phases import PHASES
from vibe_code_cli.plugin.tests.support import (
    EXAMPLE,
    ClaudeValidate,
    PlanFiles,
    all_kinds,
    component,
    directories_of,
    inventory,
    manifest_of,
    render,
)


class TestUsage:
    def test_render_help_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['plugin', 'render', '--help'])

        assert exit_info.value.code == 0
        assert '--force' in capsys.readouterr().out


class TestManifest:
    IDENTITY_KEYS = ('name', 'version', 'description', 'keywords', 'author')
    UNSET_KEYS = ('license', 'homepage', 'repository', 'userConfig', 'dependencies')

    @pytest.fixture
    def option(self) -> dict[str, object]:
        return {'type': 'string', 'title': 'Token', 'description': 'API token.', 'sensitive': True}

    @pytest.fixture
    def dependencies(self) -> list[object]:
        return ['base-tools', {'name': 'lint', 'marketplace': 'team'}]

    @pytest.fixture
    def plan_with_optional_keys(
        self, plugin_plans: PlanFiles, option: dict[str, object], dependencies: list[object]
    ) -> Path:
        return plugin_plans.write(
            license='Apache-2.0',
            homepage='https://example.com/docs',
            userConfig={'api_token': option},
            dependencies=dependencies,
        )

    def test_pp_a9_a15_b1_b4_render_of_the_example_passes_claude_validate(
        self, plugin_plans: PlanFiles, plugin_claude_validate: ClaudeValidate
    ) -> None:
        target = plugin_plans.directory / 'py-harness'

        assert render(EXAMPLE, target) == 0

        for name in ('.claude-plugin/plugin.json', 'README.md', 'PLAN.md', 'plugin-plan.json'):
            assert (target / name).is_file()
        assert not (target / 'plugin.json').exists()
        assert plugin_claude_validate(target).returncode == 0

    def test_pp_a9_manifest_has_no_schema_and_carries_the_identity_fields(
        self, plugin_target: Path
    ) -> None:
        assert render(EXAMPLE, plugin_target) == 0

        manifest = manifest_of(plugin_target)
        assert '$schema' not in manifest
        assert tuple(manifest)[:5] == self.IDENTITY_KEYS
        assert manifest['author'] == {'name': 'Platform Team', 'email': 'platform@example.com'}
        assert manifest['license'] == 'MIT'

    def test_pp_a9_manifest_omits_license_and_homepage_the_record_does_not_set(
        self, plugin_plans: PlanFiles, plugin_target: Path
    ) -> None:
        assert render(plugin_plans.write(), plugin_target) == 0

        manifest = manifest_of(plugin_target)
        for key in self.UNSET_KEYS:
            assert key not in manifest

    def test_pp_a9_b3_b4_b12_manifest_carries_the_optional_keys_the_record_sets(
        self,
        plan_with_optional_keys: Path,
        option: dict[str, object],
        dependencies: list[object],
        plugin_target: Path,
        plugin_claude_validate: ClaudeValidate,
    ) -> None:
        assert render(plan_with_optional_keys, plugin_target) == 0

        manifest = manifest_of(plugin_target)
        assert manifest['license'] == 'Apache-2.0'
        assert manifest['homepage'] == 'https://example.com/docs'
        assert manifest['userConfig'] == {'api_token': option}
        assert manifest['dependencies'] == dependencies
        assert plugin_claude_validate(plugin_target).returncode == 0


class TestDirectories:
    ONE_PER_KIND = frozenset(
        {
            '.claude-plugin',
            'skills',
            'skills/add-route',
            'skills/ship-it',
            'hooks',
            'agents',
            'mcp',
            'mcp/db-tools',
            'bin',
            'output-styles',
        }
    )

    @pytest.fixture
    def plan_with_a_built_agent(self, plugin_plans: PlanFiles) -> Path:
        built = {'kind': 'agent', 'name': 'test-runner', 'purpose': 'Run tests.', 'status': 'built'}
        return plugin_plans.write(components=[component(), built])

    def test_pp_a13_render_creates_one_directory_per_planned_component_kind(
        self,
        plugin_plans: PlanFiles,
        plugin_target: Path,
        plugin_claude_validate: ClaudeValidate,
    ) -> None:
        plan = plugin_plans.write(components=all_kinds())

        assert render(plan, plugin_target) == 0

        assert directories_of(plugin_target) == self.ONE_PER_KIND
        assert plugin_claude_validate(plugin_target).returncode == 0

    def test_pp_a13_a_built_component_creates_no_directory(
        self, plan_with_a_built_agent: Path, plugin_target: Path
    ) -> None:
        assert render(plan_with_a_built_agent, plugin_target) == 0

        assert 'agents' not in directories_of(plugin_target)


class TestPlanMd:
    RESIDUE = re.compile(r'agent-plugins|\.agent\.md|ask_user|worker', re.IGNORECASE)
    GREPPABLE_LINES = (
        'plugin.name: py-harness',
        'phase.1: Foundation; sessions: uv-runner',
        'component.test-runner.kind: agent',
        'component.uv-runner.builder: create-hooks',
        'component.add-fastapi-route.status: planned',
    )
    READY_PROMPTS = (
        '\n/vibe-code:create-skill Create the `add-route` skill',
        '\n/vibe-code:create-hooks Create the `uv-runner` hook',
        '\n/vibe-code:create-subagent Create the `test-runner` agent',
        '\n/vibe-code:create-mcp Create the `db-tools` MCP server',
        '\nAdd the `pyright` language server entry to .lsp.json',
    )
    VERIFY_COMMANDS = (
        'claude plugin validate',
        '--strict',
        'claude --plugin-dir',
        '/reload-plugins',
        '/mcp',
        '/hooks',
    )

    @pytest.fixture
    def example_plan_md(self, plugin_target: Path) -> str:
        assert render(EXAMPLE, plugin_target) == 0
        return (plugin_target / 'PLAN.md').read_text()

    def test_pp_a11_a17_plan_md_keeps_the_human_and_agent_sections_and_greppable_lines(
        self, example_plan_md: str
    ) -> None:
        assert '\n## Human\n' in example_plan_md
        assert '\n## Agent\n' in example_plan_md
        for line in self.GREPPABLE_LINES:
            assert f'\n{line}\n' in example_plan_md

    def test_pp_a48_phases_order_the_executable_before_skills_and_agents_last(
        self, plugin_plans: PlanFiles
    ) -> None:
        text = plugin_plans.plan_md(components=all_kinds())

        sessions = dict(re.findall(r'^component\.([\w-]+)\.session: (\S+)$', text, re.MULTILINE))
        assert sessions['uv-runner'].startswith('1.')
        assert sessions['lint-all'] < sessions['add-route'] < sessions['test-runner']
        assert sessions['test-runner'].startswith(str(PHASES[2].number))
        assert sessions['test-runner'] > sessions['ship-it'] > sessions['add-route']

    def test_pp_a22_ready_prompts_open_with_the_namespaced_builder(
        self, plugin_plans: PlanFiles
    ) -> None:
        text = plugin_plans.plan_md(components=all_kinds())

        for prompt in self.READY_PROMPTS:
            assert prompt in text

    def test_pp_a18_marketplace_channel_adds_the_marketplace_before_the_install(
        self, plugin_target: Path
    ) -> None:
        assert render(EXAMPLE, plugin_target) == 0

        readme = (plugin_target / 'README.md').read_text()
        add = 'claude plugin marketplace add <source>'
        install = 'claude plugin install py-harness@platform-tools --scope project'
        assert readme.index(add) < readme.index(install)

    def test_pp_a18_marketplace_channel_without_an_install_line_uses_the_plugin_name(
        self, plugin_plans: PlanFiles
    ) -> None:
        text = plugin_plans.plan_md(distribution={'channel': 'marketplace'})

        assert 'claude plugin install py-harness@<marketplace> --scope project' in text

    def test_pp_a18_local_channel_installs_with_plugin_dir(self, plugin_plans: PlanFiles) -> None:
        text = plugin_plans.plan_md()

        assert '\nplugin.install: claude --plugin-dir ./py-harness\n' in text
        assert 'marketplace add' not in text

    def test_pp_a17_a21_verify_session_names_the_claude_code_checks(
        self, plugin_plans: PlanFiles
    ) -> None:
        text = plugin_plans.plan_md()

        for command in self.VERIFY_COMMANDS:
            assert command in text.split('Verify the plugin at')[1].split('```')[0]

    def test_pp_a19_a20_publish_session_pins_sha_beside_ref(self, example_plan_md: str) -> None:
        publish = example_plan_md.split('Publish the plugin at')[1]
        publish = publish.split('```')[0]
        assert '.claude-plugin/marketplace.json' in publish
        assert '`ref` and the 40-char `sha`' in publish
        assert 'CLAUDE_CODE_PLUGIN_CACHE_DIR' in publish

    @pytest.mark.usefixtures('example_plan_md')
    def test_pp_a47_rendered_example_text_has_no_residue(self, plugin_target: Path) -> None:
        for name in ('PLAN.md', 'README.md'):
            assert self.RESIDUE.findall((plugin_target / name).read_text()) == []


class TestRefusals:
    @pytest.fixture
    def outside(self, plugin_plans: PlanFiles) -> Path:
        path = plugin_plans.directory / 'outside'
        path.mkdir()
        return path

    @pytest.fixture
    def target_linking_out(self, plugin_target: Path, outside: Path) -> Path:
        plugin_target.mkdir()
        (plugin_target / '.claude-plugin').symlink_to(outside)
        return plugin_target

    @pytest.fixture
    def target_that_is_a_file(self, plugin_target: Path) -> Path:
        plugin_target.write_text('x')
        return plugin_target

    @pytest.mark.parametrize(
        'name',
        [
            pytest.param('a/b', id='a/b'),
            pytest.param('..', id='..'),
            pytest.param('.hidden', id='.hidden'),
            pytest.param('../up', id='../up'),
            pytest.param('a\\b', id='a\\b'),
        ],
    )
    def test_pp_a13_render_refuses_a_component_name_that_could_leave_the_target(
        self,
        plugin_plans: PlanFiles,
        plugin_target: Path,
        capsys: pytest.CaptureFixture[str],
        name: str,
    ) -> None:
        plan = plugin_plans.write(components=[component(name=name, purpose='x')])

        assert render(plan, plugin_target) == 1
        assert 'error: component' in capsys.readouterr().out
        assert not plugin_target.exists()

    def test_render_refuses_a_record_that_fails_validate_and_writes_nothing(
        self, plugin_plans: PlanFiles, plugin_target: Path
    ) -> None:
        assert render(plugin_plans.write(name='claude-x'), plugin_target) == 1
        assert not plugin_target.exists()

    def test_render_refuses_an_unreadable_record_with_exit_two(
        self, plugin_plans: PlanFiles, plugin_target: Path
    ) -> None:
        assert render(plugin_plans.directory / 'missing.json', plugin_target) == 2

    def test_render_refuses_a_plan_directory_that_links_out_of_the_target(
        self,
        plugin_plans: PlanFiles,
        target_linking_out: Path,
        outside: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert render(plugin_plans.write(), target_linking_out) == 1
        assert 'resolves outside' in capsys.readouterr().err
        assert list(outside.iterdir()) == []

    def test_render_refuses_a_target_that_is_a_file(
        self, plugin_plans: PlanFiles, target_that_is_a_file: Path
    ) -> None:
        assert render(plugin_plans.write(), target_that_is_a_file) == 1
        assert target_that_is_a_file.read_text() == 'x'


class TestForce:
    HAND_WRITTEN_MANIFEST = '{"name": "kept"}'

    @pytest.fixture
    def plan(self, plugin_plans: PlanFiles) -> Path:
        return plugin_plans.write()

    @pytest.fixture
    def rendered(self, plan: Path, plugin_target: Path) -> Path:
        assert render(plan, plugin_target) == 0
        return plugin_target

    @pytest.fixture
    def manifest_with_content(self, plugin_manifest_path: Path, content: str) -> Path:
        plugin_manifest_path.parent.mkdir(parents=True)
        plugin_manifest_path.write_text(content)
        return plugin_manifest_path

    def test_render_refuses_an_existing_manifest_unless_force(
        self,
        plan: Path,
        rendered: Path,
        plugin_manifest_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        plugin_manifest_path.write_text(self.HAND_WRITTEN_MANIFEST)

        assert render(plan, rendered) == 1
        assert '--force' in capsys.readouterr().err
        assert plugin_manifest_path.read_text() == self.HAND_WRITTEN_MANIFEST

        assert render(plan, rendered, '--force') == 0
        assert manifest_of(rendered)['name'] == 'py-harness'

    def test_force_rewrites_the_plan_files_and_deletes_nothing(
        self, plugin_plans: PlanFiles, rendered: Path
    ) -> None:
        own_skill = rendered / 'skills' / 'add-route' / 'SKILL.md'
        own_skill.write_text('mine')
        stray = rendered / 'notes.txt'
        stray.write_text('keep')

        assert render(plugin_plans.write(version='0.2.0'), rendered, '--force') == 0

        assert own_skill.read_text() == 'mine'
        assert stray.read_text() == 'keep'
        assert manifest_of(rendered)['version'] == '0.2.0'

    @pytest.mark.parametrize(
        'content',
        [pytest.param('{not json', id='{not json'), pytest.param('["name"]', id='["name"]')],
    )
    def test_force_refuses_a_manifest_that_is_not_a_json_object_and_writes_nothing(
        self,
        plan: Path,
        plugin_target: Path,
        manifest_with_content: Path,
        capsys: pytest.CaptureFixture[str],
        content: str,
    ) -> None:
        assert render(plan, plugin_target, '--force') == 1

        assert str(manifest_with_content) in capsys.readouterr().err
        assert manifest_with_content.read_text() == content
        assert not (plugin_target / 'PLAN.md').exists()


class TestForceKeepsUnmodelledKeys:
    @pytest.fixture
    def kept_keys(self) -> dict[str, object]:
        return {
            'hooks': './custom/hooks.json',
            'mcpServers': {'db': {'command': 'uvx', 'args': ['db-tools']}},
            'displayName': 'Py Harness',
        }

    @pytest.fixture
    def plugin_with_unmodelled_keys(
        self, plugin_plans: PlanFiles, kept_keys: dict[str, object]
    ) -> Path:
        target = plugin_plans.directory / 'plugin'
        (target / '.claude-plugin').mkdir(parents=True)
        (target / 'custom').mkdir()
        (target / 'custom' / 'hooks.json').write_text('{"hooks": {}}')
        manifest = {
            'name': 'py-harness',
            'version': '0.1.0',
            'description': 'Conventions.',
            'author': {'name': 'Platform Team'},
            **kept_keys,
        }
        (target / '.claude-plugin' / 'plugin.json').write_text(json.dumps(manifest))
        return target

    @pytest.fixture
    def record_of_unmodelled_keys(
        self, plugin_plans: PlanFiles, plugin_with_unmodelled_keys: Path
    ) -> Path:
        record = plugin_plans.directory / 'record.json'
        assert inventory(plugin_with_unmodelled_keys, '--out', str(record)) == 0
        return record

    def test_force_keeps_the_manifest_keys_the_record_does_not_model(
        self,
        record_of_unmodelled_keys: Path,
        plugin_with_unmodelled_keys: Path,
        kept_keys: dict[str, object],
        plugin_claude_validate: ClaudeValidate,
    ) -> None:
        target = plugin_with_unmodelled_keys

        assert render(record_of_unmodelled_keys, target, '--force') == 0

        rewritten = manifest_of(target)
        assert {key: rewritten[key] for key in kept_keys} == kept_keys
        assert plugin_claude_validate(target).returncode == 0


class TestForceWritesModelledKeys:
    @pytest.fixture
    def old_manifest(self) -> dict[str, object]:
        return {'name': 'old', 'version': '9.9.9', 'keywords': ['old'], 'license': 'MIT'}

    @pytest.fixture
    def rendered_with_license(self, plugin_plans: PlanFiles, plugin_target: Path) -> Path:
        assert render(plugin_plans.write(license='MIT'), plugin_target) == 0
        return plugin_target

    def test_force_writes_the_modelled_manifest_keys_from_the_record(
        self,
        plugin_plans: PlanFiles,
        rendered_with_license: Path,
        plugin_manifest_path: Path,
        old_manifest: dict[str, object],
    ) -> None:
        plugin_manifest_path.write_text(json.dumps(old_manifest))

        changed = plugin_plans.write(version='0.2.0', keywords=['new'])
        assert render(changed, rendered_with_license, '--force') == 0

        rewritten = manifest_of(rendered_with_license)
        assert rewritten['version'] == '0.2.0'
        assert rewritten['keywords'] == ['new']
        assert 'license' not in rewritten


class TestWrittenPaths:
    def test_every_path_render_writes_resolves_inside_the_target(
        self, plugin_plans: PlanFiles, plugin_target: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert render(plugin_plans.write(components=all_kinds()), plugin_target) == 0

        written = [line.removeprefix('wrote ') for line in capsys.readouterr().out.splitlines()]
        written = [line for line in written if not line.startswith(('PASS', 'warning'))]
        assert len(written) == 4 + 7
        for relative in written:
            assert (plugin_target / relative).resolve().is_relative_to(plugin_target.resolve())
