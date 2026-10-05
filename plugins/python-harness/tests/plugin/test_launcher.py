"""The `bin/python-harness` launcher: pinned shebang, a decoy project, and failing hooks."""

import json
import os
import re
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
import tomllib

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PLUGIN_ROOT.parents[1]
LAUNCHER = PLUGIN_ROOT.joinpath('bin', 'python-harness')
HOOKS_FILE = PLUGIN_ROOT.joinpath('hooks', 'hooks.json')
SHEBANG_LIMIT = 127
REQUIREMENT_END = re.compile(r'[<>=!~;\[ ]')
WITH_PIN = re.compile(r'--with (\S+)==(\S+)')
PYTHON_SPEC = re.compile(r'--python "?([^" ]+)"?')
DECOY_PYPROJECT = '[project]\nname = "decoy"\nversion = "0"\nrequires-python = ">=3.14"\n'
DECOY_INTERPRETER = '#!/bin/sh\n: > "{ran}"\nexit 1\n'
DECOY_RAN = 'decoy-interpreter-ran'
FAKE_UV = '#!/bin/sh\nexit {status}\n'
SHELL = '/bin/sh'


def normalized(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def locked_versions() -> dict[str, str]:
    lock = tomllib.loads(REPOSITORY_ROOT.joinpath('uv.lock').read_text(encoding='utf-8'))
    return {normalized(package['name']): package['version'] for package in lock['package']}


def runtime_pins() -> dict[str, str]:
    pyproject = tomllib.loads(PLUGIN_ROOT.joinpath('pyproject.toml').read_text(encoding='utf-8'))
    locked = locked_versions()
    names = [
        normalized(REQUIREMENT_END.split(requirement, maxsplit=1)[0])
        for requirement in pyproject['project']['dependencies']
    ]
    return {name: locked[name] for name in names}


def hook_commands() -> list[str]:
    document = json.loads(HOOKS_FILE.read_text(encoding='utf-8'))
    return [
        handler['command']
        for matchers in document['hooks'].values()
        for matcher in matchers
        for handler in matcher['hooks']
    ]


def hook_name(command: str) -> str:
    return shlex.split(command)[2]


def run(
    argv: Sequence[str], directory: Path, environment: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  the repo's own launcher and hook commands
        argv,
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope='module')
def expected_pins() -> dict[str, str]:
    return runtime_pins()


@pytest.fixture(scope='module')
def requires_python() -> str:
    pyproject = tomllib.loads(PLUGIN_ROOT.joinpath('pyproject.toml').read_text(encoding='utf-8'))
    return pyproject['project']['requires-python']


@pytest.fixture(scope='module')
def shebang() -> str:
    return LAUNCHER.read_bytes().split(b'\n', 1)[0].decode('utf-8')


class TestShebang:
    PREFIX = '#!/usr/bin/env -S uv tool run '

    def test_uses_uv_tool_run(self, shebang: str) -> None:
        assert shebang.startswith(self.PREFIX)

    def test_fits_the_kernel_shebang_limit(self, shebang: str) -> None:
        assert len(shebang.encode('utf-8')) <= SHEBANG_LIMIT

    def test_is_executable(self) -> None:
        assert os.access(LAUNCHER, os.X_OK)


class TestPins:
    def test_with_pins_equal_the_locked_runtime_dependencies(
        self, shebang: str, expected_pins: dict[str, str]
    ) -> None:
        pins = {normalized(name): version for name, version in WITH_PIN.findall(shebang)}

        assert pins == expected_pins

    def test_python_spec_equals_requires_python(self, shebang: str, requires_python: str) -> None:
        found = PYTHON_SPEC.search(shebang)

        assert found is not None
        assert found.group(1) == requires_python


@pytest.fixture(scope='module')
def decoy_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    project = tmp_path_factory.mktemp('decoy')
    project.joinpath('pyproject.toml').write_text(DECOY_PYPROJECT, encoding='utf-8')
    virtualenv = project.joinpath('.venv')
    virtualenv.joinpath('bin').mkdir(parents=True)
    virtualenv.joinpath('pyvenv.cfg').write_text('home = /usr/bin\n', encoding='utf-8')
    interpreter = virtualenv.joinpath('bin', 'python')
    ran = project.joinpath(DECOY_RAN)
    interpreter.write_text(DECOY_INTERPRETER.format(ran=ran), encoding='utf-8')
    interpreter.chmod(0o755)
    return project


@pytest.fixture(scope='module')
def help_run(decoy_project: Path) -> subprocess.CompletedProcess[str]:
    return run([str(LAUNCHER), '--help'], decoy_project)


class TestRunBesideADecoyProject:
    def test_help_exits_zero(self, help_run: subprocess.CompletedProcess[str]) -> None:
        assert help_run.returncode == 0

    def test_help_names_the_program(self, help_run: subprocess.CompletedProcess[str]) -> None:
        assert help_run.stdout.startswith('usage: python-harness')

    @pytest.mark.usefixtures('help_run')
    def test_the_decoy_interpreter_never_runs(self, decoy_project: Path) -> None:
        assert not decoy_project.joinpath(DECOY_RAN).exists()

    @pytest.mark.usefixtures('help_run')
    def test_nothing_is_written_beside_the_decoy(self, decoy_project: Path) -> None:
        assert sorted(path.name for path in decoy_project.iterdir()) == ['.venv', 'pyproject.toml']


class TestHookCommandsWhenUvFails:
    @pytest.fixture
    def tools(self, tmp_path: Path, request: pytest.FixtureRequest) -> Path:
        if request.param is not None:
            uv = tmp_path.joinpath('uv')
            uv.write_text(FAKE_UV.format(status=request.param), encoding='utf-8')
            uv.chmod(0o755)
        return tmp_path

    @pytest.fixture
    def environment(self, tools: Path) -> dict[str, str]:
        return {'CLAUDE_PLUGIN_ROOT': str(PLUGIN_ROOT), 'PATH': str(tools)}

    @pytest.mark.parametrize('command', hook_commands(), ids=hook_name)
    @pytest.mark.parametrize(
        ('tools', 'expected'),
        [
            pytest.param(2, 1, id='uv-exits-two'),
            pytest.param(1, 1, id='uv-exits-one'),
            pytest.param(None, 1, id='uv-is-missing'),
            pytest.param(0, 0, id='uv-succeeds'),
        ],
        indirect=['tools'],
    )
    def test_only_zero_or_one_reaches_claude_code(
        self, command: str, tools: Path, environment: dict[str, str], expected: int
    ) -> None:
        completed = run((SHELL, '-c', command), tools, environment)

        assert completed.returncode == expected
