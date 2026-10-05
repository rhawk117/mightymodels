"""Behavioral tests for scripts/ledger.py, driven through its command-line entry point."""

from __future__ import annotations

import io
import json
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'ledger.py'
REJECTED = 2
FAKE_TOKEN = 'ghp_' + 'a' * 36


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
        code = self.main(list(argv))
        captured = self.capsys.readouterr()
        return Outcome(code=code, out=captured.out, err=captured.err)

    def start(self) -> str:
        outcome = self.run('start', '--target', 'Queue drains slowly', '--kind', 'behavior')
        return outcome.out.split()[1]

    def ledger_file(self, investigation: str) -> Path:
        return (
            self.root / '.mightymodels' / '.runtime' / 'investigations' / (f'{investigation}.jsonl')
        )


@pytest.fixture
def workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Workspace:
    (tmp_path / '.git').mkdir()
    monkeypatch.chdir(tmp_path)
    main = runpy.run_path(str(SCRIPT))['main']
    return Workspace(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys, main=main)


def known(text: str, cite: str) -> dict[str, str]:
    return {'kind': 'known', 'text': text, 'cite': cite, 'source': 'code-scout'}


def test_start_writes_a_versioned_target_record(workspace: Workspace) -> None:
    investigation = workspace.start()
    lines = workspace.ledger_file(investigation).read_text(encoding='utf-8').splitlines()
    record = json.loads(lines[0])
    assert investigation.endswith('queue-drains-slowly')
    assert (record['schema'], record['kind'], record['cite']) == (1, 'target', 'behavior')


def test_a_ledger_in_a_repository_is_never_tracked(workspace: Workspace) -> None:
    workspace.start()
    exclude = workspace.root / '.git' / 'info' / 'exclude'
    assert '.mightymodels/' in exclude.read_text(encoding='utf-8').splitlines()


def test_added_known_renders_with_its_citation(workspace: Workspace) -> None:
    investigation = workspace.start()
    entry = known('drain loop sleeps 10s', 'src/queue.py:41')
    saved = workspace.run('add', '--id', investigation, '--round', '1', stdin=[entry])
    rendered = workspace.run('render', '--id', investigation)
    assert saved.out.startswith('saved e2 ')
    assert '- e2: drain loop sleeps 10s [src/queue.py:41] (code-scout, round 1)' in (rendered.out)


@pytest.mark.parametrize(
    ('entry', 'reason'),
    [
        ({'kind': 'known', 'text': 'no cite', 'source': 'code-scout'}, 'needs a cite'),
        (
            {'kind': 'decision', 'text': 'use v2', 'source': 'primary'},
            'cannot come from primary',
        ),
        ({'kind': 'target', 'text': 'x', 'source': 'user'}, 'written by start'),
        ({'kind': 'open', 'text': '  ', 'source': 'user'}, 'text is empty'),
        ({'kind': 'nonsense', 'text': 'x', 'source': 'user'}, 'invalid field'),
    ],
)
def test_invalid_entry_is_rejected_without_writing(
    workspace: Workspace, entry: dict[str, str], reason: str
) -> None:
    investigation = workspace.start()
    before = workspace.ledger_file(investigation).read_text(encoding='utf-8')
    valid = known('first', 'a.py:1')
    outcome = workspace.run('add', '--id', investigation, '--round', '1', stdin=[valid, entry])
    after = workspace.ledger_file(investigation).read_text(encoding='utf-8')
    assert outcome.code == REJECTED
    assert reason in outcome.err
    assert before == after


def test_secrets_are_redacted_before_they_reach_disk(workspace: Workspace) -> None:
    investigation = workspace.start()
    entry = known(f'CI uses {FAKE_TOKEN} and password=hunter2', 'ci.yml:3')
    saved = workspace.run('add', '--id', investigation, '--round', '1', stdin=[entry])
    stored = workspace.ledger_file(investigation).read_text(encoding='utf-8')
    assert '(2 redacted)' in saved.out
    assert FAKE_TOKEN not in stored
    assert 'hunter2' not in stored


def test_superseded_entries_leave_the_rendered_ledger(workspace: Workspace) -> None:
    investigation = workspace.start()
    question = {'kind': 'open', 'text': 'is backoff 30s?', 'source': 'web-scout'}
    workspace.run('add', '--id', investigation, '--round', '1', stdin=[question])
    answer = {
        **known('backoff is 30s', 'https://docs.example/q#backoff'),
        'supersedes': [2],
    }
    workspace.run('add', '--id', investigation, '--round', '2', stdin=[answer])
    rendered = workspace.run('render', '--id', investigation).out
    stored = workspace.ledger_file(investigation).read_text(encoding='utf-8')
    assert 'is backoff 30s?' not in rendered
    assert 'backoff is 30s' in rendered
    assert 'is backoff 30s?' in stored


def test_superseding_an_unknown_entry_is_rejected(workspace: Workspace) -> None:
    investigation = workspace.start()
    entry = {**known('x', 'a.py:1'), 'supersedes': [99]}
    outcome = workspace.run('add', '--id', investigation, '--round', '1', stdin=[entry])
    assert outcome.code == REJECTED
    assert 'supersedes unknown entries [99]' in outcome.err


def test_only_the_latest_round_next_questions_render(workspace: Workspace) -> None:
    investigation = workspace.start()
    first = {'kind': 'next', 'text': 'find callers', 'source': 'code-scout'}
    second = {'kind': 'next', 'text': 'fetch changelog', 'source': 'web-scout'}
    workspace.run('add', '--id', investigation, '--round', '1', stdin=[first])
    workspace.run('add', '--id', investigation, '--round', '2', stdin=[second])
    rendered = workspace.run('render', '--id', investigation).out
    assert 'fetch changelog' in rendered
    assert 'find callers' not in rendered


def test_an_earlier_round_is_rejected(workspace: Workspace) -> None:
    investigation = workspace.start()
    workspace.run('add', '--id', investigation, '--round', '2', stdin=[known('a', 'a:1')])
    outcome = workspace.run('add', '--id', investigation, '--round', '1', stdin=[])
    assert outcome.code == REJECTED
    assert 'earlier than the latest round 2' in outcome.err


def test_an_unsupported_schema_is_refused(workspace: Workspace) -> None:
    investigation = workspace.start()
    path = workspace.ledger_file(investigation)
    record = json.loads(path.read_text(encoding='utf-8'))
    path.write_text(json.dumps({**record, 'schema': 99}) + '\n', encoding='utf-8')
    outcome = workspace.run('render', '--id', investigation)
    assert outcome.code == REJECTED
    assert 'schema 99 is not supported' in outcome.err


def test_unknown_investigation_names_the_list_command(workspace: Workspace) -> None:
    outcome = workspace.run('render', '--id', 'missing')
    assert outcome.code == REJECTED
    assert 'run list' in outcome.err


def test_list_reports_each_investigation_with_its_round(workspace: Workspace) -> None:
    investigation = workspace.start()
    workspace.run('add', '--id', investigation, '--round', '3', stdin=[known('a', 'a:1')])
    assert workspace.run('list').out == f'{investigation}\tround 3\n'


def test_outside_a_repository_state_goes_under_home(workspace: Workspace) -> None:
    outside = workspace.root / 'outside'
    home = workspace.root / 'home'
    outside.mkdir()
    (workspace.root / '.git').rmdir()
    workspace.monkeypatch.chdir(outside)
    workspace.monkeypatch.setenv('HOME', str(home))
    workspace.start()
    stored = list((home / '.local' / 'state' / 'mightymodels').glob('*/investigations/*'))
    assert len(stored) == 1


def test_long_targets_are_cut_at_a_word_boundary(workspace: Workspace) -> None:
    target = 'Retry queue drains at a tenth of its rate after 2am'
    outcome = workspace.run('start', '--target', target, '--kind', 'behavior')
    assert outcome.out.split()[1].endswith('-retry-queue-drains-at-a-tenth-of-its')


SHA_A = 'a' * 40
SHA_B = 'b' * 40


def point_head(git: Path, sha: str) -> None:
    (git / 'refs' / 'heads').mkdir(parents=True, exist_ok=True)
    (git / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
    (git / 'refs' / 'heads' / 'main').write_text(f'{sha}\n', encoding='utf-8')


def test_entries_verified_at_head_are_current(workspace: Workspace) -> None:
    point_head(workspace.root / '.git', SHA_A)
    investigation = workspace.start()
    workspace.run('add', '--id', investigation, '--round', '1', stdin=[known('a', 'a:1')])
    table = workspace.run('knowns', '--id', investigation).out
    assert f'at HEAD {SHA_A[:12]}' in table
    assert '| e2 | known | a | a:1 | code-scout | 1 | current |' in table


def test_entries_from_an_older_head_become_leads(workspace: Workspace) -> None:
    git = workspace.root / '.git'
    point_head(git, SHA_A)
    investigation = workspace.start()
    workspace.run('add', '--id', investigation, '--round', '1', stdin=[known('a', 'a:1')])
    point_head(git, SHA_B)
    workspace.run('add', '--id', investigation, '--round', '2', stdin=[known('b', 'b:1')])
    table = workspace.run('knowns', '--id', investigation).out
    assert '| e2 | known | a | a:1 | code-scout | 1 | lead |' in table
    assert '| e3 | known | b | b:1 | code-scout | 2 | current |' in table


def test_head_resolves_through_packed_refs(workspace: Workspace) -> None:
    git = workspace.root / '.git'
    (git / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
    packed = f'# pack-refs with: peeled\n{SHA_B} refs/heads/main\n'
    (git / 'packed-refs').write_text(packed, encoding='utf-8')
    investigation = workspace.start()
    record = json.loads(workspace.ledger_file(investigation).read_text(encoding='utf-8'))
    assert record['head'] == SHA_B


def test_head_resolves_from_a_worktree(workspace: Workspace) -> None:
    common = workspace.root / 'main-repo' / '.git'
    worktree_git = common / 'worktrees' / 'feature'
    worktree_git.mkdir(parents=True)
    point_head(common, SHA_A)
    (worktree_git / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
    (worktree_git / 'commondir').write_text('../..\n', encoding='utf-8')
    (workspace.root / '.git').rmdir()
    (workspace.root / '.git').write_text(f'gitdir: {worktree_git}\n', encoding='utf-8')
    investigation = workspace.start()
    record = json.loads(workspace.ledger_file(investigation).read_text(encoding='utf-8'))
    assert record['head'] == SHA_A


def test_detached_head_is_the_sha_itself(workspace: Workspace) -> None:
    (workspace.root / '.git' / 'HEAD').write_text(f'{SHA_B}\n', encoding='utf-8')
    investigation = workspace.start()
    record = json.loads(workspace.ledger_file(investigation).read_text(encoding='utf-8'))
    assert record['head'] == SHA_B


def test_knowns_table_is_bounded_filtered_and_escaped(workspace: Workspace) -> None:
    investigation = workspace.start()
    entries = [known(f'a | {index}', 'a:1') for index in range(3)]
    entries.append({'kind': 'open', 'text': 'why?', 'source': 'user'})
    workspace.run('add', '--id', investigation, '--round', '1', stdin=entries)
    table = workspace.run('knowns', '--id', investigation, '--kind', 'known', '--limit', '2').out
    assert r'a \| 0' in table
    assert 'why?' not in table
    assert '1 more rows; rerun with a larger --limit' in table
