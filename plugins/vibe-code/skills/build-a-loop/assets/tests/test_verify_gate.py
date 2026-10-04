"""Tests for verify_gate.py, the Stop-hook gate shipped with the build-a-loop skill.

The gate is a standalone entry-point script (invoked by path, not an importable
package), so the test imports it directly off the filesystem.
"""

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import verify_gate
from verify_gate import load_gate_config, run_check

PASSING = (sys.executable, '-c', 'raise SystemExit(0)')
FAILING = (sys.executable, '-c', 'print("2 tests failed"); raise SystemExit(1)')


def write_config(tmp_path: Path, **overrides: object) -> Path:
    raw = {'check': FAILING, 'state_path': str(tmp_path / 'state'), **overrides}
    config_path = tmp_path / 'gate.json'
    config_path.write_text(json.dumps(raw))
    return config_path


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    config_path: Path,
    payload: dict[str, object] | None = None,
) -> tuple[int, str]:
    monkeypatch.setenv('LOOP_GATE_CONFIG', str(config_path))
    code = verify_gate.main(io.StringIO(json.dumps(payload) if payload else ''))
    return code, capsys.readouterr().out


class TestLoadGateConfig:
    def test_load_reads_every_key_and_expands_the_defaults(self, tmp_path: Path) -> None:
        config_path = write_config(tmp_path, cwd=str(tmp_path), max_blocks=3)

        config = load_gate_config(config_path)

        assert config.check == list(FAILING)
        assert config.cwd == tmp_path
        assert config.state_path == tmp_path / 'state'
        assert config.max_blocks == 3

    def test_load_defaults_to_one_block_in_the_working_directory(self, tmp_path: Path) -> None:
        config_path = tmp_path / 'gate.json'
        config_path.write_text(json.dumps({'check': ['true']}))

        config = load_gate_config(config_path)

        assert config.cwd == Path()
        assert config.state_path == Path('.loop-gate.state')
        assert config.max_blocks == 1

    def test_load_requires_a_check_command(self, tmp_path: Path) -> None:
        config_path = tmp_path / 'gate.json'
        config_path.write_text('{}')

        with pytest.raises(KeyError):
            load_gate_config(config_path)


class TestGateOutcome:
    def test_missing_config_exits_one_without_a_payload(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        code, out = run_gate(monkeypatch, capsys, tmp_path / 'absent.json')

        assert code == 1
        assert out == ''

    def test_failing_check_blocks_with_the_check_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        code, out = run_gate(monkeypatch, capsys, write_config(tmp_path))

        payload = json.loads(out)
        assert code == 0
        assert payload['decision'] == 'block'
        assert '2 tests failed' in payload['reason']

    def test_second_failure_releases_with_a_system_message(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        config_path = write_config(tmp_path)
        run_gate(monkeypatch, capsys, config_path)

        code, out = run_gate(monkeypatch, capsys, config_path)

        payload = json.loads(out)
        assert code == 0
        assert set(payload) == {'systemMessage'}
        assert 'still failing after 1 blocked attempt' in payload['systemMessage']
        assert not (tmp_path / 'state').exists()

    def test_stop_hook_active_counts_as_one_prior_block(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        code, out = run_gate(
            monkeypatch, capsys, write_config(tmp_path), {'stop_hook_active': True}
        )

        assert code == 0
        assert set(json.loads(out)) == {'systemMessage'}

    def test_max_blocks_allows_that_many_blocks_before_release(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        config_path = write_config(tmp_path, max_blocks=2)

        first = json.loads(run_gate(monkeypatch, capsys, config_path)[1])
        second = json.loads(run_gate(monkeypatch, capsys, config_path)[1])
        third = json.loads(run_gate(monkeypatch, capsys, config_path)[1])

        assert [first.get('decision'), second.get('decision'), third.get('decision')] == [
            'block',
            'block',
            None,
        ]
        assert 'systemMessage' in third

    def test_passing_check_prints_nothing_and_clears_the_state(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        (tmp_path / 'state').write_text('1')

        code, out = run_gate(monkeypatch, capsys, write_config(tmp_path, check=PASSING))

        assert code == 0
        assert out == ''
        assert not (tmp_path / 'state').exists()


class TestCheckCommand:
    def test_check_that_times_out_fails_the_gate(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv('LOOP_GATE_TIMEOUT', '1')
        config = load_gate_config(
            write_config(tmp_path, check=[sys.executable, '-c', 'import time; time.sleep(30)'])
        )

        result = run_check(config)

        assert result.passed is False
        assert 'verification could not run' in result.detail

    def test_check_that_cannot_start_fails_the_gate(self, tmp_path: Path) -> None:
        config = load_gate_config(write_config(tmp_path, check=[str(tmp_path / 'no-such-command')]))

        result = run_check(config)

        assert result.passed is False
        assert 'verification could not run' in result.detail


class TestMalformedInput:
    def test_unparsable_payload_is_treated_as_empty(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv('LOOP_GATE_CONFIG', str(write_config(tmp_path)))

        code = verify_gate.main(io.StringIO('not json'))

        assert code == 0
        assert json.loads(capsys.readouterr().out)['decision'] == 'block'

    def test_corrupt_state_file_counts_as_no_prior_blocks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        (tmp_path / 'state').write_text('many')

        _, out = run_gate(monkeypatch, capsys, write_config(tmp_path))

        assert json.loads(out)['decision'] == 'block'

    def test_invalid_config_exits_one(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        config_path = tmp_path / 'gate.json'
        config_path.write_text('{}')

        code, out = run_gate(monkeypatch, capsys, config_path)

        assert code == 1
        assert out == ''

    def test_unparsable_timeout_falls_back_to_the_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv('LOOP_GATE_TIMEOUT', 'soon')

        assert run_check(load_gate_config(write_config(tmp_path, check=PASSING))).passed is True
