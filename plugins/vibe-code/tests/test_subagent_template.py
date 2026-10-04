import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

import pytest
from vibe_code_cli.builtin import Services
from vibe_code_cli.cli import main
from vibe_code_cli.findings import Finding

type ServicesFactory = Callable[[Sequence[Finding]], Services]
type TemplateFill = Callable[[str, Mapping[str, str], re.Pattern[str]], str]

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / 'skills'
    / 'create-subagent'
    / 'assets'
    / 'agent.template.md'
)
PLACEHOLDER = re.compile(r'\b[A-Z][A-Z0-9_]{2,}\b')


class TestAgentTemplate:
    NOT_PLACEHOLDERS = frozenset({'CLAUDE'})
    FILLS = MappingProxyType(
        {
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
    )

    @pytest.fixture
    def template_without_comments(self) -> str:
        lines = TEMPLATE.read_text().splitlines()
        return '\n'.join(line for line in lines if not line.startswith('#'))

    @pytest.fixture
    def filled_template(self, fill: TemplateFill) -> str:
        return fill(TEMPLATE.read_text(), self.FILLS, PLACEHOLDER)

    def test_every_template_placeholder_has_a_fill(
        self, template_without_comments: str, fill: TemplateFill
    ) -> None:
        filled = fill(template_without_comments, self.FILLS, PLACEHOLDER)

        unfilled = set(PLACEHOLDER.findall(filled)) - self.NOT_PLACEHOLDERS

        assert unfilled == set()

    @pytest.mark.parametrize(
        'directory',
        [
            pytest.param('.claude/agents', id='.claude/agents'),
            pytest.param('plugin/agents', id='plugin/agents'),
        ],
    )
    def test_filled_template_passes_strict_validation(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        fake_services: ServicesFactory,
        filled_template: str,
        directory: str,
    ) -> None:
        agent = tmp_path / directory / 'demo.md'
        agent.parent.mkdir(parents=True)
        agent.write_text(filled_template)

        code = main(['subagent', 'validate', str(agent), '--strict'], fake_services(()))

        assert code == 0, capsys.readouterr().out
