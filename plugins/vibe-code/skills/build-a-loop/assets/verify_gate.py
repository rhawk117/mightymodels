#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO


@dataclass(frozen=True, slots=True, kw_only=True)
class GateConfig:
    check: list[str]
    cwd: Path
    state_path: Path
    max_blocks: int


def load_gate_config(path: Path) -> GateConfig:
    raw = json.loads(path.read_text())
    return GateConfig(
        check=list(raw['check']),
        cwd=Path(raw.get('cwd', '.')).expanduser(),
        state_path=Path(raw.get('state_path', '.loop-gate.state')).expanduser(),
        max_blocks=int(raw.get('max_blocks', 1)),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckResult:
    passed: bool
    detail: str


def read_payload(stream: TextIO) -> dict[str, Any]:
    raw = stream.read().strip() if not stream.isatty() else ''
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _gate_timeout() -> int:
    try:
        return int(os.environ.get('LOOP_GATE_TIMEOUT', '300'))
    except ValueError:
        return 300


def run_check(config: GateConfig) -> CheckResult:
    try:
        completed = subprocess.run(  # noqa: S603 -- argv list built by this harness, never a shell string
            config.check,
            cwd=config.cwd,
            capture_output=True,
            text=True,
            timeout=_gate_timeout(),
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        return CheckResult(passed=False, detail=f'verification could not run: {error}')
    tail = (completed.stdout + completed.stderr).strip().splitlines()[-20:]
    return CheckResult(passed=completed.returncode == 0, detail='\n'.join(tail))


def blocks_recorded(config: GateConfig) -> int:
    if not config.state_path.exists():
        return 0

    try:
        return int(config.state_path.read_text().strip() or 0)
    except ValueError:
        return 0


def record_blocks(config: GateConfig, count: int) -> None:
    config.state_path.parent.mkdir(parents=True, exist_ok=True)
    config.state_path.write_text(str(count))


def clear_blocks(config: GateConfig) -> None:
    config.state_path.unlink(missing_ok=True)


def emit(*, blocking: bool, message: str) -> None:
    if blocking:
        print(json.dumps({'decision': 'block', 'reason': message}))
        return
    print(json.dumps({'systemMessage': message}) if message else '', end='')


def load_config() -> GateConfig | None:
    config_path = Path(os.environ.get('LOOP_GATE_CONFIG', '.loop-gate.json'))
    if not config_path.exists():
        print(f'loop gate config not found at {config_path}', file=sys.stderr)
        return None

    try:
        return load_gate_config(config_path)
    except (KeyError, ValueError, json.JSONDecodeError) as error:
        print(f'loop gate config is invalid: {error}', file=sys.stderr)
        return None


def main(stdin: TextIO) -> int:
    config = load_config()
    if config is None:
        return 1

    payload = read_payload(stdin)
    result = run_check(config)

    if result.passed:
        clear_blocks(config)
        emit(blocking=False, message='')
        return 0

    prior = max(blocks_recorded(config), 1 if payload.get('stop_hook_active') else 0)
    if prior >= config.max_blocks:
        clear_blocks(config)
        emit(
            blocking=False,
            message=(
                f'Verification still failing after {prior} blocked attempt(s). '
                f'Releasing the turn and reporting unresolved failure:\n{result.detail}'
            ),
        )
        return 0

    record_blocks(config, prior + 1)
    emit(
        blocking=True,
        message=(
            "The loop's verification check is failing, so the work is not done. "
            f'Fix the cause rather than the symptom, then finish again:\n{result.detail}'
        ),
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.stdin))
