import asyncio
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.usefixtures('session_data_directory')]

ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = ROOT / 'bin' / 'mightymodels'
EXECUTABLE_MODE = '100755'


async def run_in(cwd: Path, *command: str) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        *command, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await process.communicate()
    return process.returncode or 0, stdout.decode()


class TestLauncher:
    def test_help_lists_verify_from_any_directory(self, tmp_path: Path) -> None:
        code, stdout = asyncio.run(run_in(tmp_path, str(LAUNCHER), '--help'))

        assert code == 0
        assert 'verify' in stdout

    def test_the_launcher_is_committed_executable(self) -> None:
        _, stdout = asyncio.run(run_in(ROOT, 'git', 'ls-files', '-s', 'bin/mightymodels'))

        assert stdout.split()[0] == EXECUTABLE_MODE
