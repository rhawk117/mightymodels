#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path

type JsonValue = dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None


def parse_stdout(raw: str) -> list[tuple[str, JsonValue]]:
    lines = [ln for ln in raw.strip().splitlines() if ln.strip()]
    payload_lines: list[tuple[str, JsonValue]] = []
    for ln in lines:
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            payload_lines.append((ln, None))
            continue
        if isinstance(obj, dict) and obj.get('type') == 'progress':
            continue
        payload_lines.append((ln, obj))

    return payload_lines


def check_field(obj: JsonValue, spec: str) -> tuple[bool, str]:
    key, _, expected = spec.partition('=')
    cur = obj
    for part in key.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return False, f'missing field {key}'
        cur = cur[part]
    if expected and str(cur) != expected:
        return False, f'{key}={cur!r}, expected {expected!r}'
    return True, f'{key}={cur!r}'


def parse_arguments() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=(
            'Pipe a sample payload into a Claude Code hook script and check the '
            'output contract: exit 0 with at most one JSON object on stdout, or '
            'exit 2 to block with the reason on stderr'
        )
    )
    ap.add_argument('script')
    ap.add_argument('payload')
    ap.add_argument('--expect-exit', type=int, default=0)
    ap.add_argument('--expect-field', action='append', default=[], metavar='KEY[=VALUE]')
    ap.add_argument('--expect-empty', action='store_true')
    ap.add_argument('--timeout', type=float, default=15.0)
    return ap.parse_args()


def hook_command(script: Path) -> list[str]:
    interpreters = {
        '.py': [sys.executable],
        '.ps1': ['pwsh', '-File'],
        '.mjs': ['node'],
        '.js': ['node'],
    }
    return [*interpreters.get(script.suffix, ['bash']), str(script)]


def field_failures(outputs: list[tuple[str, JsonValue]], specs: list[str]) -> list[str]:
    result_obj = outputs[0][1] if outputs and outputs[0][1] is not None else {}
    failures = []
    for spec in specs:
        ok, detail = check_field(result_obj, spec)
        if not ok:
            failures.append(detail)
    return failures


def contract_failures(
    proc: subprocess.CompletedProcess[str],
    outputs: list[tuple[str, JsonValue]],
    args: argparse.Namespace,
) -> list[str]:
    failures = []
    if proc.returncode != args.expect_exit:
        failures.append(
            f'exit={proc.returncode}, expected {args.expect_exit}; '
            f'stderr: {proc.stderr.strip()[:300]}'
        )

    bad_lines = [ln for ln, obj in outputs if obj is None]
    if bad_lines:
        failures.append(f'non-JSON stdout line(s): {bad_lines[:2]}')
    if args.expect_empty and outputs:
        failures.append(f'expected empty stdout, got: {outputs[0][0][:200]}')
    if len(outputs) > 1:
        failures.append(f'{len(outputs)} JSON output lines; the contract is a single line')

    failures.extend(field_failures(outputs, args.expect_field))
    return failures


def main() -> int:
    args = parse_arguments()

    script = Path(args.script)
    payload = Path(args.payload).read_text()
    json.loads(payload)

    cmd = hook_command(script)

    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            input=payload,
            capture_output=True,
            text=True,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(
            f'FAIL {script.name}: timed out after {args.timeout}s '
            '(a real hook this slow stalls every matching call)'
        )
        return 1

    outputs = parse_stdout(proc.stdout)
    failures = contract_failures(proc, outputs, args)
    if failures:
        print(f'FAIL {script.name} < {Path(args.payload).name}')
        for f in failures:
            print(f'  - {f}')
        return 1
    shown = outputs[0][0][:200] if outputs else '(empty stdout)'
    print(f'PASS {script.name} < {Path(args.payload).name} -> exit {proc.returncode}, {shown}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
