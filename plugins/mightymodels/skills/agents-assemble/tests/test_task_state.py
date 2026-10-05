"""Behavioral tests for scripts/task_state.py against a real git repository."""

from __future__ import annotations

import json
import runpy
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'task_state.py'
SLUG = 'retry-queue'
ADVANCED, BLOCKED, REJECTED = 0, 1, 2
GIT = shutil.which('git') or 'git'
IDENTITY = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')


@dataclass(frozen=True, slots=True)
class Outcome:
    code: int
    out: str
    err: str


@dataclass(frozen=True, slots=True)
class Repo:
    root: Path
    capsys: pytest.CaptureFixture[str]
    main: Callable[[list[str]], int]

    def git(self, *args: str) -> str:
        completed = subprocess.run(  # noqa: S603 - fixed git argv built by the test itself
            [GIT, *IDENTITY, *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()

    def commit(self, relative: str, text: str) -> str:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        self.git('add', relative)
        self.git('commit', '-q', '-m', f'change {relative}')
        return self.git('rev-parse', 'HEAD')

    def run(self, *argv: str) -> Outcome:
        code = self.main([argv[0], '--slug', SLUG, *argv[1:]])
        captured = self.capsys.readouterr()
        return Outcome(code=code, out=captured.out, err=captured.err)

    @property
    def ticket_dir(self) -> Path:
        return self.root / '.mightymodels' / SLUG

    def unit(self) -> dict[str, Any]:
        return json.loads((self.ticket_dir / 'work-unit.json').read_text(encoding='utf-8'))

    def approve(self, *command_ids: str) -> None:
        commands = {command_id: {'id': command_id} for command_id in command_ids}
        contract = {'schema': 1, 'slug': SLUG, 'commands': commands}
        directory = self.ticket_dir / 'verification'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'contract.json').write_text(json.dumps(contract), encoding='utf-8')

    def receipt(self, command_id: str, outcome: str, head: str) -> None:
        entry = {'id': command_id, 'outcome': outcome, 'head': head, 'schema': 1}
        with (self.ticket_dir / 'verification' / 'receipts.jsonl').open('a') as handle:
            handle.write(json.dumps(entry) + '\n')
        if command_id.startswith('T'):
            task_id = command_id.split('.', 1)[0]
            self.done(task_id, head)

    def done(self, task_id: str, head: str) -> None:
        brief = self.ticket_dir / 'briefs' / f'task-{int(task_id[1:]):02d}.md'
        brief.parent.mkdir(exist_ok=True)
        asked = brief.read_text().split('## DONE', 1)[0] if brief.exists() else '## ASKED\n'
        brief.write_text(f'{asked}\n## DONE\ncommit: {head}\n')


@pytest.fixture
def repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Repo:
    monkeypatch.chdir(tmp_path)
    main = runpy.run_path(str(SCRIPT))['main']
    space = Repo(root=tmp_path, capsys=capsys, main=main)
    space.git('init', '-q')
    space.commit('src/queue.py', 'base\n')
    space.ticket_dir.mkdir(parents=True)
    unit = {'schema': 1, 'slug': SLUG, 'status': 'staged', 'ticket': {}}
    (space.ticket_dir / 'work-unit.json').write_text(json.dumps(unit), encoding='utf-8')
    return space


def start(repo: Repo, worker: str = 'engineer') -> Outcome:
    return repo.run('start', '--task', 'T1', '--by', worker, '--owned', 'src/queue.py')


def test_start_records_the_attempt_and_its_base(repo: Repo) -> None:
    base = repo.git('rev-parse', 'HEAD')
    outcome = start(repo)
    task = repo.unit()['progress']['tasks']['T1']
    assert outcome.code == ADVANCED
    assert (task['status'], task['base'], task['attempts']) == (
        'in-progress',
        base,
        {'engineer': 1},
    )


def test_a_task_with_passing_receipts_and_owned_changes_verifies(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', head)
    outcome = repo.run('verify', '--task', 'T1', '--commit', head)
    transitions = (repo.ticket_dir / 'transitions.jsonl').read_text().splitlines()
    assert (outcome.code, outcome.out.strip()) == (ADVANCED, 'T1 verified')
    assert [json.loads(line)['to'] for line in transitions] == ['in-progress', 'verified']


def test_changes_outside_the_owned_set_block_the_task(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    repo.commit('src/queue.py', 'fixed\n')
    head = repo.commit('deploy/values.yaml', 'pool: 5\n')
    repo.receipt('T1.AC-1', 'pass', head)
    outcome = repo.run('verify', '--task', 'T1', '--commit', head)
    assert outcome.code == BLOCKED
    assert 'changed outside the owned set: deploy/values.yaml' in outcome.out


def test_a_receipt_from_an_older_head_does_not_count(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    old = repo.git('rev-parse', 'HEAD')
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', old)
    outcome = repo.run('verify', '--task', 'T1', '--commit', head)
    assert outcome.code == BLOCKED
    assert 'T1.AC-1 has no receipt at the current HEAD' in outcome.out


def test_a_failing_receipt_blocks_the_task(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'fail', head)
    outcome = repo.run('verify', '--task', 'T1', '--commit', head)
    assert 'T1.AC-1 fail at HEAD' in outcome.out


def test_brief_criteria_need_a_command_or_a_citation(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    brief = repo.ticket_dir / 'briefs' / 'task-01.md'
    brief.parent.mkdir()
    brief.write_text('## ASKED\nacceptance:\n  - AC-1: tests pass\n  - AC-2: docs updated\n')
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', head)
    blocked = repo.run('verify', '--task', 'T1', '--commit', head, '--brief', str(brief))
    start(repo)
    cited = ('--assertion', 'AC-2=README.md:12')
    verified = repo.run('verify', '--task', 'T1', '--commit', head, '--brief', str(brief), *cited)
    assert 'AC-2 has neither a contract command nor a citation' in blocked.out
    assert verified.code == ADVANCED


def test_a_task_needs_some_proof(repo: Repo) -> None:
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    outcome = repo.run('verify', '--task', 'T1', '--commit', head)
    assert 'no contract command and no cited assertion proves this task' in outcome.out


def test_architect_recovers_a_task_only_once(repo: Repo) -> None:
    start(repo)
    repo.run('mark', '--task', 'T1', '--to', 'failed', '--reason', 'AC-1 still red')
    start(repo, 'architect')
    repo.run('mark', '--task', 'T1', '--to', 'blocked', '--reason', 'needs a decision')
    outcome = start(repo, 'architect')
    assert outcome.code == REJECTED
    assert 'route it to whats-broken' in outcome.err


def test_a_verified_task_cannot_restart(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', head)
    repo.run('verify', '--task', 'T1', '--commit', head)
    outcome = start(repo)
    assert 'cannot move from verified to in-progress' in outcome.err


def test_option_shaped_revisions_are_refused(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    outcome = repo.run('verify', '--task', 'T1', '--commit=--output=/tmp/pwned')
    assert outcome.code == REJECTED
    assert 'is not a plain revision name' in outcome.err


def test_an_unstaged_ticket_is_refused(repo: Repo) -> None:
    (repo.ticket_dir / 'work-unit.json').unlink()
    outcome = start(repo)
    assert 'stage the ticket with open-ticket first' in outcome.err


def test_an_approved_scope_expansion_allows_one_more_architect_pass(repo: Repo) -> None:
    start(repo)
    repo.run('mark', '--task', 'T1', '--to', 'failed', '--reason', 'AC-1 still red')
    start(repo, 'architect')
    repo.run('mark', '--task', 'T1', '--to', 'blocked', '--reason', 'scope-expansion-requested')
    expanded = ('--owned', 'src/queue.py', 'src/client.py', '--expanded-envelope')
    outcome = repo.run('start', '--task', 'T1', '--by', 'architect', *expanded)
    task = repo.unit()['progress']['tasks']['T1']
    assert outcome.code == ADVANCED
    assert task['owned'] == ['src/client.py', 'src/queue.py']


def verified_task(repo: Repo) -> str:
    repo.approve('T1.AC-1')
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', head)
    repo.run('verify', '--task', 'T1', '--commit', head)
    return head


def test_ready_when_every_task_is_verified_at_head(repo: Repo) -> None:
    head = verified_task(repo)
    outcome = repo.run('ready')
    assert (outcome.code, outcome.out) == (ADVANCED, f'ready at {head[:12]}\n')


def test_a_contract_task_never_started_is_not_ready(repo: Repo) -> None:
    verified_task(repo)
    repo.approve('T1.AC-1', 'T2.AC-1')
    outcome = repo.run('ready')
    assert outcome.code == BLOCKED
    assert 'T2 has contract commands but was never started' in outcome.out


def test_a_ci_fix_makes_earlier_receipts_stale(repo: Repo) -> None:
    verified_task(repo)
    repo.run('start', '--task', 'C1', '--by', 'engineer', '--owned', 'src/lint.py')
    repo.commit('src/lint.py', 'clean\n')
    outcome = repo.run('ready')
    assert outcome.code == BLOCKED
    assert outcome.out.splitlines()[1:] == ['  - T1.AC-1 has no receipt at the current HEAD']


def test_a_ci_fix_verifies_on_the_check_it_repaired(repo: Repo) -> None:
    verified_task(repo)
    repo.run('start', '--task', 'C1', '--by', 'engineer', '--owned', 'src/lint.py')
    head = repo.commit('src/lint.py', 'clean\n')
    repo.receipt('T1.AC-1', 'pass', head)
    check = ('--assertion', 'AC-1=https://github.com/o/r/actions/runs/99')
    outcome = repo.run('verify', '--task', 'C1', '--commit', head, *check)
    assert (outcome.code, outcome.out.strip()) == (ADVANCED, 'C1 verified')
    assert repo.run('ready').code == ADVANCED


def test_a_stuck_ci_fix_blocks_the_push(repo: Repo) -> None:
    head = verified_task(repo)
    repo.run('start', '--task', 'C1', '--by', 'engineer', '--owned', 'src/lint.py')
    repo.run('mark', '--task', 'C1', '--to', 'failed', '--reason', 'lint still red')
    repo.receipt('T1.AC-1', 'pass', head)
    outcome = repo.run('ready')
    assert outcome.code == BLOCKED
    assert 'C1 is failed: lint still red' in outcome.out


def test_ready_needs_some_verified_work(repo: Repo) -> None:
    outcome = repo.run('ready')
    assert 'no plan task has been started' in outcome.out


def test_a_failed_review_remediation_blocks_the_push(repo: Repo) -> None:
    head = verified_task(repo)
    repo.run('start', '--task', 'R3', '--by', 'engineer', '--owned', 'src/queue.py')
    repo.run('mark', '--task', 'R3', '--to', 'blocked', '--reason', 'needs a decision')
    repo.receipt('T1.AC-1', 'pass', head)
    outcome = repo.run('ready')
    assert 'R3 is blocked: needs a decision' in outcome.out


def test_an_old_report_cannot_hide_new_outside_changes(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    old = repo.commit('src/queue.py', 'fixed\n')
    head = repo.commit('deploy/values.yaml', 'pool: 5\n')
    repo.receipt('T1.AC-1', 'pass', head)
    outcome = repo.run('verify', '--task', 'T1', '--commit', old)
    assert outcome.code == BLOCKED
    assert 'reported commit must resolve to the current HEAD' in outcome.out


@pytest.mark.parametrize('brief_state', ['missing', 'no-done', 'old-commit'])
def test_done_evidence_must_exist_and_match_head(repo: Repo, brief_state: str) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    old = repo.git('rev-parse', 'HEAD')
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', head)
    brief = repo.ticket_dir / 'briefs' / 'task-01.md'
    if brief_state == 'missing':
        brief.unlink()
    elif brief_state == 'no-done':
        brief.write_text('## ASKED\n')
    else:
        repo.done('T1', old)
    assert repo.run('verify', '--task', 'T1', '--commit', head).code == BLOCKED


def test_short_commit_ids_are_saved_as_full_ids(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', head)
    repo.done('T1', head[:12])
    assert repo.run('verify', '--task', 'T1', '--commit', head[:12]).code == ADVANCED
    assert repo.unit()['progress']['tasks']['T1']['commit'] == head


def test_a_task_base_from_another_history_is_blocked(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    repo.git('checkout', '--orphan', 'unrelated')
    head = repo.commit('src/queue.py', 'other history\n')
    repo.receipt('T1.AC-1', 'pass', head)
    outcome = repo.run('verify', '--task', 'T1', '--commit', head)
    assert outcome.code == BLOCKED
    assert 'base is not an ancestor' in outcome.out
