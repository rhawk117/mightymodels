import os
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PLUGIN_ROOT.parents[1]
LAUNCHER = PLUGIN_ROOT.joinpath('bin', 'vibe-code')
CMD_TWIN = PLUGIN_ROOT.joinpath('bin', 'vibe-code.cmd')
SHEBANG_LIMIT = 127
REQUIREMENT_END = re.compile(r'[<>=!~;\[ ]')
WITH_PIN = re.compile(r'--with (\S+)==(\S+)')
PYTHON_SPEC = re.compile(r'--python "?([^" ]+)"?')


@dataclass(frozen=True, slots=True, kw_only=True)
class Launch:
    shebang: str
    command: str
    pins: dict[str, str]
    requires_python: str


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


@pytest.fixture(scope='module')
def cmd_command() -> str:
    return CMD_TWIN.read_text(encoding='utf-8').splitlines()[1]


@pytest.fixture
def launch(request: pytest.FixtureRequest) -> str:
    return request.getfixturevalue(request.param)


class TestShebang:
    PREFIX = '#!/usr/bin/env -S uv tool run '

    def test_uses_uv_tool_run(self, shebang: str) -> None:
        assert shebang.startswith(self.PREFIX)

    def test_fits_the_kernel_shebang_limit(self, shebang: str) -> None:
        assert len(shebang.encode('utf-8')) <= SHEBANG_LIMIT

    def test_is_executable(self) -> None:
        assert os.access(LAUNCHER, os.X_OK)


class TestPins:
    @pytest.mark.parametrize(
        'launch',
        [
            pytest.param('shebang', id='shebang'),
            pytest.param('cmd_command', id='cmd'),
        ],
        indirect=True,
    )
    def test_with_pins_equal_the_locked_runtime_dependencies(
        self, launch: str, expected_pins: dict[str, str]
    ) -> None:
        pins = {normalized(name): version for name, version in WITH_PIN.findall(launch)}

        assert pins == expected_pins

    @pytest.mark.parametrize(
        'launch',
        [
            pytest.param('shebang', id='shebang'),
            pytest.param('cmd_command', id='cmd'),
        ],
        indirect=True,
    )
    def test_python_spec_equals_requires_python(self, launch: str, requires_python: str) -> None:
        found = PYTHON_SPEC.search(launch)

        assert found is not None
        assert found.group(1) == requires_python


@pytest.fixture(scope='module')
def help_run(tmp_path_factory: pytest.TempPathFactory) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # fixed path to the repo's own launcher
        [str(LAUNCHER), '--help'],
        cwd=tmp_path_factory.mktemp('elsewhere'),
        capture_output=True,
        text=True,
        check=False,
    )


class TestRun:
    def test_help_exits_zero(self, help_run: subprocess.CompletedProcess[str]) -> None:
        assert help_run.returncode == 0

    def test_help_names_the_program(self, help_run: subprocess.CompletedProcess[str]) -> None:
        assert help_run.stdout.startswith('usage: vibe-code')
