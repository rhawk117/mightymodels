"""The inspect commands end to end: arguments and streams in, JSON and exit code out."""

import io
import json
from types import MappingProxyType

import pytest
from python_harness.cli import main
from python_harness.commands.domain import InspectCommand, ProcessEdge
from python_harness.commands.exit_codes import ExitCode
from python_harness.commands.inspection import default_inspect_commands
from python_harness.core.tests.fixtures import GitProject, ProjectBuilder
from python_harness.core.tests.support import JsonDocument
from python_harness.core.workspace import Workspace

PROJECT = MappingProxyType(
    {
        'pyproject.toml': """
            [project]
            name = "shop"
            requires-python = ">=3.14"
            [project.scripts]
            shop = "shop.cli:main"
            [build-system]
            requires = ["uv_build"]
            build-backend = "uv_build"
        """,
        'src/shop/__init__.py': '',
        'src/shop/pricing.py': """
            def price(total: int) -> int:
                return total
        """,
        'src/shop/cli.py': """
            from shop.pricing import price


            def main() -> int:
                return price(0)
        """,
        'REVIEW.md': """
            - Location: src/shop/pricing.py:1 `def price(total: int) -> int:`
            - Location: src/shop/pricing.py:40 `return total`
        """,
    }
)


def run_inspect(workspace: Workspace, *arguments: str, stdin: str = '') -> tuple[int, JsonDocument]:
    stdout = io.StringIO()
    edge = ProcessEdge(io.StringIO(stdin), stdout, io.StringIO(), MappingProxyType({}))
    command = ('inspect', *arguments, '--root', str(workspace.root))
    exit_code = main(command, edge=edge)
    return exit_code, json.loads(stdout.getvalue())


def run_failing_inspect(workspace: Workspace, *arguments: str) -> tuple[int, str]:
    stderr = io.StringIO()
    edge = ProcessEdge(io.StringIO(), io.StringIO(), stderr, MappingProxyType({}))
    command = ('inspect', *arguments, '--root', str(workspace.root))
    exit_code = main(command, edge=edge)
    return exit_code, stderr.getvalue()


@pytest.fixture
def workspace(project_builder: ProjectBuilder) -> Workspace:
    return project_builder.write(PROJECT)


class TestCommandTable:
    def test_every_inspect_command_has_a_definition(self) -> None:
        assert frozenset(default_inspect_commands()) == frozenset(InspectCommand)


class TestSurvey:
    def test_survey_prints_the_projects_domains(self, workspace: Workspace) -> None:
        exit_code, document = run_inspect(workspace, 'survey')

        assert (exit_code, document['domains']) == (ExitCode.PASSED, ['cli'])


class TestGate:
    EVERY_TOOL_SKIPPED = (
        '--skip',
        'ruff_check',
        '--skip',
        'ruff_format',
        '--skip',
        'ty',
        '--skip',
        'pytest',
    )

    def test_gate_with_every_tool_skipped_reports_no_results(self, workspace: Workspace) -> None:
        exit_code, document = run_inspect(workspace, 'gate', *self.EVERY_TOOL_SKIPPED)

        assert (exit_code, document['results']) == (ExitCode.PASSED, [])

    @pytest.fixture
    def configured(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write({**PROJECT, 'config/ruff.toml': 'line-length = 90\n'})

    def test_relative_fallback_ruff_config_is_found_under_the_root(
        self, configured: Workspace
    ) -> None:
        exit_code, document = run_inspect(
            configured,
            'gate',
            '--fallback-ruff-config',
            'config/ruff.toml',
            *self.EVERY_TOOL_SKIPPED,
        )

        assert (exit_code, document['ruff_config_source']) == (
            ExitCode.PASSED,
            'fallback',
        )

    def test_missing_fallback_ruff_config_is_refused_before_any_tool_runs(
        self, workspace: Workspace
    ) -> None:
        missing = workspace.root.joinpath('absent-ruff.toml')

        exit_code, stderr = run_failing_inspect(
            workspace, 'gate', '--fallback-ruff-config', str(missing)
        )

        assert (exit_code, stderr) == (
            ExitCode.ERROR,
            f'pythonista: --fallback-ruff-config {missing} is not a file\n',
        )


class TestSurfaceCodebase:
    @pytest.mark.parametrize(
        ('arguments', 'expected'),
        [
            pytest.param(('--codebase', 'src'), ['src'], id='one-path'),
            pytest.param(
                ('--codebase', 'src/shop/pricing.py', 'src/shop/cli.py'),
                ['src/shop/pricing.py', 'src/shop/cli.py'],
                id='several-paths',
            ),
            pytest.param(('--codebase',), ['.'], id='defaults-to-the-root'),
        ],
    )
    def test_codebase_paths_become_the_target(
        self, workspace: Workspace, arguments: tuple[str, ...], expected: list[str]
    ) -> None:
        exit_code, document = run_inspect(workspace, 'surface', *arguments)

        assert (exit_code, document['target']['paths']) == (ExitCode.PASSED, expected)

    def test_head_without_diff_is_refused(self, workspace: Workspace) -> None:
        exit_code, stderr = run_failing_inspect(
            workspace, 'surface', '--codebase', '--head', 'feature'
        )

        assert (exit_code, stderr) == (
            ExitCode.ERROR,
            'pythonista: --head feature needs --diff BASE\n',
        )


class TestSurfaceDiff:
    @pytest.fixture
    def workspace(self, git_project: GitProject) -> Workspace:
        git_project.commit(PROJECT, 'base')
        git_project.switch_to_new_branch('feature')
        return git_project.commit({'src/shop/pricing.py': 'def price() -> int: ...\n'}, 'x')

    def test_diff_surface_holds_only_changed_modules(self, workspace: Workspace) -> None:
        _, plan = run_inspect(workspace, 'surface', '--diff', 'main')

        assert plan['module_count'] == 1

    @pytest.mark.parametrize(
        ('arguments', 'expected'),
        [
            pytest.param(
                ('--diff', 'main'),
                {'base': 'main', 'head': 'HEAD', 'kind': 'diff'},
                id='head-defaults-to-the-checkout',
            ),
            pytest.param(
                ('--diff', 'main', '--head', 'feature'),
                {'base': 'main', 'head': 'feature', 'kind': 'diff'},
                id='named-head',
            ),
        ],
    )
    def test_diff_target(
        self, workspace: Workspace, arguments: tuple[str, ...], expected: JsonDocument
    ) -> None:
        _, plan = run_inspect(workspace, 'surface', *arguments)

        assert plan['target'] == expected


class TestFacts:
    @pytest.mark.parametrize(
        ('paths', 'expected'),
        [
            pytest.param(('src/shop/pricing.py',), ['src/shop/pricing.py'], id='one-file'),
            pytest.param(
                ('src/shop', 'src/shop/pricing.py'),
                ['src/shop/__init__.py', 'src/shop/cli.py', 'src/shop/pricing.py'],
                id='overlapping-paths-report-a-module-once',
            ),
        ],
    )
    def test_facts_cover_the_given_paths(
        self, workspace: Workspace, paths: tuple[str, ...], expected: list[str]
    ) -> None:
        _, facts = run_inspect(workspace, 'facts', *paths)

        assert [module['path'] for module in facts['modules']] == expected


class TestCalls:
    def test_calls_cover_the_given_paths(self, workspace: Workspace) -> None:
        _, calls = run_inspect(workspace, 'calls', 'src/shop/pricing.py')

        paths = [module['metrics']['path'] for module in calls['modules']]
        assert paths == ['src/shop/pricing.py']

    def test_symbol_option_prints_its_references(self, workspace: Workspace) -> None:
        _, found = run_inspect(workspace, 'calls', 'src/shop/pricing.py', '--symbol', 'price')

        contexts = [item['context'] for item in found['symbols'][0]['references']]
        assert contexts == ['import', 'call']


class TestCite:
    PYLENS_RETURN = '| src/shop/pricing.py:2 | `return total` | returns its argument |\n'
    MALFORMED_RETURN = (
        '| src/shop/pricing.py:2 | `return total` | returns its argument |\n'
        '| src/shop/pricing.py#L2 | `return total` | returns its argument |\n'
    )
    MALFORMED_ROWS = (1, [2])

    def test_failed_citation_exits_failed(self, workspace: Workspace) -> None:
        exit_code, document = run_inspect(workspace, 'cite', 'REVIEW.md')

        assert (exit_code, document['passed']) == (ExitCode.FAILED, False)

    def test_dash_reads_the_document_from_stdin(self, workspace: Workspace) -> None:
        exit_code, document = run_inspect(workspace, 'cite', '-', stdin=self.PYLENS_RETURN)

        assert (exit_code, document['document']) == (ExitCode.PASSED, '<stdin>')

    def test_a_row_without_a_parseable_citation_exits_failed(self, workspace: Workspace) -> None:
        exit_code, document = run_inspect(workspace, 'cite', '-', stdin=self.MALFORMED_RETURN)

        rows = (document['checked'], document['uncited_rows'])
        assert (exit_code, rows) == (ExitCode.FAILED, self.MALFORMED_ROWS)


class TestUndecodableDocument:
    DOCUMENT = 'LATIN.md'

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        workspace = project_builder.write(PROJECT)
        document = workspace.root.joinpath(self.DOCUMENT)
        document.write_bytes(b'| src/shop/pricing.py:1 | `caf\xe9` | x |\n')
        return workspace

    def test_undecodable_document_exits_error_with_a_message(self, workspace: Workspace) -> None:
        exit_code, stderr = run_failing_inspect(workspace, 'cite', self.DOCUMENT)

        expected_start = f'pythonista: citation document {self.DOCUMENT} is not readable'
        assert (exit_code, stderr.startswith(expected_start)) == (ExitCode.ERROR, True)


class TestPathErrors:
    @pytest.mark.parametrize(
        'command',
        [
            pytest.param(('surface', '--codebase', 'src/shopp'), id='surface'),
            pytest.param(('facts', 'src/shop/pricng.py'), id='facts'),
            pytest.param(('calls', 'src/shopp'), id='calls'),
        ],
    )
    def test_missing_target_path_exits_error_with_a_message(
        self, workspace: Workspace, command: tuple[str, ...]
    ) -> None:
        exit_code, stderr = run_failing_inspect(workspace, *command)

        assert (exit_code, stderr.startswith('pythonista: ')) == (ExitCode.ERROR, True)


class TestUndecodableSource:
    PATH = 'src/shop/legacy.py'

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        workspace = project_builder.write(PROJECT)
        workspace.root.joinpath(self.PATH).write_bytes(b'name = "caf\xe9"\n')
        return workspace

    @pytest.mark.parametrize(
        'command',
        [
            pytest.param(('facts', 'src/shop'), id='facts'),
            pytest.param(('surface', '--codebase', 'src/shop'), id='surface'),
        ],
    )
    def test_undecodable_file_is_reported_as_unparsable(
        self, workspace: Workspace, command: tuple[str, ...]
    ) -> None:
        exit_code, document = run_inspect(workspace, *command)

        unparsable = [item['path'] for item in document['unparsable']]
        assert (exit_code, unparsable) == (ExitCode.PASSED, [self.PATH])
