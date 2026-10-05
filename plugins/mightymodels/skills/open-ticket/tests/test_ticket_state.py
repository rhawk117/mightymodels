"""Behavioral tests for scripts/ticket_state.py, driven through its entry point."""

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

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'ticket_state.py'
REJECTED = 2
SLUG = 'retry-queue'
ANSWERS = {
    'summary': 'Retry queue drains at a tenth of its rate after 2am',
    'scope': 'med',
    'compaction': False,
    'branch': 'fix/retry-queue',
    'context': ['drain loop sleeps between batches', 'user: correlates with compaction'],
    'issue': 42,
}


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

    def run(self, command: str, answers: object = None) -> Outcome:
        payload = '' if answers is None else json.dumps(answers)
        self.monkeypatch.setattr('sys.stdin', io.StringIO(payload))
        code = self.main([command, '--slug', SLUG])
        captured = self.capsys.readouterr()
        return Outcome(code=code, out=captured.out, err=captured.err)

    @property
    def ticket(self) -> Path:
        return self.root / '.mightymodels' / SLUG / 'ticket.yml'

    @property
    def work_unit(self) -> Path:
        return self.root / '.mightymodels' / SLUG / 'work-unit.json'

    def edit(self, old: str, new: str) -> None:
        text = self.ticket.read_text(encoding='utf-8')
        self.ticket.write_text(text.replace(old, new), encoding='utf-8')


@pytest.fixture
def workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Workspace:
    (tmp_path / '.git').mkdir()
    monkeypatch.chdir(tmp_path)
    main = runpy.run_path(str(SCRIPT))['main']
    return Workspace(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys, main=main)


@pytest.mark.parametrize(
    ('scope', 'models'),
    [
        ('sm', ('gpt-5.6-luna', 'gpt-5.6-terra')),
        ('med', ('gpt-5.6-luna', 'gpt-5.6-terra')),
        ('large', ('claude-sonnet-5', 'gpt-5.6-sol')),
    ],
)
def test_write_derives_the_implementer_models_from_scope(
    workspace: Workspace, scope: str, models: tuple[str, str]
) -> None:
    engineer, architect = models
    outcome = workspace.run('write', {**ANSWERS, 'scope': scope})
    text = workspace.ticket.read_text(encoding='utf-8')
    assert outcome.code == 0
    assert f'  engineer: "{engineer}"' in text
    assert f'  architect: "{architect}"' in text


def test_write_derives_plan_first_from_the_compaction_answer(
    workspace: Workspace,
) -> None:
    workspace.run('write', {**ANSWERS, 'compaction': True})
    assert '  plan-first: true' in workspace.ticket.read_text(encoding='utf-8')


def test_write_keeps_mightymodels_out_of_git_once(workspace: Workspace) -> None:
    workspace.run('write', ANSWERS)
    workspace.run('validate')
    exclude = workspace.root / '.git' / 'info' / 'exclude'
    assert exclude.read_text(encoding='utf-8').splitlines().count('.mightymodels/') == 1


def test_write_refuses_to_overwrite_a_tweaked_ticket(workspace: Workspace) -> None:
    workspace.run('write', ANSWERS)
    outcome = workspace.run('write', ANSWERS)
    assert outcome.code == REJECTED
    assert 'edit it by hand' in outcome.err


def test_write_rejects_incomplete_answers(workspace: Workspace) -> None:
    outcome = workspace.run('write', {'scope': 'sm'})
    assert outcome.code == REJECTED
    assert 'summary' in outcome.err
    assert not workspace.ticket.exists()


def test_validate_stages_the_work_unit(workspace: Workspace) -> None:
    workspace.run('write', ANSWERS)
    outcome = workspace.run('validate')
    unit = json.loads(workspace.work_unit.read_text(encoding='utf-8'))
    assert 'status staged' in outcome.out
    assert (unit['status'], unit['ticket']['branch']) == ('staged', 'fix/retry-queue')
    assert unit['ticket']['tracker'] == {'issue': 42, 'jira': None}
    assert unit['ticket']['models']['uncle-bob-reviewer'] == 'claude-sonnet-5'


def test_hand_edits_inside_the_subset_validate(workspace: Workspace) -> None:
    workspace.run('write', ANSWERS)
    workspace.edit('  scope: "med"', '  scope: large   # bumped after review')
    outcome = workspace.run('validate')
    unit = json.loads(workspace.work_unit.read_text(encoding='utf-8'))
    assert outcome.code == 0
    assert unit['ticket']['scope'] == 'large'


def test_syntax_outside_the_subset_is_refused_with_its_line(workspace: Workspace) -> None:
    workspace.run('write', ANSWERS)
    workspace.edit('reference-urls:', 'reference-urls: [a, b]')
    outcome = workspace.run('validate')
    assert outcome.code == REJECTED
    assert 'ticket.yml:' in outcome.err
    assert 'unsupported YAML syntax' in outcome.err


def test_retired_worker_keys_are_refused(workspace: Workspace) -> None:
    workspace.run('write', ANSWERS)
    workspace.edit('subagent-models:\n', 'subagent-models:\n  scout: gpt-5.6-luna\n')
    outcome = workspace.run('validate')
    assert outcome.code == REJECTED
    assert "unknown workers ['scout']" in outcome.err


def test_linked_investigations_must_exist(workspace: Workspace) -> None:
    outcome = workspace.run('write', {**ANSWERS, 'investigations': ['20260928-missing']})
    assert outcome.code == REJECTED
    assert 'investigation 20260928-missing has no ledger file' in outcome.err


def test_revalidation_keeps_progress_and_only_adds_links(workspace: Workspace) -> None:
    runtime = workspace.root / '.mightymodels' / '.runtime' / 'investigations'
    runtime.mkdir(parents=True)
    (runtime / 'inv-a.jsonl').write_text('', encoding='utf-8')
    workspace.run('write', {**ANSWERS, 'investigations': ['inv-a']})
    workspace.run('validate')
    unit = json.loads(workspace.work_unit.read_text(encoding='utf-8'))
    progressed = {**unit, 'status': 'in-progress', 'tasks': {'T1': 'verified'}}
    workspace.work_unit.write_text(json.dumps(progressed), encoding='utf-8')
    workspace.run('validate')
    refreshed = json.loads(workspace.work_unit.read_text(encoding='utf-8'))
    assert (refreshed['status'], refreshed['tasks']) == (
        'in-progress',
        {'T1': 'verified'},
    )
    assert refreshed['investigations'] == ['inv-a']


def test_exclude_goes_to_the_common_dir_from_a_worktree(workspace: Workspace) -> None:
    common = workspace.root / 'main' / '.git'
    worktree_git = common / 'worktrees' / 'feature'
    worktree_git.mkdir(parents=True)
    (worktree_git / 'commondir').write_text('../..\n', encoding='utf-8')
    (workspace.root / '.git').rmdir()
    (workspace.root / '.git').write_text(f'gitdir: {worktree_git}\n', encoding='utf-8')
    workspace.run('write', ANSWERS)
    exclude = common / 'info' / 'exclude'
    assert exclude.read_text(encoding='utf-8') == '.mightymodels/\n'


def test_outside_a_repository_nothing_is_written(workspace: Workspace) -> None:
    (workspace.root / '.git').rmdir()
    outcome = workspace.run('write', ANSWERS)
    assert outcome.code == REJECTED
    assert 'not inside a git repository' in outcome.err


def test_hashes_and_colons_inside_quoted_values_survive(workspace: Workspace) -> None:
    summary = 'Quote "x" and colon: y # not a comment'
    workspace.run('write', {**ANSWERS, 'summary': summary, 'context': ['a: b', 'c # d']})
    workspace.edit('context:\n', 'context:   # rollup lines\n')
    outcome = workspace.run('validate')
    unit = json.loads(workspace.work_unit.read_text(encoding='utf-8'))
    assert outcome.code == 0
    assert unit['ticket']['summary'] == summary
