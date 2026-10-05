"""The `bin/pythonista` shim: prerequisite errors, first-run sync, and hook-safe exits."""

import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SHIM = PLUGIN_ROOT.joinpath('bin', 'pythonista')
SHELL_TOOLS = ('dirname', 'cksum', 'cut', 'mkdir', 'chmod')
FAKE_UV = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_UV_LOG"
case "$1" in
    sync)
        if [ "${FAKE_SYNC_STATUS:-0}" -ne 0 ]; then
            echo 'uv: no network' >&2
            exit "$FAKE_SYNC_STATUS"
        fi
        mkdir -p "$UV_PROJECT_ENVIRONMENT/bin"
        : > "$UV_PROJECT_ENVIRONMENT/bin/pythonista"
        chmod +x "$UV_PROJECT_ENVIRONMENT/bin/pythonista"
        ;;
    run)
        shift
        printf 'project=%s frozen=%s no_dev=%s args=%s\\n' \\
            "$UV_PROJECT" "$UV_FROZEN" "$UV_NO_DEV" "$*"
        exit "${FAKE_RUN_STATUS:-0}"
        ;;
esac
"""


@dataclass(frozen=True, slots=True)
class ShimRun:
    exit_code: int
    stdout: str
    stderr: str
    uv_calls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ShimSandbox:
    plugin: Path
    tools: Path
    home: Path

    @property
    def log(self) -> Path:
        return self.home.joinpath('uv-calls.log')

    @property
    def venv_bin(self) -> Path:
        environments = self.home.joinpath('.cache', 'pythonista').glob('venv-*')
        return next(environments).joinpath('bin')

    def install_fake_uv(self) -> None:
        fake = self.tools.joinpath('uv')
        fake.write_text(FAKE_UV, encoding='utf-8')
        fake.chmod(0o755)

    def run(self, *arguments: str, extra: Mapping[str, str] | None = None) -> ShimRun:
        environment = {
            'PATH': str(self.tools),
            'HOME': str(self.home),
            'FAKE_UV_LOG': str(self.log),
            **(extra or {}),
        }
        completed = subprocess.run(  # noqa: S603  the plugin's own shim, in a sandbox.
            (
                str(shutil.which('sh')),
                str(self.plugin.joinpath('bin', 'pythonista')),
                *arguments,
            ),
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        calls = self.log.read_text(encoding='utf-8').splitlines() if self.log.exists() else []
        return ShimRun(completed.returncode, completed.stdout, completed.stderr, tuple(calls))


@pytest.fixture
def sandbox(tmp_path: Path) -> ShimSandbox:
    if shutil.which('sh') is None:
        pytest.skip('sh is not installed')
    plugin = tmp_path.joinpath('plugin')
    plugin.joinpath('bin').mkdir(parents=True)
    shutil.copy2(SHIM, plugin.joinpath('bin', 'pythonista'))
    plugin.joinpath('pyproject.toml').write_text('', encoding='utf-8')
    plugin.joinpath('uv.lock').write_text('', encoding='utf-8')
    tools = tmp_path.joinpath('tools')
    tools.mkdir()
    for name in SHELL_TOOLS:
        tools.joinpath(name).symlink_to(str(shutil.which(name)))
    home = tmp_path.joinpath('home')
    home.mkdir()
    return ShimSandbox(plugin.resolve(), tools, home)


class TestPrerequisites:
    @pytest.mark.parametrize(
        ('arguments', 'exit_code'),
        [
            pytest.param(('inspect', 'survey'), 2, id='cli'),
            pytest.param(('hooks', 'guard-python'), 1, id='hook'),
        ],
    )
    def test_a_missing_uv_is_named_with_its_install_page(
        self, sandbox: ShimSandbox, arguments: tuple[str, ...], exit_code: int
    ) -> None:
        result = sandbox.run(*arguments)

        assert (result.exit_code, result.stderr) == (
            exit_code,
            (
                'pythonista: uv is not on PATH; install it'
                ' (https://docs.astral.sh/uv/getting-started/installation/), then start'
                ' a new session\n'
            ),
        )

    def test_a_missing_plugin_file_asks_for_a_reinstall(self, sandbox: ShimSandbox) -> None:
        sandbox.install_fake_uv()
        sandbox.plugin.joinpath('uv.lock').unlink()

        result = sandbox.run('inspect', 'survey')

        assert (result.exit_code, result.stderr) == (
            2,
            f'pythonista: {sandbox.plugin}/uv.lock is missing; reinstall the plugin\n',
        )

    def test_no_cache_home_is_reported(self, sandbox: ShimSandbox) -> None:
        sandbox.install_fake_uv()

        result = sandbox.run('inspect', 'survey', extra={'HOME': ''})

        assert (result.exit_code, result.stderr) == (
            2,
            (
                'pythonista: neither XDG_CACHE_HOME nor HOME is set, so there is'
                " nowhere to keep the CLI's virtualenv\n"
            ),
        )


class TestEnvironment:
    def test_the_first_run_syncs_then_runs_the_cli(self, sandbox: ShimSandbox) -> None:
        sandbox.install_fake_uv()

        result = sandbox.run('inspect', 'survey')

        assert (result.exit_code, result.uv_calls, result.stdout) == (
            0,
            ('sync --quiet', 'run --quiet pythonista inspect survey'),
            (
                f'project={sandbox.plugin} frozen=1 no_dev=1'
                ' args=--quiet pythonista inspect survey\n'
            ),
        )

    def test_a_built_environment_is_not_synced_again(self, sandbox: ShimSandbox) -> None:
        sandbox.install_fake_uv()
        sandbox.run('inspect', 'gate')
        sandbox.log.unlink()

        result = sandbox.run('inspect', 'gate')

        assert (result.uv_calls, sandbox.venv_bin.joinpath('pythonista').exists()) == (
            ('run --quiet pythonista inspect gate',),
            True,
        )

    @pytest.mark.parametrize(
        ('arguments', 'exit_code'),
        [
            pytest.param(('inspect', 'survey'), 2, id='cli'),
            pytest.param(('hooks', 'session-start'), 1, id='hook'),
        ],
    )
    def test_a_failed_sync_explains_itself_and_skips_the_cli(
        self, sandbox: ShimSandbox, arguments: tuple[str, ...], exit_code: int
    ) -> None:
        sandbox.install_fake_uv()

        result = sandbox.run(*arguments, extra={'FAKE_SYNC_STATUS': '2'})

        assert (
            result.exit_code,
            result.uv_calls,
            result.stderr.splitlines()[1][:41],
        ) == (
            exit_code,
            ('sync --quiet',),
            'pythonista: uv could not build the CLI en',
        )


class TestExitCodes:
    @pytest.mark.parametrize(
        ('arguments', 'cli_exit', 'shim_exit'),
        [
            pytest.param(('inspect', 'gate'), 1, 1, id='cli-keeps-its-code'),
            pytest.param(('inspect', 'survey'), 2, 2, id='cli-keeps-an-error'),
            pytest.param(('hooks', 'guard-python'), 2, 1, id='hook-never-exits-two'),
            pytest.param(('hooks', 'guard-python'), 0, 0, id='hook-success'),
        ],
    )
    def test_only_hooks_map_failures_to_one(
        self,
        sandbox: ShimSandbox,
        *,
        arguments: tuple[str, ...],
        cli_exit: int,
        shim_exit: int,
    ) -> None:
        sandbox.install_fake_uv()

        result = sandbox.run(*arguments, extra={'FAKE_RUN_STATUS': str(cli_exit)})

        assert result.exit_code == shim_exit

    def test_xdg_cache_home_wins_over_home(self, sandbox: ShimSandbox, tmp_path: Path) -> None:
        sandbox.install_fake_uv()
        cache = tmp_path.joinpath('xdg')

        sandbox.run('inspect', 'survey', extra={'XDG_CACHE_HOME': str(cache)})

        assert [path.name[:5] for path in cache.joinpath('pythonista').iterdir()] == ['venv-']


def test_the_shim_parses_under_dash() -> None:
    dash = shutil.which('dash')
    if dash is None:
        pytest.skip('dash is not installed')

    completed = subprocess.run(  # noqa: S603  a syntax check of the plugin's own shim.
        (dash, '-n', str(SHIM)), capture_output=True, text=True, check=False
    )

    assert (completed.returncode, completed.stderr) == (0, '')


def test_environment_variables_do_not_leak_into_this_process() -> None:
    assert 'FAKE_UV_LOG' not in os.environ
