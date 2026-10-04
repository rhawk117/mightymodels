import re
from pathlib import Path

import pytest
import yaml
from vibe_code_cli.frontmatter import parse_skill_text

EVALS = Path(__file__).resolve().parents[1] / 'evals'

PROMPT_KEYS = {
    'schema_version',
    'name',
    'description',
    'tags',
    'plugins',
    'runs',
    'expected_outcome',
    'model',
    'max_turns',
    'timeout_seconds',
    'allowed_tools',
    'append_system_prompt',
    'env',
}
CASE_YAML_KEYS = {
    'schema_version',
    'name',
    'description',
    'tags',
    'plugins',
    'runs',
    'expected_outcome',
    'execution',
    'context',
    'graders',
}
EXECUTION_KEYS = {
    'model',
    'max_turns',
    'timeout_seconds',
    'allowed_tools',
    'append_system_prompt',
    'env',
    'prompt',
}
CONTEXT_KEYS = {'scaffold_script', 'history_file', 'add_dirs'}
COMMON_GRADER_KEYS = {'type', 'weight', 'arm'}
GRADER_OPTIONS = {
    'regex': {'pattern', 'flags', 'match', 'target'},
    'tool_used': {'tool', 'input_match', 'min', 'max'},
    'tool_order': {'before', 'after'},
    'file_exists': {'path', 'exists'},
    'llm': {'criteria', 'focus'},
    'baseline': {'baseline_file', 'criteria'},
}
REQUIRED_OPTIONS = {
    'regex': {'pattern'},
    'tool_used': {'tool'},
    'tool_order': {'before', 'after'},
    'file_exists': {'path'},
    'llm': set(),
    'baseline': {'baseline_file'},
}
STRING_TARGETS = {'last_message', 'trace', 'files', 'mock_calls'}
REGEX_FLAGS = set('dgimsuvy')
FORBIDDEN_WORDS = re.compile(r'agentStop|deniedTools|com\.github|worker', re.IGNORECASE)
SKILL_PREFIXES = ('create-mcp-', 'plan-plugin-')


def case_dirs(marker: str | None = None) -> list[Path]:
    markers = (marker,) if marker else ('prompt.md', 'case.yaml')
    return sorted({path.parent for name in markers for path in EVALS.glob(f'*/{name}')})


def grader_files(grader_type: str | None = None) -> list[Path]:
    paths = sorted(EVALS.glob('*/graders/*.md'))
    if grader_type is None:
        return paths
    return [path for path in paths if frontmatter_of(path)['type'] == grader_type]


def grader_id(path: Path) -> str:
    return f'{path.parent.parent.name}/{path.stem}'


def eval_files() -> list[Path]:
    return sorted(path for path in EVALS.rglob('*') if path.is_file())


def frontmatter_of(path: Path) -> dict[str, object]:
    parsed = parse_skill_text(path.read_text(encoding='utf-8'))
    assert parsed.yaml_problem is None, f'{path}: {parsed.yaml_problem}'
    assert parsed.key_problems == [], f'{path}: {parsed.key_problems}'
    assert parsed.fields is not None, f'{path}: no frontmatter'
    return parsed.fields


def mapping_keys(value: object) -> set[str]:
    assert isinstance(value, dict)
    return {str(key) for key in value}


def test_each_reference_case_has_one_case_directory() -> None:
    names = [path.name for path in case_dirs()]

    assert len(names) == 6
    for prefix in SKILL_PREFIXES:
        assert sum(name.startswith(prefix) for name in names) == 3, names


@pytest.mark.parametrize('case', case_dirs(), ids=lambda path: path.name)
def test_case_has_a_prompt_and_a_grader(case: Path) -> None:
    prompt = case / 'prompt.md'

    assert prompt.is_file()
    assert parse_skill_text(prompt.read_text(encoding='utf-8')).body.strip()
    assert list((case / 'graders').glob('*.md'))


@pytest.mark.parametrize('case', case_dirs(), ids=lambda path: path.name)
def test_prompt_frontmatter_keys_are_documented(case: Path) -> None:
    unknown = mapping_keys(frontmatter_of(case / 'prompt.md')) - PROMPT_KEYS

    assert not unknown


@pytest.mark.parametrize('case', case_dirs('case.yaml'), ids=lambda path: path.name)
def test_case_yaml_keys_are_documented_and_files_exist(case: Path) -> None:
    fields = yaml.safe_load((case / 'case.yaml').read_text(encoding='utf-8'))

    assert mapping_keys(fields) <= CASE_YAML_KEYS
    assert fields['schema_version'] == '1.1'
    assert fields['name'] == case.name
    context = fields.get('context', {})
    assert mapping_keys(context) <= CONTEXT_KEYS
    assert mapping_keys(fields.get('execution', {})) <= EXECUTION_KEYS
    if 'scaffold_script' in context:
        assert (case / context['scaffold_script']).is_file()
    for directory in context.get('add_dirs', []):
        assert (case / directory).is_dir()


@pytest.mark.parametrize('grader', grader_files(), ids=grader_id)
def test_grader_uses_documented_keys_and_type(grader: Path) -> None:
    fields = frontmatter_of(grader)
    grader_type = fields['type']

    assert isinstance(grader_type, str)
    assert grader_type in GRADER_OPTIONS
    keys = mapping_keys(fields)
    assert keys - COMMON_GRADER_KEYS <= GRADER_OPTIONS[grader_type]
    assert REQUIRED_OPTIONS[grader_type] <= keys


@pytest.mark.parametrize('grader', grader_files('regex'), ids=grader_id)
def test_regex_grader_pattern_compiles_and_target_is_valid(grader: Path) -> None:
    fields = frontmatter_of(grader)
    pattern = fields['pattern']
    flags = fields.get('flags', '')

    assert isinstance(pattern, str)
    re.compile(pattern)
    assert '(?i)' not in pattern
    assert isinstance(flags, str)
    assert set(flags) <= REGEX_FLAGS
    target = fields.get('target', 'last_message')
    if isinstance(target, dict):
        assert target.get('source') == 'file'
        assert isinstance(target.get('path'), str)
    else:
        assert target in STRING_TARGETS


@pytest.mark.parametrize('grader', grader_files('llm'), ids=grader_id)
def test_llm_grader_has_a_rubric(grader: Path) -> None:
    fields = frontmatter_of(grader)
    body = parse_skill_text(grader.read_text(encoding='utf-8')).body

    assert body.strip() or fields.get('criteria')
    assert 'focus' in fields


@pytest.mark.parametrize('case', case_dirs(), ids=lambda path: path.name)
def test_case_checks_what_was_produced_and_not_only_the_skill_call(case: Path) -> None:
    graders = [frontmatter_of(path) for path in (case / 'graders').glob('*.md')]
    inspects_output = [
        grader
        for grader in graders
        if grader['type'] == 'file_exists'
        or (grader['type'] == 'regex' and 'target' in grader)
        or (grader['type'] == 'llm' and 'focus' in grader)
    ]

    assert inspects_output


@pytest.mark.parametrize('path', eval_files(), ids=lambda path: str(path.relative_to(EVALS)))
def test_eval_files_name_claude_code_and_hold_no_plaintext_url(path: Path) -> None:
    text = path.read_text(encoding='utf-8')

    assert not FORBIDDEN_WORDS.search(text)
    assert 'http://' not in text
