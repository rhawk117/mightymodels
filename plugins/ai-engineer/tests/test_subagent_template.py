import re
from pathlib import Path

import pytest
from ai_engineer_cli.cli import main
from ai_engineer_cli.findings import Finding
from ai_engineer_cli.subagent import command as create_subagent

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / 'skills'
    / 'create-subagent'
    / 'assets'
    / 'agent.template.md'
)
PLACEHOLDER = re.compile(r'\b[A-Z][A-Z0-9_]{2,}\b')
NOT_PLACEHOLDERS = {'CLAUDE'}
FILLS = {
    'NAME': 'demo',
    'WHAT_IT_DOES': 'Reviews demo files for defects',
    'TRIGGER': 'the user asks for a demo review',
    'MODEL': 'sonnet',
    'ONE_LINE_IDENTITY': 'careful reviewer',
    'JOB': 'review the files the caller names',
    'RESULT_SHAPE': 'a short findings list',
    'REPO_OR_PLUGIN_FACTS_FROM_STAGE_2': 'The repository is a Python project.',
    'WHAT_THE_DISPATCH_SUPPLIES': 'The dispatch names the files to review',
    'STEP': 'Read the named files',
    'NEVER_DO_1': 'Never edit a file',
    'REASON': 'the caller reviews alone',
    'TOOL_RESTRICTION_IN_PROSE': 'Use only the read tools',
    'SELF_CHECK': 're-read each cited line',
    'CALLER_CHECK': 'opening the cited lines',
}


def fill(template: str) -> str:
    return PLACEHOLDER.sub(lambda token: FILLS.get(token[0], token[0]), template)


def test_every_template_placeholder_has_a_fill() -> None:
    body = '\n'.join(line for line in TEMPLATE.read_text().splitlines() if not line.startswith('#'))

    unfilled = set(PLACEHOLDER.findall(fill(body))) - NOT_PLACEHOLDERS

    assert unfilled == set()


@pytest.mark.parametrize('directory', ['.claude/agents', 'plugin/agents'])
def test_filled_template_passes_strict_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    directory: str,
) -> None:
    def no_findings(_target: Path, **_options: bool) -> list[Finding]:
        return []

    monkeypatch.setattr(create_subagent, 'run_builtin', no_findings)
    agent = tmp_path / directory / 'demo.md'
    agent.parent.mkdir(parents=True)
    agent.write_text(fill(TEMPLATE.read_text()))

    code = main(['create-subagent', 'validate', str(agent), '--strict'])

    assert code == 0, capsys.readouterr().out
