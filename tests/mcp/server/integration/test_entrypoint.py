import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

import anyio
import pytest
from mightymodels_core.edge import PLUGIN_DATA_VARIABLE
from mightymodels_mcp.server.call_log import LOG_LEVEL_VARIABLE

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from tests.mcp.server.server_harness import ServerHarness

CONSOLE_SCRIPT = Path(sys.executable).with_name('mightymodels-mcp')
INITIALIZE = {
    'jsonrpc': '2.0',
    'id': 1,
    'method': 'initialize',
    'params': {
        'protocolVersion': '2025-06-18',
        'capabilities': {},
        'clientInfo': {'name': 'entrypoint-test', 'version': '0'},
    },
}


@dataclass(slots=True, kw_only=True, frozen=True)
class ConsoleRun:
    exit: int
    stdout: str
    stderr: str


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusedStart:
    name: str
    environ: MappingProxyType[str, str]
    stderr_fragment: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def refused_start_cases() -> pytest.MarkDecorator:
    unset = RefusedStart(
        name='data-directory-unset',
        environ=MappingProxyType({}),
        stderr_fragment=PLUGIN_DATA_VARIABLE,
    )
    empty = RefusedStart(
        name='data-directory-empty',
        environ=MappingProxyType({PLUGIN_DATA_VARIABLE: ''}),
        stderr_fragment=PLUGIN_DATA_VARIABLE,
    )
    bad_level = RefusedStart(
        name='unknown-log-level',
        environ=MappingProxyType({LOG_LEVEL_VARIABLE: 'LOUD', PLUGIN_DATA_VARIABLE: 'data'}),
        stderr_fragment='DEBUG, INFO, WARNING, ERROR, CRITICAL',
    )
    return pytest.mark.parametrize('refused', [unset.param, empty.param, bad_level.param])


async def run_console_script(environ: dict[str, str], cwd: Path, stdin: bytes = b'') -> ConsoleRun:
    base = {'PATH': os.environ['PATH'], 'HOME': str(cwd)}
    done = await anyio.run_process(
        [str(CONSOLE_SCRIPT)], env={**base, **environ}, cwd=cwd, input=stdin, check=False
    )
    return ConsoleRun(
        exit=done.returncode, stdout=done.stdout.decode(), stderr=done.stderr.decode()
    )


class TestRefusedStart:
    @pytest.fixture
    def working_directory(self, tmp_path: Path) -> Path:
        directory = tmp_path.joinpath('work')
        directory.mkdir()
        return directory

    @refused_start_cases()
    async def test_start_is_refused_with_one_line_and_no_files(
        self, refused: RefusedStart, working_directory: Path
    ) -> None:
        done = await run_console_script(dict(refused.environ), working_directory)

        assert done.exit != 0
        assert len(done.stderr.splitlines()) == 1
        assert refused.stderr_fragment in done.stderr
        assert not [entry async for entry in anyio.Path(working_directory).iterdir()]


class TestServing:
    @pytest.fixture
    def stdin(self) -> bytes:
        return f'{json.dumps(INITIALIZE)}\n'.encode()

    async def test_initialize_succeeds_and_stdout_is_only_json_rpc(
        self, server_harness: ServerHarness, stdin: bytes
    ) -> None:
        done = await run_console_script(server_harness.environ, server_harness.repository, stdin)

        messages = [json.loads(line) for line in done.stdout.splitlines()]
        assert messages
        assert all(message['jsonrpc'] == '2.0' for message in messages)
        assert any(message.get('id') == 1 and 'result' in message for message in messages)
