"""The PreToolUse hook on Agent denies a worker's dispatch outside the row its agent file states."""

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from mightymodels_plugin.cli import main
from mightymodels_plugin.commands.dispatch_hook import DISPATCH_RULES, check_dispatch
from mightymodels_plugin.routing import Worker

AGENTS = Path(__file__).parent.parent.joinpath('agents')
ROW_LINE = re.compile(r'^- (?:Delegate|Dispatch) only (?:to )?(?P<names>[^.]*)\.', re.MULTILINE)
BACKTICKED = re.compile(r'`([\w-]+)`')
PREFIX = 'mightymodels:'
EMPTY_ROW = (
    Worker.CODE_SCOUT,
    Worker.WEB_SCOUT,
    Worker.QUALITYLENS,
    Worker.GITTY_UP,
    Worker.WINGMAN,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class Verdict:
    decision: str | None
    reason: str


def hook_input(caller: str | None, target: str | None) -> str:
    fields: dict[str, object] = {'tool_name': 'Agent', 'tool_input': {'subagent_type': target}}
    if caller is not None:
        fields['agent_type'] = caller
    return json.dumps(fields)


def run_hook(text: str) -> Verdict:
    stdout = io.StringIO()
    assert check_dispatch(io.StringIO(text), stdout) == 0
    printed = stdout.getvalue()
    if not printed:
        return Verdict(decision=None, reason='')
    output = json.loads(printed)['hookSpecificOutput']
    assert output['hookEventName'] == 'PreToolUse'
    return Verdict(decision=output['permissionDecision'], reason=output['permissionDecisionReason'])


def row_stated_by(worker: Worker) -> frozenset[str]:
    body = AGENTS.joinpath(f'{worker}.md').read_text(encoding='utf-8')
    found = ROW_LINE.search(body)
    return frozenset(BACKTICKED.findall(found['names'])) if found else frozenset()


class TestWorkerRow:
    @pytest.mark.parametrize(
        ('caller', 'target'),
        [
            pytest.param('engineer', 'code-scout', id='engineer-to-code-scout'),
            pytest.param('architect', 'code-scout', id='architect-to-code-scout'),
            pytest.param('merge-vader-reviewer', 'web-scout', id='merge-vader-to-web-scout'),
            pytest.param('merge-vader-reviewer', 'qualitylens', id='merge-vader-to-qualitylens'),
            pytest.param('uncle-bob-reviewer', 'qualitylens', id='uncle-bob-to-qualitylens'),
        ],
    )
    def test_a_target_inside_the_row_is_allowed(self, caller: str, target: str) -> None:
        assert run_hook(hook_input(caller, target)) == Verdict(decision=None, reason='')

    @pytest.mark.parametrize(
        ('caller', 'target', 'may_dispatch'),
        [
            pytest.param('engineer', 'web-scout', 'code-scout', id='engineer-to-web-scout'),
            pytest.param('engineer', 'engineer', 'code-scout', id='engineer-to-engineer'),
            pytest.param('architect', 'engineer', 'code-scout', id='architect-to-engineer'),
            pytest.param(
                'uncle-bob-reviewer',
                'web-scout',
                'code-scout, qualitylens',
                id='uncle-bob-to-web-scout',
            ),
            pytest.param(
                'merge-vader-reviewer',
                'architect',
                'code-scout, qualitylens, web-scout',
                id='merge-vader-to-architect',
            ),
            pytest.param('engineer', 'general-purpose', 'code-scout', id='built-in-target'),
            pytest.param('engineer', 'other:code-scout', 'code-scout', id='other-plugin-target'),
        ],
    )
    def test_a_target_outside_the_row_is_denied_with_the_row_named(
        self, caller: str, target: str, may_dispatch: str
    ) -> None:
        verdict = run_hook(hook_input(caller, target))

        assert verdict.decision == 'deny'
        assert (
            verdict.reason == f'{caller} may not dispatch {target}; it may dispatch: {may_dispatch}'
        )

    @pytest.mark.parametrize('caller', EMPTY_ROW)
    @pytest.mark.parametrize('target', [*Worker, 'general-purpose'])
    def test_a_worker_with_an_empty_row_is_denied_every_target(
        self, caller: Worker, target: str
    ) -> None:
        verdict = run_hook(hook_input(caller, target))

        assert verdict.decision == 'deny'
        assert verdict.reason.endswith('it may dispatch: nothing')


class TestNames:
    @pytest.mark.parametrize(
        ('caller', 'target'),
        [
            pytest.param('engineer', 'code-scout', id='bare-both'),
            pytest.param(f'{PREFIX}engineer', 'code-scout', id='prefixed-caller'),
            pytest.param('engineer', f'{PREFIX}code-scout', id='prefixed-target'),
            pytest.param(f'{PREFIX}engineer', f'{PREFIX}code-scout', id='prefixed-both'),
        ],
    )
    def test_a_prefix_changes_nothing_for_an_allowed_dispatch(
        self, caller: str, target: str
    ) -> None:
        assert run_hook(hook_input(caller, target)).decision is None

    @pytest.mark.parametrize(
        ('caller', 'target'),
        [
            pytest.param('engineer', 'web-scout', id='bare-both'),
            pytest.param(f'{PREFIX}engineer', 'web-scout', id='prefixed-caller'),
            pytest.param('engineer', f'{PREFIX}web-scout', id='prefixed-target'),
            pytest.param(f'{PREFIX}engineer', f'{PREFIX}web-scout', id='prefixed-both'),
        ],
    )
    def test_a_prefix_changes_nothing_for_a_denied_dispatch(self, caller: str, target: str) -> None:
        assert run_hook(hook_input(caller, target)).decision == 'deny'

    @pytest.mark.parametrize(
        'caller',
        [
            pytest.param('general-purpose', id='built-in'),
            pytest.param('other-plugin:engineer', id='another-plugins-agent'),
            pytest.param('', id='empty'),
        ],
    )
    def test_an_unknown_caller_gets_no_allowance(self, caller: str) -> None:
        verdict = run_hook(hook_input(caller, 'code-scout'))

        assert verdict.decision == 'deny'
        assert verdict.reason.endswith('it may dispatch: nothing')


class TestMainConversation:
    @pytest.mark.parametrize('target', ['code-scout', 'engineer', 'general-purpose'])
    def test_input_with_no_agent_type_gets_no_decision(self, target: str) -> None:
        assert run_hook(hook_input(None, target)) == Verdict(decision=None, reason='')


class TestUnexpectedInput:
    @pytest.mark.parametrize(
        'text',
        [
            pytest.param('{"agent_type": "engineer"', id='truncated-json-naming-a-caller'),
            pytest.param('{"agent_type": "engineer"}', id='no-tool-input'),
            pytest.param('{"agent_type": "engineer", "tool_input": []}', id='tool-input-a-list'),
            pytest.param(
                '{"agent_type": "engineer", "tool_input": {"subagent_type": 3}}',
                id='target-a-number',
            ),
            pytest.param('{"agent_type": 7, "tool_input": {}}', id='caller-a-number'),
            pytest.param('{"agent_type": null}', id='caller-null'),
        ],
    )
    def test_input_naming_a_caller_is_denied(self, text: str) -> None:
        assert run_hook(text).decision == 'deny'

    @pytest.mark.parametrize(
        'text',
        [
            pytest.param('', id='empty'),
            pytest.param('not json', id='text'),
            pytest.param('{"tool_name": "Agent"', id='truncated-json'),
            pytest.param('[]', id='list'),
            pytest.param('{"tool_name": "Agent"}', id='object-without-a-caller'),
        ],
    )
    def test_input_naming_no_caller_is_allowed(self, text: str) -> None:
        assert run_hook(text) == Verdict(decision=None, reason='')


class TestCommand:
    def test_the_subcommand_prints_the_deny_decision(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr('sys.stdin', io.StringIO(hook_input('engineer', 'architect')))

        assert main(['dispatch-hook']) == 0
        assert json.loads(capsys.readouterr().out)['hookSpecificOutput'] == {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': (
                'engineer may not dispatch architect; it may dispatch: code-scout'
            ),
        }


class TestAgentFiles:
    @pytest.mark.parametrize('worker', Worker)
    def test_the_row_equals_the_one_the_agent_file_states(self, worker: Worker) -> None:
        assert frozenset(DISPATCH_RULES[worker]) == row_stated_by(worker)

    def test_every_worker_has_a_row(self) -> None:
        assert set(DISPATCH_RULES) == set(Worker)
