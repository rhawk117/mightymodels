"""Behavioral tests for scripts/archive_ticket.py against a real git repository."""

from __future__ import annotations

import io
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

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'archive_ticket.py'
SLUG = 'retry-queue'
LEDGER = '20260928-queue'
BLOCKED, REJECTED = 1, 2
ARCHIVE_LINES = 30
GIT = shutil.which('git') or 'git'
IDENTITY = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')
CLOSING = {
    'shipped': 'Retry queue drains in under a second',
    'pr': 'https://x/pull/7',
    'gotchas': ['the backoff floor is load-bearing'],
}


@dataclass(frozen=True, slots=True)
class Outcome:
    code: int
    out: str
    err: str


@dataclass(frozen=True, slots=True)
class Repo:
    root: Path
    monkeypatch: pytest.MonkeyPatch
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

    @property
    def base(self) -> Path:
        return self.root / '.mightymodels'

    def put(self, relative: str, value: object) -> None:
        path = self.base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def lines(self, relative: str, *records: object) -> None:
        path = self.base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        text = ''.join(json.dumps(record) + '\n' for record in records)
        path.write_text(text, encoding='utf-8')

    def unit(self) -> dict[str, Any]:
        return json.loads((self.base / SLUG / 'work-unit.json').read_text(encoding='utf-8'))

    def run(self, *argv: str, stdin: object = None) -> Outcome:
        payload = '' if stdin is None else json.dumps(stdin)
        self.monkeypatch.setattr('sys.stdin', io.StringIO(payload))
        code = self.main([argv[0], '--slug', SLUG, *argv[1:]])
        captured = self.capsys.readouterr()
        return Outcome(code, captured.out, captured.err)


def verified_unit(**extra: object) -> dict[str, object]:
    tasks = {
        'T1': {'status': 'verified', 'attempts': {'engineer': 1}},
        'C1': {'status': 'verified', 'attempts': {'engineer': 1, 'architect': 1}},
    }
    return {
        'schema': 1,
        'status': 'in-progress',
        'ticket': {
            'summary': 'Retry queue drains slowly',
            'branch': 'main',
            'tracker': {'issue': 42, 'jira': None},
        },
        'investigations': [LEDGER],
        'progress': {'tasks': tasks},
        **extra,
    }


@pytest.fixture
def repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Repo:
    monkeypatch.chdir(tmp_path)
    space = Repo(tmp_path, monkeypatch, capsys, runpy.run_path(str(SCRIPT))['main'])
    space.git('init', '-q', '-b', 'feature')
    (tmp_path / 'queue.py').write_text('base\n', encoding='utf-8')
    space.git('add', 'queue.py')
    space.git('commit', '-q', '-m', 'base')
    space.put(f'{SLUG}/work-unit.json', verified_unit())
    commands = {'T1.AC-1': {'id': 'T1.AC-1', 'argv': ['uv', 'run', 'pytest'], 'expect_exit': 0}}
    space.put(f'{SLUG}/verification/contract.json', {'schema': 1, 'commands': commands})
    space.lines(
        f'{SLUG}/verification/receipts.jsonl',
        {
            'schema': 1,
            'id': 'T1.AC-1',
            'outcome': 'pass',
            'head': 'a' * 40,
            'digest': 'd' * 64,
        },
    )
    space.lines(
        f'.runtime/investigations/{LEDGER}.jsonl',
        {'schema': 1, 'seq': 1, 'kind': 'target', 'text': 'queue'},
        {'schema': 1, 'seq': 2, 'kind': 'decision', 'text': 'keep the 10s floor'},
    )
    space.lines(
        '.runtime/decisions/receipts.jsonl',
        {'schema': 1, 'id': 'd-1', 'ticket': SLUG, 'question': 'Ship?', 'answer': 'yes'},
    )
    space.lines(
        '.runtime/subagents/receipts.jsonl',
        {'schema': 1, 'agent': 'engineer', 'status': 'done', 'ticket': SLUG},
        {'schema': 1, 'agent': 'code-scout', 'status': 'VERIFIED', 'ticket': 'other'},
    )
    return space


def test_a_ticket_with_everything_verified_has_no_live_work(repo: Repo) -> None:
    outcome = repo.run('check')
    assert (outcome.code, outcome.out) == (0, f'{SLUG} has no live work\n')


def test_unverified_tasks_and_a_live_debug_block_closing(repo: Repo) -> None:
    unit = verified_unit()
    unit['progress'] = {'tasks': {'T1': {'status': 'blocked'}}}
    repo.put(f'{SLUG}/work-unit.json', unit)
    (repo.base / SLUG / 'whats-broken.md').write_text('hypothesis\n', encoding='utf-8')
    outcome = repo.run('close', stdin=CLOSING)
    assert outcome.code == BLOCKED
    assert 'T1 is blocked, not verified' in outcome.out
    assert 'whats-broken.md is present' in outcome.out
    assert not (repo.base / 'archives').exists()


def test_undecided_and_unfixed_review_findings_block(repo: Repo) -> None:
    run = {
        'schema': 1,
        'run': '20260928-120000',
        'dispositions': {'F1': {'decision': 'fix'}},
        'outcomes': {},
    }
    repo.put(f'{SLUG}/review/20260928-120000/review-run.json', run)
    repo.lines(
        f'{SLUG}/review/20260928-120000/findings.jsonl',
        {'schema': 1, 'id': 'F1'},
        {'schema': 1, 'id': 'F2'},
    )
    outcome = repo.run('check')
    assert 'review finding F2 has no decision' in outcome.out
    assert 'review finding F1 was chosen for fixing and is not fixed' in outcome.out


def test_a_branch_with_commits_on_no_remote_blocks(repo: Repo) -> None:
    repo.put(f'{SLUG}/work-unit.json', verified_unit(ticket={'branch': 'feature'}))
    outcome = repo.run('check')
    assert 'branch feature has 1 commits on no remote' in outcome.out


def test_close_writes_a_bounded_archive_and_marks_the_unit_closed(repo: Repo) -> None:
    outcome = repo.run('close', stdin=CLOSING)
    archive = (repo.base / 'archives' / f'{SLUG}.md').read_text(encoding='utf-8')
    record = json.loads((repo.base / 'archives' / f'{SLUG}.json').read_text(encoding='utf-8'))
    assert outcome.code == 0, outcome.err
    assert len(archive.splitlines()) <= ARCHIVE_LINES
    assert 'PR: https://x/pull/7 · tracker: #42' in archive
    assert '- keep the 10s floor (20260928-queue e2)' in archive
    assert 'agents: 1 runs (engineer done 1)' in archive
    assert 'answers: 1 recorded through ask_user' in archive
    assert record['answers']['recent'][0]['answer'] == 'yes'
    assert record['verification'][0]['argv'] == ['uv', 'run', 'pytest']
    assert (repo.unit()['status'], repo.unit()['archive']) == (
        'closed',
        f'.mightymodels/archives/{SLUG}.md',
    )


def test_close_needs_a_shipped_line(repo: Repo) -> None:
    outcome = repo.run('close', stdin={'gotchas': []})
    assert outcome.code == REJECTED
    assert 'shipped is required' in outcome.err
    assert repo.unit()['status'] == 'in-progress'


def test_secrets_in_closing_lines_are_redacted(repo: Repo) -> None:
    repo.run('close', stdin={**CLOSING, 'gotchas': ['token=abc123 was in the log']})
    archive = (repo.base / 'archives' / f'{SLUG}.md').read_text(encoding='utf-8')
    assert 'abc123' not in archive


def test_a_repeated_slug_gets_its_own_archive(repo: Repo) -> None:
    (repo.base / 'archives').mkdir(parents=True)
    (repo.base / 'archives' / f'{SLUG}.md').write_text('# older\n', encoding='utf-8')
    repo.run('close', stdin=CLOSING)
    assert repo.unit()['archive'] == f'.mightymodels/archives/{SLUG}-2.md'


def test_prune_refuses_an_open_ticket(repo: Repo) -> None:
    outcome = repo.run('prune', '--confirm')
    assert outcome.code == REJECTED
    assert 'nothing was deleted' in outcome.err
    assert (repo.base / SLUG).is_dir()


def test_prune_without_confirm_only_lists(repo: Repo) -> None:
    repo.run('close', stdin=CLOSING)
    outcome = repo.run('prune')
    assert outcome.out.startswith('would remove (run again with --confirm):')
    assert f'.mightymodels/.runtime/investigations/{LEDGER}.jsonl' in outcome.out
    assert (repo.base / SLUG).is_dir()


def test_prune_removes_the_ticket_its_ledger_and_its_receipts(repo: Repo) -> None:
    repo.run('close', stdin=CLOSING)
    outcome = repo.run('prune', '--confirm')
    receipts = (repo.base / '.runtime' / 'subagents' / 'receipts.jsonl').read_text()
    assert outcome.code == 0, outcome.err
    assert not (repo.base / SLUG).exists()
    assert not (repo.base / '.runtime' / 'investigations' / f'{LEDGER}.jsonl').exists()
    assert [json.loads(line)['ticket'] for line in receipts.splitlines()] == ['other']
    answers = (repo.base / '.runtime' / 'decisions' / 'receipts.jsonl').read_text()
    assert answers == ''
    assert (repo.base / 'archives' / f'{SLUG}.md').is_file()


def test_a_ledger_another_ticket_links_is_kept(repo: Repo) -> None:
    repo.put('other/work-unit.json', {'schema': 1, 'investigations': [LEDGER]})
    repo.run('close', stdin=CLOSING)
    outcome = repo.run('prune', '--confirm')
    assert f'kept {LEDGER}: another ticket links it' in outcome.out
    assert (repo.base / '.runtime' / 'investigations' / f'{LEDGER}.jsonl').is_file()


def test_a_damaged_archive_stops_the_prune(repo: Repo) -> None:
    repo.run('close', stdin=CLOSING)
    (repo.base / 'archives' / f'{SLUG}.json').write_text('{broken', encoding='utf-8')
    outcome = repo.run('prune', '--confirm')
    assert 'failed its read-back' in outcome.err
    assert (repo.base / SLUG).is_dir()


def test_a_path_shaped_slug_is_refused(repo: Repo) -> None:
    code = repo.main(['prune', '--slug', '..', '--confirm'])
    assert code == REJECTED
    assert (repo.base / SLUG).is_dir()


STATE_FILES = [
    f'{SLUG}/work-unit.json',
    f'{SLUG}/verification/contract.json',
    f'{SLUG}/verification/receipts.jsonl',
    f'{SLUG}/review/20260928-120000/review-run.json',
    f'{SLUG}/review/20260928-120000/findings.jsonl',
    '.runtime/subagents/receipts.jsonl',
    f'.runtime/investigations/{LEDGER}.jsonl',
]


@pytest.mark.parametrize('relative', STATE_FILES)
@pytest.mark.parametrize('damaged', ['{broken', '[]', '{"schema": 2}'])
@pytest.mark.parametrize('command', ['close', 'prune'])
def test_unreadable_state_prevents_archiving_and_deletion(
    repo: Repo,
    relative: str,
    damaged: str,
    command: str,
) -> None:
    if command == 'prune':
        assert repo.run('close', stdin=CLOSING).code == 0
    path = repo.base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(damaged)
    outcome = repo.run(command, *(['--confirm'] if command == 'prune' else []), stdin=CLOSING)
    assert outcome.code == REJECTED
    assert 'repair the state' in outcome.err
    assert (repo.base / SLUG).is_dir()
    assert (repo.base / '.runtime' / 'investigations' / f'{LEDGER}.jsonl').exists()
    assert path.read_text() == damaged
    if command == 'close':
        assert not (repo.base / 'archives').exists()


@pytest.mark.parametrize(
    'progress',
    [[], {'tasks': []}, {'tasks': {'T1': []}}, {'tasks': {'T1': {'status': 'unknown'}}}],
)
def test_invalid_task_containers_are_not_treated_as_empty(repo: Repo, progress: object) -> None:
    repo.put(f'{SLUG}/work-unit.json', verified_unit(progress=progress))
    assert repo.run('close', stdin=CLOSING).code == REJECTED
    assert not (repo.base / 'archives').exists()


def test_a_staged_ticket_without_verified_work_cannot_close(repo: Repo) -> None:
    repo.put(f'{SLUG}/work-unit.json', verified_unit(progress={}))
    assert repo.run('close', stdin=CLOSING).code == BLOCKED


def test_live_work_added_after_closing_prevents_pruning(repo: Repo) -> None:
    repo.run('close', stdin=CLOSING)
    (repo.base / SLUG / 'whats-broken.md').write_text('new failure\n')
    assert repo.run('prune', '--confirm').code == BLOCKED
    assert (repo.base / SLUG).is_dir()


def test_corrupt_other_ticket_links_prevent_deleting_shared_ledgers(repo: Repo) -> None:
    repo.run('close', stdin=CLOSING)
    repo.put('other/work-unit.json', {'schema': 1, 'investigations': [LEDGER]})
    (repo.base / 'other' / 'work-unit.json').write_text('{broken')
    assert repo.run('prune', '--confirm').code == REJECTED
    assert (repo.base / '.runtime' / 'investigations' / f'{LEDGER}.jsonl').exists()
