import re
from pathlib import Path

import pytest
from ai_engineer_cli.cli import main

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / 'skills'
    / 'create-instructions'
    / 'assets'
    / 'instructions.template.md'
)
PLACEHOLDER = re.compile(r'\b[A-Z][A-Z0-9_]{2,}\b')
FILLS = {
    'GLOB_ONE': 'src/**/*.py',
    'FILES_IN_WORDS': 'the Python sources under src',
    'CARVE_OUTS': 'generated code',
    'STRENGTH_WORD': 'Prefer',
    'CONVENTION_ONE': 'early returns over nested conditionals',
    'CONVENTION_TWO': 'named constants over repeated literals',
    'REASON': 'flat code is easier to review',
    'LANG': 'python',
    'BEFORE_SNIPPET': 'if ready:\n    run()',
    'AFTER_SNIPPET': 'if not ready:\n    return\nrun()',
    'GENERIC_ANTI_PATTERN': 'Nesting three conditionals deep',
    'INSTEAD': 'return early',
    'EXISTING_VIOLATION_POLICY': 'leave it unless the change touches those lines',
    'CHECK_COMMAND_OR_QUESTION': 'ask whether any new branch can return early',
    'REVIEWER_CHECK': 'scanning the diff for nested conditionals',
}


def fill(template: str) -> str:
    return PLACEHOLDER.sub(lambda token: FILLS.get(token[0], token[0]), template)


def test_every_template_placeholder_has_a_fill() -> None:
    unfilled = set(PLACEHOLDER.findall(fill(TEMPLATE.read_text())))

    assert unfilled == set()


def test_template_frontmatter_holds_paths_and_no_other_key() -> None:
    frontmatter = TEMPLATE.read_text().split('---\n')[1]

    keys = re.findall(r'^([a-z]+):', frontmatter, re.MULTILINE)

    assert keys == ['paths']


def test_filled_template_passes_strict_validation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rule = tmp_path / '.claude' / 'rules' / 'demo.md'
    rule.parent.mkdir(parents=True)
    rule.write_text(fill(TEMPLATE.read_text()))

    code = main(['instruction', 'validate', str(rule), '--strict'])

    assert code == 0, capsys.readouterr().out
