from pathlib import Path

import pytest
from ai_engineer_cli.cli import main
from ai_engineer_cli.findings import Finding
from ai_engineer_cli.subagent import command as create_subagent

SECTIONS = ('role', 'context', 'workflow', 'constraints', 'output_format', 'verification')
DESCRIPTION = 'Reviews code for defects. Use when the user asks for a code review.'
CLEAN_FIELDS: dict[str, str | None] = {
    'name': 'demo-agent',
    'description': DESCRIPTION,
    'tools': 'Read, Grep',
}


def sections(names: tuple[str, ...] = SECTIONS) -> str:
    return ''.join(f'<{name}>\nText.\n</{name}>\n\n' for name in names)


def agent_text(fields: dict[str, str | None] | None = None, body: str | None = None) -> str:
    """An agent file; a field set to None is dropped."""
    merged = {**CLEAN_FIELDS, **(fields or {})}
    lines = [f'{key}: {value}' for key, value in merged.items() if value is not None]
    return '---\n' + '\n'.join(lines) + '\n---\n' + (sections() if body is None else body)


def write_agent(
    root: Path, text: str, *, plugin: bool = False, name: str = 'demo-agent.md'
) -> Path:
    directory = root / 'plugin' / 'agents' if plugin else root / '.claude' / 'agents'
    directory.mkdir(parents=True)
    path = directory / name
    path.write_text(text)
    return path


def run(path: Path, capsys: pytest.CaptureFixture[str], *options: str) -> tuple[int, str]:
    code = main(['create-subagent', 'validate', str(path), *options])
    return code, capsys.readouterr().out


@pytest.fixture
def builtin_findings(monkeypatch: pytest.MonkeyPatch) -> list[Finding]:
    """What the stubbed built-in reports; a test appends to it."""
    findings: list[Finding] = []
    monkeypatch.setattr(create_subagent, 'run_builtin', lambda _target, **_options: findings)
    return findings


def check(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    text: str,
    *,
    plugin: bool = False,
) -> tuple[int, str]:
    return run(write_agent(tmp_path, text, plugin=plugin), capsys)


pytestmark = pytest.mark.usefixtures('builtin_findings')


@pytest.mark.parametrize(
    'text',
    [
        'Notes about agents, no frontmatter.\n',
        '\n' + agent_text(),
        '---\nname: demo-agent\ndescription: Reviews code. Use when asked.\n\n' + sections(),
    ],
    ids=['no-block', 'text-before-the-opening-line', 'block-never-closed'],
)
def test_va_3_la_1_la_2_file_without_a_frontmatter_block_is_an_error_in_claude_agents(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    code, output = check(tmp_path, capsys, text)

    assert code == 1
    assert 'error: no frontmatter block' in output


def test_va_3_la_1_la_2_are_left_to_the_builtin_in_a_plugin_agents_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(tmp_path, capsys, 'Notes, no frontmatter.\n', plugin=True)

    assert code == 0
    assert 'frontmatter block' not in output


@pytest.mark.parametrize('name', [None, '', '[a, b]'])
def test_va_5_la_12_missing_name_is_an_error_in_claude_agents(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str | None
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'name': name}))

    assert code == 1
    assert 'error: name is missing or empty' in output


def test_sa_c11_missing_name_in_a_plugin_agents_directory_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'name': None}), plugin=True)

    assert code == 0
    assert 'warning: name is missing or empty' in output
    assert 'loads under its filename' in output


@pytest.mark.parametrize('name', ['Demo_Agent', 'my:agent', '-lead', 'Demo Agent'])
def test_va_7_la_13_invalid_name_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'name': f'"{name}"'}))

    assert code == 1
    assert 'error: name' in output
    assert 'must be lowercase letters, digits and single hyphens' in output


def test_va_12_la_14_omitted_tools_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'tools': None}))

    assert code == 0
    assert "warning: no 'tools' list, so the agent inherits every tool" in output


@pytest.mark.parametrize('tools', ['Reed, Grep', 'read', 'github/pull_request_read', 'mcp__'])
def test_va_13_unknown_tool_name_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], tools: str
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'tools': f'"{tools}"'}))

    assert code == 1
    assert 'is not a Claude Code tool name' in output


def test_va_15a_closing_tag_with_no_open_section_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = sections(SECTIONS[:2]) + '</workflow>\n' + sections(SECTIONS[2:])

    code, output = check(tmp_path, capsys, agent_text(body=body))

    assert code == 1
    assert 'closes </workflow> but the open section is <none>' in output


def test_va_15b_section_never_closed_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(
        tmp_path, capsys, agent_text(body='<role>\nText.\n\n' + sections(SECTIONS[1:]))
    )

    assert code == 1
    assert 'error: <role> is never closed' in output


def test_va_15c_stray_tag_is_a_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, output = check(tmp_path, capsys, agent_text(body=sections() + '<widget>\nx\n</widget>\n'))

    assert code == 0
    assert 'warning: <widget> is not a section tag' in output


def test_va_15d_missing_required_section_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = sections(SECTIONS[:3] + SECTIONS[4:])

    code, output = check(tmp_path, capsys, agent_text(body=body))

    assert code == 1
    assert 'error: required section <constraints> is missing' in output


def test_va_15e_required_sections_out_of_order_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = sections(('role', 'workflow', 'context', *SECTIONS[3:]))

    code, output = check(tmp_path, capsys, agent_text(body=body))

    assert code == 1
    assert 'error: required sections out of order' in output


def test_va_15f_body_wrapped_in_a_root_element_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = '<agent_prompt>\n' + sections() + '</agent_prompt>\n'

    code, output = check(tmp_path, capsys, agent_text(body=body))

    assert code == 1
    assert 'wrapped in a single root element <agent_prompt>' in output


def test_va_15g_bare_angle_bracket_and_ampersand_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = sections() + 'Use a < b when comparing & counting.\n'

    code, output = check(tmp_path, capsys, agent_text(body=body))

    assert code == 0
    assert 'warning: not strictly parseable' in output


def test_va_15h_doctype_declaration_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(tmp_path, capsys, agent_text(body=sections() + '<!DOCTYPE foo>\n'))

    assert code == 0
    assert 'warning: document and entity declarations are not supported' in output


def test_la_7_sa_c16_description_without_a_trigger_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'description': 'Reviews code carefully'}))

    assert code == 0
    assert 'warning: description states a capability but no trigger condition' in output


@pytest.mark.parametrize(
    'description',
    [
        'Reviews code. Use when: asked for a review',
        'Reviews code. Use when asked, see http://x.y',
    ],
    ids=['yaml-rejects-it', 'yaml-reads-it'],
)
def test_la_8_sa_c16_unquoted_colon_in_the_description_is_a_warning_not_a_failure_to_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], description: str
) -> None:
    text = agent_text({'description': description, 'tools': None})

    code, output = check(tmp_path, capsys, text)

    assert code == 0
    assert "warning: description contains ':' and is not quoted" in output
    assert 'inherits every tool' in output


def test_la_8_a_quoted_description_with_a_colon_is_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(
        tmp_path, capsys, agent_text({'description': '"Reviews code. Use when: asked"'})
    )

    assert code == 0
    assert 'is not quoted' not in output


def test_la_9_empty_body_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, output = check(tmp_path, capsys, agent_text(body='\n'))

    assert code == 1
    assert "error: the body is empty; it is the agent's system prompt" in output
    assert 'required section' not in output


def test_la_11_model_directive_in_the_body_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = sections() + 'MODEL REQUIREMENT: run on opus.\n'

    code, output = check(tmp_path, capsys, agent_text(body=body))

    assert code == 0
    assert 'warning: body contains a model-requirement directive' in output


def test_la_15_sa_b1_sa_c14_tools_with_disallowed_tools_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'disallowedTools': 'Write'}))

    assert code == 0
    assert "warning: 'disallowedTools' is applied first" in output


def test_la_15_sa_b1_sa_c14_disallowed_tools_alone_is_recognised_and_quiet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'tools': None, 'disallowedTools': 'Write'}))

    assert code == 0
    assert 'disallowedTools' not in output


def test_la_16_sa_b3_sa_c13_bash_without_max_turns_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'tools': 'Read, Bash(git status *)'}))

    assert code == 0
    assert 'warning: agent can run commands but sets no maxTurns' in output


def test_la_16_sa_b3_sa_c13_max_turns_silences_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'tools': 'Read, Bash', 'maxTurns': '20'}))

    assert code == 0
    assert 'maxTurns' not in output


def test_sa_c13_command_tool_names_of_another_host_are_not_command_tools(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'tools': 'Read, execute, runCommands'}))

    assert code == 1
    assert "'execute' is not a Claude Code tool name" in output
    assert 'maxTurns' not in output


@pytest.mark.parametrize('model', ['gpt4', 'Sonnet', 'opus[2m]'])
def test_la_17_sa_a10_sa_c15_unknown_model_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], model: str
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'model': model}))

    assert code == 1
    assert f"error: model '{model}' is not a Claude Code alias" in output


@pytest.mark.parametrize(
    'model', ['sonnet', 'opus', 'haiku', 'fable', 'inherit', 'claude-opus-5-5', 'opus[1m]']
)
def test_sa_a10_sa_c15_aliases_inherit_and_full_ids_are_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], model: str
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'model': model}))

    assert code == 0
    assert 'model' not in output


def test_la_18_sa_a14_unknown_key_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'bogus-field': 'x', 'infer': 'false'}))

    assert code == 0
    assert "warning: 'bogus-field' is not a documented frontmatter key" in output
    assert "warning: 'infer' is not a documented frontmatter key" in output


@pytest.mark.parametrize(
    ('key', 'value'),
    [
        ('initialPrompt', 'Start'),
        ('experimental', '{cacheTtl: 1h}'),
        ('omitClaudeMd', 'true'),
        ('skills', '[demo-skill]'),
        ('memory', 'project'),
        ('isolation', 'worktree'),
    ],
)
def test_sa_b11_sa_b12_sa_c2_documented_keys_are_recognised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str, value: str
) -> None:
    code, output = check(tmp_path, capsys, agent_text({key: value}))

    assert code == 0
    assert 'not a documented frontmatter key' not in output


def test_la_19_sa_c12_bypass_permissions_warning_says_the_main_mode_wins(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'permissionMode': 'bypassPermissions'}))

    assert code == 0
    assert "keeps the main conversation's permission mode" in output
    assert '.vscode' not in output


def test_sa_b2_sa_b13_permission_mode_is_quiet_in_claude_agents(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fields: dict[str, str | None] = {
        'permissionMode': 'acceptEdits',
        'hooks': '{}',
        'mcpServers': '[slack]',
        'initialPrompt': 'Go',
    }

    code, output = check(tmp_path, capsys, agent_text(fields))

    assert code == 0
    assert 'ignored' not in output


@pytest.mark.parametrize(
    ('key', 'value'),
    [
        ('permissionMode', 'acceptEdits'),
        ('hooks', '{}'),
        ('mcpServers', '[slack]'),
        ('initialPrompt', 'Go'),
    ],
)
def test_sa_b2_sa_b13_four_keys_warn_in_a_plugin_agents_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str, value: str
) -> None:
    code, output = check(tmp_path, capsys, agent_text({key: value}), plugin=True)

    assert code == 0
    assert f"warning: '{key}' is ignored in a plugin agents/ directory" in output


def test_sa_b2_sa_b13_bypass_permissions_in_a_plugin_gets_only_the_ignored_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = agent_text({'permissionMode': 'bypassPermissions'})

    code, output = check(tmp_path, capsys, text, plugin=True)

    assert code == 0
    assert output.count('warning:') == 1
    assert 'is ignored in a plugin agents/ directory' in output


def test_sa_a1_file_name_need_not_match_the_name_or_carry_a_suffix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_agent(tmp_path, agent_text(), name='another-name.md')

    code, output = run(path, capsys)

    assert code == 0
    assert 'filename' not in output


@pytest.mark.parametrize(
    'tools',
    [
        'Read, Grep, Glob, Edit, Write, WebFetch, WebSearch, TodoWrite',
        'Agent(worker, researcher), Read',
        'Task, Skill',
        'mcp__github, mcp__github__create_issue, mcp__github__*',
        '[Read, Grep]',
    ],
)
def test_sa_a7_sa_a9_claude_code_tool_names_and_mcp_references_are_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], tools: str
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'tools': tools}))

    assert code == 0
    assert 'tool' not in output


@pytest.mark.parametrize('tools', ['[]', '""'])
def test_sa_a8_empty_tools_list_means_no_tools_and_is_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], tools: str
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'tools': tools}))

    assert code == 0
    assert 'PASS demo-agent.md: 0 error(s), 0 warning(s)' in output


def test_sa_a8_list_whose_every_entry_is_misspelled_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = check(tmp_path, capsys, agent_text({'tools': 'Grpe, Raed'}))

    assert code == 1
    assert output.count('is not a Claude Code tool name') == 2


def test_la_10_sa_c17_body_in_the_reference_template_shape_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        '<role>\nYou are demo-agent, a code reviewer. You return a review.\n</role>\n\n'
        '<context>\nThe repository holds Python.\n</context>\n\n'
        '<workflow>\n1. Read the diff.\n2. Check each change.\n</workflow>\n\n'
        '<constraints>\n- Never edit files, because you only review.\n</constraints>\n\n'
        '<output_format>\nReturn exactly:\n\n## Summary\n\n## Findings\n</output_format>\n\n'
        '<verification>\nRe-read each cited line.\n</verification>\n'
    )

    code, output = check(tmp_path, capsys, agent_text(body=body))

    assert code == 0
    assert 'PASS demo-agent.md: 0 error(s), 0 warning(s)' in output
    assert 'inputs_expected' not in output
    assert 'output_contract' not in output
