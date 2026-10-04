import subprocess
from pathlib import Path

SHIM = Path(__file__).resolve().parents[1] / 'bin' / 'vibe-code'


def test_shim_without_uv_exits_127_naming_uv(tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603  # fixed path to the repo's own shim
        [str(SHIM), '--help'],
        env={'PATH': str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 127
    assert 'uv is required' in result.stderr
