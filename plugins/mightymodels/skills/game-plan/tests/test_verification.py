"""Behavioral tests for scripts/verification.py via its entry point."""

from __future__ import annotations

import io
import json
import runpy
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'verification.py'
SLUG = 'retry-queue'
PASSED, FAILED, REJECTED = 0, 1, 2
PYTHON = sys.executable
SHA_A = 'a' * 40
SHA_B = 'b' * 40
SHA256_HEX = 64


def python(code: str, *args: str) -> list[str]:
    return [PYTHON, '-c', code, *args]


@dataclass(frozen=True, slots=True)
class Outcome:
    code: int
    out: str
    err: str


@dataclass(frozen=True, slots=True)
class Workspace:
    root: Path
    monkeypatch: pytest.MonkeyPatch
    capsys: pytest.CaptureFixture[str]
    main: Callable[[list[str]], int]

    def run(self, *argv: str, stdin: object = None) -> Outcome:
        payload = '' if stdin is None else json.dumps(stdin)
        self.monkeypatch.setattr('sys.stdin', io.StringIO(payload))
        code = self.main([argv[0], '--slug', SLUG, *argv[1:]])
        captured = self.capsys.readouterr()
        return Outcome(code=code, out=captured.out, err=captured.err)

    def approve(self, *commands: dict[str, object]) -> Outcome:
        return self.run('contract', stdin={'approved_by': 'user', 'commands': commands})

    def receipts(self) -> list[dict[str, object]]:
        path = self.root / '.mightymodels' / SLUG / 'verification' / 'receipts.jsonl'
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]

    def point_head(self, sha: str) -> None:
        git = self.root / '.git'
        (git / 'refs' / 'heads').mkdir(parents=True, exist_ok=True)
        (git / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
        (git / 'refs' / 'heads' / 'main').write_text(f'{sha}\n', encoding='utf-8')


@pytest.fixture
def workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Workspace:
    (tmp_path / '.git').mkdir()
    monkeypatch.chdir(tmp_path)
    main = runpy.run_path(str(SCRIPT))['main']
    space = Workspace(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys, main=main)
    space.point_head(SHA_A)
    return space


def test_contract_requires_a_named_approver(workspace: Workspace) -> None:
    outcome = workspace.run('contract', stdin={'commands': []})
    assert outcome.code == REJECTED
    assert 'approved_by is required' in outcome.err


def test_a_shell_string_is_refused(workspace: Workspace) -> None:
    outcome = workspace.approve({'id': 'T1.AC-1', 'argv': 'pytest -q && rm -rf /'})
    assert outcome.code == REJECTED
    assert 'no shell string' in outcome.err


def test_an_approved_command_runs_and_leaves_a_receipt(workspace: Workspace) -> None:
    workspace.approve({'id': 'T1.AC-1', 'argv': python('print("ok")')})
    outcome = workspace.run('run', '--id', 'T1.AC-1')
    receipt = workspace.receipts()[0]
    assert outcome.code == PASSED
    assert outcome.out.startswith('T1.AC-1 pass exit=0')
    assert (receipt['outcome'], receipt['head'], receipt['stdout_tail']) == (
        'pass',
        SHA_A,
        'ok',
    )


def test_ids_outside_the_contract_never_run(workspace: Workspace) -> None:
    workspace.approve({'id': 'T1.AC-1', 'argv': python('print(1)')})
    outcome = workspace.run('run', '--id', 'T1.AC-1', '--id', 'rm-everything')
    assert outcome.code == REJECTED
    assert "not in the contract: ['rm-everything']" in outcome.err
    assert not (
        workspace.root / '.mightymodels' / SLUG / 'verification' / 'receipts.jsonl'
    ).exists()


def test_arguments_reach_the_command_without_a_shell(workspace: Workspace) -> None:
    code = 'import sys; print(sys.argv[1])'
    workspace.approve({'id': 'I1', 'argv': python(code, '$HOME; echo pwned')})
    workspace.run('run', '--id', 'I1')
    assert workspace.receipts()[0]['stdout_tail'] == '$HOME; echo pwned'


def test_a_failing_command_reports_its_tail(workspace: Workspace) -> None:
    code = 'import sys; sys.stderr.write("boom\\n"); sys.exit(3)'
    workspace.approve({'id': 'T2.AC-1', 'argv': python(code)})
    outcome = workspace.run('run', '--id', 'T2.AC-1')
    assert outcome.code == FAILED
    assert 'T2.AC-1 fail exit=3' in outcome.out
    assert '  | boom' in outcome.out


def test_an_expected_red_command_passes_at_planning(workspace: Workspace) -> None:
    code = 'import sys; sys.exit(1)'
    workspace.approve({'id': 'T3.AC-1', 'argv': python(code), 'expect_exit': 1})
    outcome = workspace.run('run', '--id', 'T3.AC-1', '--phase', 'planning')
    assert outcome.code == PASSED
    assert workspace.receipts()[0]['phase'] == 'planning'


def test_a_hung_command_times_out(workspace: Workspace) -> None:
    code = 'import time; time.sleep(10)'
    workspace.approve({'id': 'slow', 'argv': python(code), 'timeout': 1})
    outcome = workspace.run('run', '--id', 'slow')
    assert outcome.code == FAILED
    assert workspace.receipts()[0]['outcome'] == 'timeout'


def test_a_missing_program_is_reported_not_raised(workspace: Workspace) -> None:
    workspace.approve({'id': 'gone', 'argv': ['no-such-program-xyz']})
    outcome = workspace.run('run', '--id', 'gone')
    assert outcome.code == FAILED
    assert workspace.receipts()[0]['outcome'] == 'not-found'


def test_head_changes_during_a_command_cannot_produce_a_passing_receipt(
    workspace: Workspace,
) -> None:
    code = f'from pathlib import Path; Path(".git/refs/heads/main").write_text("{SHA_B}\\n")'
    workspace.approve({'id': 'T1.AC-1', 'argv': python(code)})
    outcome = workspace.run('run', '--id', 'T1.AC-1')
    receipt = workspace.receipts()[0]
    assert outcome.code == FAILED
    assert (receipt['outcome'], receipt['head']) == ('fail', SHA_A)
    assert 'HEAD changed during verification' in receipt['stderr_tail']


def test_an_approved_id_cannot_change_its_argv(workspace: Workspace) -> None:
    workspace.approve({'id': 'T1.AC-1', 'argv': python('print(1)')})
    outcome = workspace.approve({'id': 'T1.AC-1', 'argv': python('print(2)')})
    assert outcome.code == REJECTED
    assert 'give it a new id' in outcome.err


def test_output_is_bounded_but_digested_whole(workspace: Workspace) -> None:
    code = 'print("\\n".join(str(n) for n in range(100)))'
    workspace.approve({'id': 'loud', 'argv': python(code)})
    workspace.run('run', '--id', 'loud')
    receipt = workspace.receipts()[0]
    assert str(receipt['stdout_tail']).splitlines() == [str(n) for n in range(60, 100)]
    assert len(str(receipt['digest'])) == SHA256_HEX


def test_status_marks_results_from_an_older_head_stale(workspace: Workspace) -> None:
    workspace.approve(
        {'id': 'T1.AC-1', 'argv': python('print(1)')},
        {'id': 'T1.AC-2', 'argv': python('print(2)')},
    )
    workspace.run('run', '--id', 'T1.AC-1')
    workspace.point_head(SHA_B)
    outcome = workspace.run('status', '--prefix', 'T1.')
    assert f'T1.AC-1 stale (pass at {SHA_A[:12]})' in outcome.out
    assert 'T1.AC-2 never-run' in outcome.out
    assert outcome.code == FAILED


def test_status_passes_when_every_command_passed_at_head(workspace: Workspace) -> None:
    workspace.approve({'id': 'T1.AC-1', 'argv': python('print(1)')})
    workspace.run('run', '--id', 'T1.AC-1')
    outcome = workspace.run('status')
    assert outcome.code == PASSED
    assert 'T1.AC-1 pass task expect=0' in outcome.out


def test_all_runs_every_approved_command_at_head(workspace: Workspace) -> None:
    workspace.approve(
        {'id': 'I1', 'argv': python('print(1)')},
        {'id': 'T1.AC-1', 'argv': python('print(2)')},
    )
    outcome = workspace.run('run', '--all', '--phase', 'landing')
    receipts = workspace.receipts()
    assert outcome.code == PASSED
    assert [(r['id'], r['phase']) for r in receipts] == [
        ('I1', 'landing'),
        ('T1.AC-1', 'landing'),
    ]
