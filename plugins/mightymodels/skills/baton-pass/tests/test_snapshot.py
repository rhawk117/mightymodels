"""Behavioral tests for scripts/snapshot.py against a real git repository."""

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

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'snapshot.py'
SLUG = 'retry-queue'
REJECTED = 2
GIT = shutil.which('git') or 'git'
IDENTITY = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')
OLD = 'a' * 40


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

    @property
    def ticket(self) -> Path:
        return self.root / '.mightymodels' / SLUG

    def put(self, relative: str, value: object) -> None:
        path = self.root / '.mightymodels' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def lines(self, relative: str, *records: object) -> None:
        path = self.root / '.mightymodels' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        text = ''.join(json.dumps(record) + '\n' for record in records)
        path.write_text(text, encoding='utf-8')

    def write(self, *extra: str) -> tuple[int, str]:
        code = self.main(['write', '--slug', SLUG, *extra])
        captured = self.capsys.readouterr()
        return code, captured.out + captured.err

    def snapshot(self, *extra: str) -> dict[str, Any]:
        code, output = self.write(*extra)
        assert code == 0, output
        text = (self.ticket / 'handoffs' / 'snapshot.json').read_text(encoding='utf-8')
        return json.loads(text)

    def markdown(self) -> str:
        return (self.ticket / 'handoffs' / 'snapshot.md').read_text(encoding='utf-8')


@pytest.fixture
def repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Repo:
    monkeypatch.chdir(tmp_path)
    space = Repo(tmp_path, capsys, runpy.run_path(str(SCRIPT))['main'])
    space.git('init', '-q', '-b', 'fix/retry')
    (tmp_path / 'queue.py').write_text('base\n', encoding='utf-8')
    space.git('add', 'queue.py')
    space.git('commit', '-q', '-m', 'base')
    unit = {
        'schema': 1,
        'status': 'in-progress',
        'ticket': {'summary': 'Retry queue drains slowly', 'scope': 'med'},
        'investigations': ['20260928-queue'],
    }
    space.put(f'{SLUG}/work-unit.json', unit)
    return space


def head(repo: Repo) -> str:
    return repo.git('rev-parse', 'HEAD')


def test_an_unstaged_ticket_writes_nothing(repo: Repo) -> None:
    (repo.ticket / 'work-unit.json').unlink()
    code, output = repo.write()
    assert code == REJECTED
    assert 'snapshot not written' in output
    assert not (repo.ticket / 'handoffs').exists()


def test_missing_sources_read_as_empty(repo: Repo) -> None:
    snapshot = repo.snapshot()
    assert snapshot['repository']['branch'] == 'fix/retry'
    assert (snapshot['checks'], snapshot['subagents'], snapshot['review']) == ([], [], {})
    assert snapshot['warnings'] == ['investigation 20260928-queue is missing']
    assert '- no receipts yet' in repo.markdown()


def test_checks_are_judged_at_head_and_passing_commands_are_kept(repo: Repo) -> None:
    commands = {
        'T1.AC-1': {'id': 'T1.AC-1', 'argv': ['uv', 'run', 'pytest', '-q']},
        'T1.AC-2': {'id': 'T1.AC-2', 'argv': ['ruff', 'check']},
        'T2.AC-1': {'id': 'T2.AC-1', 'argv': ['make', 'e2e']},
    }
    repo.put(f'{SLUG}/verification/contract.json', {'schema': 1, 'commands': commands})
    repo.lines(
        f'{SLUG}/verification/receipts.jsonl',
        {'schema': 1, 'id': 'T1.AC-1', 'outcome': 'pass', 'head': head(repo)},
        {'schema': 1, 'id': 'T1.AC-2', 'outcome': 'pass', 'head': OLD},
    )
    snapshot = repo.snapshot()
    assert snapshot['checks'] == [
        {'id': 'T1.AC-1', 'state': 'pass'},
        {'id': 'T1.AC-2', 'state': f'stale (pass at {OLD[:12]})'},
        {'id': 'T2.AC-1', 'state': 'never-run'},
    ]
    assert [work['id'] for work in snapshot['works']] == ['T1.AC-1', 'T1.AC-2']
    assert '- T1.AC-1: `uv run pytest -q`' in repo.markdown()


def test_open_tasks_include_contract_tasks_never_started(repo: Repo) -> None:
    progress = {
        'tasks': {
            'T1': {
                'status': 'blocked',
                'attempts': {'engineer': 1},
                'reasons': ['T1.AC-1 fail at HEAD'],
            }
        }
    }
    unit = json.loads((repo.ticket / 'work-unit.json').read_text(encoding='utf-8'))
    repo.put(f'{SLUG}/work-unit.json', {**unit, 'progress': progress})
    commands = {'T2.AC-1': {'id': 'T2.AC-1', 'argv': ['make']}}
    repo.put(f'{SLUG}/verification/contract.json', {'schema': 1, 'commands': commands})
    snapshot = repo.snapshot()
    assert [(t['task'], t['status']) for t in snapshot['tasks']] == [
        ('T1', 'blocked'),
        ('T2', 'not started'),
    ]
    assert '- T1 blocked (engineer 1 | T1.AC-1 fail at HEAD)' in repo.markdown()


def test_ledger_decisions_and_questions_skip_superseded_entries(repo: Repo) -> None:
    repo.lines(
        '.runtime/investigations/20260928-queue.jsonl',
        {'schema': 1, 'seq': 1, 'kind': 'target', 'text': 'queue'},
        {'schema': 1, 'seq': 2, 'kind': 'open', 'text': 'is backoff capped?'},
        {'schema': 1, 'seq': 3, 'kind': 'decision', 'text': 'keep the 10s floor'},
        {
            'schema': 1,
            'seq': 4,
            'kind': 'known',
            'text': 'cap is 60s',
            'cite': 'queue.py:9',
            'supersedes': [2],
        },
    )
    snapshot = repo.snapshot()
    assert snapshot['open_questions'] == []
    assert snapshot['decisions'] == [
        {
            'kind': 'decision',
            'text': 'keep the 10s floor',
            'cite': None,
            'from': '20260928-queue e3',
        },
    ]


def test_failed_attempts_become_do_not_retry_lines(repo: Repo) -> None:
    repo.lines(
        f'{SLUG}/transitions.jsonl',
        {'schema': 1, 'task': 'T1', 'to': 'in-progress', 'reasons': ['by engineer']},
        {
            'schema': 1,
            'task': 'T1',
            'to': 'failed',
            'reasons': ['AC-1 still red'],
            'head': OLD,
        },
    )
    snapshot = repo.snapshot()
    assert [entry['reason'] for entry in snapshot['do_not_retry']] == ['AC-1 still red']
    assert f'- T1 failed at {OLD[:12]}: AC-1 still red' in repo.markdown()


def test_the_latest_review_run_reports_open_remediation(repo: Repo) -> None:
    run = {
        'schema': 1,
        'run': '20260928-120000',
        'depth': 'deep',
        'head': OLD,
        'dispositions': {
            'F1': {'decision': 'fix'},
            'F2': {'decision': 'accept-risk', 'reason': 'internal only'},
        },
        'outcomes': {},
    }
    repo.put(f'{SLUG}/review/20260928-120000/review-run.json', run)
    repo.lines(
        f'{SLUG}/review/20260928-120000/findings.jsonl',
        {'schema': 1, 'id': 'F1'},
        {'schema': 1, 'id': 'F2'},
        {'schema': 1, 'id': 'F3'},
    )
    review = repo.snapshot()['review']
    assert (review['undecided'], review['remediation_open']) == (['F3'], ['F1'])
    assert review['decisions'] == [
        {'finding': 'F2', 'decision': 'accept-risk', 'reason': 'internal only'}
    ]


def test_subagent_receipts_are_filtered_to_the_ticket_and_bounded(repo: Repo) -> None:
    receipts = [
        {
            'schema': 1,
            'agent': 'code-scout',
            'status': 'VERIFIED',
            'ticket': SLUG,
            'summary': f'answer {n}',
        }
        for n in range(5)
    ]
    other = {'schema': 1, 'agent': 'engineer', 'status': 'done', 'ticket': 'other'}
    repo.lines('.runtime/subagents/receipts.jsonl', *receipts, other)
    snapshot = repo.snapshot('--limit', '2')
    assert [s['summary'] for s in snapshot['subagents']] == ['answer 3', 'answer 4']


def test_unsupported_schema_records_are_skipped_visibly(repo: Repo) -> None:
    repo.lines(
        '.runtime/subagents/receipts.jsonl',
        {'schema': 2, 'agent': 'engineer', 'ticket': SLUG},
    )
    snapshot = repo.snapshot()
    assert snapshot['subagents'] == []
    assert 'receipts.jsonl: schema 2 is not supported; ignored' in snapshot['warnings']
    assert '## Warnings' in repo.markdown()


def test_a_dirty_tree_is_listed(repo: Repo) -> None:
    (repo.root / 'queue.py').write_text('changed\n', encoding='utf-8')
    repository = repo.snapshot()['repository']
    assert (repository['dirty_count'], repository['dirty']) == (1, ['queue.py'])


def test_a_path_shaped_slug_is_refused(repo: Repo) -> None:
    code = repo.main(['write', '--slug', '../../etc'])
    assert code == REJECTED
    assert 'is not a ticket slug' in repo.capsys.readouterr().err


def test_recorded_answers_for_this_ticket_are_listed(repo: Repo) -> None:
    answers = [
        {
            'schema': 1,
            'id': 'd-1',
            'ticket': SLUG,
            'question': 'Tracker?',
            'answer': 'Jira',
        },
        {'schema': 1, 'id': 'd-2', 'ticket': 'other', 'question': 'x', 'answer': 'y'},
    ]
    repo.lines('.runtime/decisions/receipts.jsonl', *answers)
    snapshot = repo.snapshot()
    assert [answer['id'] for answer in snapshot['answers']] == ['d-1']
    assert '- d-1: Tracker? -> Jira' in repo.markdown()


def test_a_worker_stopped_twice_by_the_gate_is_listed_once(repo: Repo) -> None:
    stops = [
        {
            'schema': 1,
            'agent': 'engineer',
            'agent_id': 'a-1',
            'status': 'done',
            'ticket': SLUG,
            'summary': 'first stop',
        },
        {
            'schema': 1,
            'agent': 'engineer',
            'agent_id': 'a-1',
            'status': 'done',
            'ticket': SLUG,
            'summary': 'second stop',
        },
    ]
    repo.lines('.runtime/subagents/receipts.jsonl', *stops)
    assert [s['summary'] for s in repo.snapshot()['subagents']] == ['second stop']
