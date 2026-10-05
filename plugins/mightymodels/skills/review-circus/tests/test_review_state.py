"""Behavioral tests for scripts/review_state.py via its entry point."""

from __future__ import annotations

import io
import json
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'review_state.py'
SLUG = 'retry-queue'
REJECTED = 2
SHA = 'c' * 40


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

    def start(self, *extra: str) -> str:
        outcome = self.run('start', '--scope', 'ticket', '--slug', SLUG, '--base', 'main', *extra)
        assert outcome.code == 0, outcome.err
        return outcome.out.split()[1]

    def directory(self, run: str) -> Path:
        return self.root / '.mightymodels' / SLUG / 'review' / run

    def state(self, run: str) -> dict[str, Any]:
        text = (self.directory(run) / 'review-run.json').read_text(encoding='utf-8')
        return json.loads(text)


@pytest.fixture
def workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Workspace:
    git = tmp_path / '.git'
    (git / 'refs' / 'heads').mkdir(parents=True)
    (git / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
    (git / 'refs' / 'heads' / 'main').write_text(f'{SHA}\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    main = runpy.run_path(str(SCRIPT))['main']
    return Workspace(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys, main=main)


def finding(source: str, severity: str, location: str, **extra: object) -> dict[str, Any]:
    return {
        'sources': [source],
        'severity': severity,
        'title': f'{source} title',
        'location': location,
        'fix': 'do the thing',
        'verify': 'uv run pytest -q',
        **extra,
    }


def test_deep_review_runs_both_personas_on_the_ticket_models(
    workspace: Workspace,
) -> None:
    unit = workspace.root / '.mightymodels' / SLUG / 'work-unit.json'
    unit.parent.mkdir(parents=True)
    models = {
        'uncle-bob-reviewer': 'claude-opus-5',
        'merge-vader-reviewer': 'gpt-5.6-sol',
    }
    unit.write_text(json.dumps({'ticket': {'models': models}}), encoding='utf-8')
    run = workspace.start('--depth', 'deep', '--emphasis', 'balanced')
    state = workspace.state(run)
    assert state['personas'] == ['merge-vader', 'uncle-bob']
    assert state['models'] == models
    assert state['head'] == SHA


def test_quick_review_runs_the_heavier_persona_on_luna(workspace: Workspace) -> None:
    run = workspace.start('--depth', 'quick', '--emphasis', 'maintainability')
    assert workspace.state(run)['models'] == {'uncle-bob-reviewer': 'gpt-5.6-luna'}


def test_quick_review_with_tied_weights_needs_a_persona(workspace: Workspace) -> None:
    outcome = workspace.run(
        'start', '--scope', 'codebase', '--depth', 'quick', '--emphasis', 'balanced'
    )
    assert outcome.code == REJECTED
    assert 'pass --persona' in outcome.err


def test_standard_review_drops_a_persona_below_the_threshold(
    workspace: Workspace,
) -> None:
    weights = ('--weights', 'merge-vader=0.8,uncle-bob=0.2')
    run = workspace.start('--depth', 'standard', '--emphasis', 'custom', *weights)
    assert workspace.state(run)['models'] == {'merge-vader-reviewer': 'gpt-5.6-terra'}


def test_custom_weights_must_sum_to_one(workspace: Workspace) -> None:
    outcome = workspace.run(
        'start',
        '--scope',
        'codebase',
        '--depth',
        'deep',
        '--emphasis',
        'custom',
        '--weights',
        'merge-vader=0.8,uncle-bob=0.8',
    )
    assert 'must sum to 1' in outcome.err


def test_a_run_without_a_ticket_lives_under_runtime(workspace: Workspace) -> None:
    outcome = workspace.run(
        'start', '--scope', 'codebase', '--depth', 'deep', '--emphasis', 'balanced'
    )
    run = outcome.out.split()[1]
    exclude = (workspace.root / '.git' / 'info' / 'exclude').read_text(encoding='utf-8')
    runtime = workspace.root / '.mightymodels' / '.runtime' / 'reviews' / run
    assert (runtime / 'review-run.json').is_file()
    assert '.mightymodels/' in exclude.splitlines()


def test_findings_get_stable_ids_and_uncle_bob_blockers_become_critical(
    workspace: Workspace,
) -> None:
    run = workspace.start('--depth', 'deep', '--emphasis', 'balanced')
    batch = [
        finding('MV-1', 'High', 'src/queue.py:10', security=True),
        finding('UB-1', 'Blocker', 'src/store.py:4-9'),
    ]
    outcome = workspace.run('add', '--run', run, stdin=batch)
    gate = workspace.run('gate', '--run', run).out.splitlines()
    assert 'recorded: F1, F2' in outcome.out
    assert gate[0].startswith('F2\tCritical\t[UB-1]')
    assert gate[1].startswith('F1\tHigh security\t[MV-1]')


def test_overlapping_findings_merge_and_keep_the_higher_severity(
    workspace: Workspace,
) -> None:
    run = workspace.start('--depth', 'deep', '--emphasis', 'balanced')
    workspace.run('add', '--run', run, stdin=[finding('MV-2', 'Medium', 'src/q.py:10-20')])
    workspace.run('add', '--run', run, stdin=[finding('UB-4', 'High', 'src/q.py:15')])
    gate = workspace.run('gate', '--run', run).out
    assert gate.startswith('F1\tHigh\t[MV-2/UB-4]\tsrc/q.py:15\tUB-4 title')
    assert 'conflict' not in gate


def test_a_two_level_gap_is_flagged_for_the_user(workspace: Workspace) -> None:
    run = workspace.start('--depth', 'deep', '--emphasis', 'balanced')
    batch = [
        finding('MV-1', 'Critical', 'src/q.py:3'),
        finding('UB-1', 'Low', 'src/q.py:3'),
    ]
    workspace.run('add', '--run', run, stdin=batch)
    gate = workspace.run('gate', '--run', run).out
    assert 'conflict: UB-1 rated Low, MV-1 rated Critical: the user decides' in gate


def test_quality_findings_need_structured_evidence(workspace: Workspace) -> None:
    run = workspace.start('--depth', 'deep', '--emphasis', 'balanced')
    preference = finding('UB-3', 'Medium', 'src/q.py:1', kind='quality')
    refused = workspace.run('add', '--run', run, stdin=[preference])
    metric = {'kind': 'metric', 'cite': 'uncle-bob-metrics.json functions_over_20_loc'}
    backed = workspace.run('add', '--run', run, stdin=[{**preference, 'evidence': metric}])
    assert refused.code == REJECTED
    assert 'needs structured evidence' in refused.err
    assert backed.code == 0


def test_a_bad_finding_rejects_the_whole_batch(workspace: Workspace) -> None:
    run = workspace.start('--depth', 'deep', '--emphasis', 'balanced')
    batch = [finding('MV-1', 'High', 'src/q.py:1'), finding('MV-2', 'High', 'nowhere')]
    outcome = workspace.run('add', '--run', run, stdin=batch)
    assert 'finding 1: location must be' in outcome.err
    assert workspace.run('gate', '--run', run).out == 'no findings recorded\n'


def test_secrets_in_findings_are_redacted(workspace: Workspace) -> None:
    run = workspace.start('--depth', 'deep', '--emphasis', 'balanced')
    leaked = finding('MV-1', 'Critical', 'cfg.py:2', title='hardcoded password=hunter22')
    workspace.run('add', '--run', run, stdin=[leaked])
    stored = (workspace.directory(run) / 'findings.jsonl').read_text(encoding='utf-8')
    assert 'hunter22' not in stored
    assert '[REDACTED:assignment]' in stored


def test_weights_order_findings_inside_a_severity(workspace: Workspace) -> None:
    run = workspace.start('--depth', 'deep', '--emphasis', 'maintainability')
    batch = [finding('MV-1', 'Medium', 'a.py:1'), finding('UB-1', 'Medium', 'b.py:1')]
    workspace.run('add', '--run', run, stdin=batch)
    gate = workspace.run('gate', '--run', run).out.splitlines()
    assert [line.split('\t')[2] for line in gate] == ['[UB-1]', '[MV-1]']


def test_accepting_risk_needs_a_reason(workspace: Workspace) -> None:
    run = workspace.start('--depth', 'deep', '--emphasis', 'balanced')
    workspace.run('add', '--run', run, stdin=[finding('MV-1', 'High', 'a.py:1')])
    decision = {'by': 'user', 'decisions': {'F1': {'decision': 'accept-risk'}}}
    outcome = workspace.run('dispose', '--run', run, stdin=decision)
    assert outcome.code == REJECTED
    assert 'accept-risk needs a reason' in outcome.err


def test_the_verdict_follows_the_decisions_and_the_fixes(workspace: Workspace) -> None:
    run = workspace.start('--depth', 'deep', '--emphasis', 'balanced')
    batch = [finding('MV-1', 'High', 'a.py:1'), finding('MV-2', 'Medium', 'b.py:1')]
    workspace.run('add', '--run', run, stdin=batch)
    before = workspace.run('report', '--run', run).out
    decisions = {
        'F1': {'decision': 'fix'},
        'F2': {'decision': 'defer', 'reason': 'ticketed as PLAT-9'},
    }
    workspace.run('dispose', '--run', run, stdin={'by': 'user', 'decisions': decisions})
    workspace.run(
        'resolve',
        '--run',
        run,
        '--finding',
        'F1',
        '--result',
        'fixed',
        '--commit',
        'abc123',
    )
    after = workspace.run('report', '--run', run, '--shape', 'comment').out
    comment = (workspace.directory(run) / 'pr-comment.md').read_text(encoding='utf-8')
    assert before.endswith('(BLOCK)\n')
    assert after.endswith('(MERGE WITH CONDITIONS)\n')
    assert '- F1 (High, fixed): MV-1 title. `a.py:1`' in comment


def test_only_findings_chosen_for_fixing_are_resolved(workspace: Workspace) -> None:
    run = workspace.start('--depth', 'deep', '--emphasis', 'balanced')
    workspace.run('add', '--run', run, stdin=[finding('MV-1', 'High', 'a.py:1')])
    outcome = workspace.run(
        'resolve', '--run', run, '--finding', 'F1', '--result', 'fixed', '--commit', 'abc'
    )
    assert 'only a finding the user chose to fix is resolved' in outcome.err


def test_a_path_shaped_run_id_is_refused(workspace: Workspace) -> None:
    outcome = workspace.run('gate', '--run', '../../etc')
    assert outcome.code == REJECTED
    assert "--run '../../etc' is not valid" in outcome.err
