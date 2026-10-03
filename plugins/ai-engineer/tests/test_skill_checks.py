from pathlib import Path

import pytest
from ai_engineer_cli.create_skill import check_skill
from ai_engineer_cli.findings import CannotCheckError, Finding

DESCRIPTION = 'Summarize a file. Use when the user asks for a summary of a file.'
CLEAN_FRONTMATTER = f'name: demo-skill\ndescription: {DESCRIPTION}\n'
CLEAN_BODY = '# Demo\n\nSummarize the file the user names.\n'


def write_skill(
    root: Path,
    frontmatter: str = CLEAN_FRONTMATTER,
    body: str = CLEAN_BODY,
    directory: str = 'demo-skill',
) -> Path:
    skill_dir = root / directory
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text(f'---\n{frontmatter}---\n{body}', encoding='utf-8')
    return skill_dir


def check(root: Path, extra: str = '', **options: str) -> list[Finding]:
    frontmatter = options.pop('frontmatter', CLEAN_FRONTMATTER)
    return check_skill(write_skill(root, frontmatter + extra, **options))


def messages(findings: list[Finding], level: str) -> list[str]:
    return [finding.message for finding in findings if finding.level == level]


def assert_error(findings: list[Finding], fragment: str) -> None:
    assert any(fragment in message for message in messages(findings, 'error')), findings


def assert_warning(findings: list[Finding], fragment: str) -> None:
    assert any(fragment in message for message in messages(findings, 'warning')), findings


def test_clean_skill_has_no_findings(tmp_path: Path) -> None:
    assert check(tmp_path) == []


def test_vs3_skill_md_missing(tmp_path: Path) -> None:
    skill_dir = tmp_path / 'demo-skill'
    skill_dir.mkdir()

    assert_error(check_skill(skill_dir), 'SKILL.md not found')


def test_vs8_duplicate_frontmatter_key(tmp_path: Path) -> None:
    assert_error(check(tmp_path, 'description: again\n'), "duplicate frontmatter key 'description'")


def test_vs9_non_string_frontmatter_key(tmp_path: Path) -> None:
    assert_error(check(tmp_path, '1: one\n'), 'frontmatter key 1 on line 4 is not a string')


def test_vs13_unknown_frontmatter_field(tmp_path: Path) -> None:
    assert_error(check(tmp_path, 'colour: red\n'), "unknown frontmatter field 'colour'")


def test_cs_a17_a18_c11_known_keys_are_claude_codes(tmp_path: Path) -> None:
    claude_keys = (
        'argument-hint: "[file]"\n'
        'disable-model-invocation: false\n'
        'user-invocable: true\n'
        'when_to_use: Use for files.\n'
        'arguments: file\n'
        'paths: "**/*.md"\n'
        'shell: bash\n'
        'context: fork\n'
        'agent: Explore\n'
        'background: false\n'
        'hooks: {}\n'
        'effort: low\n'
        'model: inherit\n'
        'disallowed-tools: Bash\n'
    )

    assert check(tmp_path, claude_keys) == []


def test_cs_a18_c11_keys_of_other_agent_hosts_are_unknown(tmp_path: Path) -> None:
    findings = check(tmp_path, 'handoffs: []\nmcp-servers: {}\ntarget: vscode\n')

    assert len(messages(findings, 'error')) == 3


def test_cs_a17_flag_keys_raise_nothing_under_any_mode(tmp_path: Path) -> None:
    extra = 'argument-hint: "[file]"\ndisable-model-invocation: true\nuser-invocable: true\n'

    assert check(tmp_path, extra) == []


def test_vs15a_name_missing(tmp_path: Path) -> None:
    findings = check(tmp_path, frontmatter=f'description: {DESCRIPTION}\n')

    assert_warning(findings, 'name is missing')


def test_vs15c_name_empty(tmp_path: Path) -> None:
    findings = check(tmp_path, frontmatter=f'name: ""\ndescription: {DESCRIPTION}\n')

    assert_error(findings, 'name must not be empty')


def test_vs15f_description_empty(tmp_path: Path) -> None:
    assert_error(check(tmp_path, frontmatter='name: demo-skill\ndescription: ""\n'), 'description')


def test_vs16_description_over_1024_chars(tmp_path: Path) -> None:
    long_description = 'x' * 1100
    findings = check(tmp_path, frontmatter=f'name: demo-skill\ndescription: {long_description}\n')

    assert_error(findings, 'description is 1100 chars; the limit is 1024')


def test_cs_a32_listing_text_over_1536_chars(tmp_path: Path) -> None:
    extra = f'when_to_use: {"y" * 1500}\n'

    assert_warning(check(tmp_path, extra), 'Claude Code truncates the skill listing at 1536')


def test_vs17a_license_not_a_string(tmp_path: Path) -> None:
    assert_error(check(tmp_path, 'license: [MIT]\n'), 'license must be a string, got list')


def test_vs17b_license_empty(tmp_path: Path) -> None:
    assert_error(check(tmp_path, 'license: ""\n'), 'license must not be empty')


def test_vs18a_compatibility_not_a_string(tmp_path: Path) -> None:
    assert_error(check(tmp_path, 'compatibility: 3\n'), 'compatibility must be a string, got int')


def test_vs18b_compatibility_empty(tmp_path: Path) -> None:
    assert_error(check(tmp_path, 'compatibility: ""\n'), 'compatibility must not be empty')


def test_vs18c_compatibility_over_500_chars(tmp_path: Path) -> None:
    findings = check(tmp_path, f'compatibility: {"c" * 600}\n')

    assert_error(findings, 'compatibility is 600 chars; the limit is 500')


def test_vs19a_argument_hint_not_a_string(tmp_path: Path) -> None:
    assert_error(check(tmp_path, 'argument-hint: [file]\n'), 'argument-hint must be a string')


def test_vs19b_argument_hint_empty(tmp_path: Path) -> None:
    assert_error(check(tmp_path, 'argument-hint: ""\n'), 'argument-hint must not be empty')


def test_vs20a_name_fails_lowercase_hyphen_pattern(tmp_path: Path) -> None:
    findings = check(
        tmp_path,
        frontmatter=f'name: Demo_Skill\ndescription: {DESCRIPTION}\n',
        directory='Demo_Skill',
    )

    assert_error(findings, "name 'Demo_Skill' must be 1 to 64 chars")


def test_vs20b_name_over_64_chars(tmp_path: Path) -> None:
    name = 'n' * 70
    findings = check(
        tmp_path, frontmatter=f'name: {name}\ndescription: {DESCRIPTION}\n', directory=name
    )

    assert_error(findings, 'must be 1 to 64 chars')


def test_vs21_name_differs_from_directory(tmp_path: Path) -> None:
    findings = check(tmp_path, frontmatter=f'name: other-skill\ndescription: {DESCRIPTION}\n')

    assert_error(findings, "name 'other-skill' must equal the directory name 'demo-skill'")


def test_vs22b_metadata_values_not_strings(tmp_path: Path) -> None:
    assert_error(check(tmp_path, 'metadata:\n  version: 2\n'), "got 'version': 2")


def test_vs23_flags_must_be_booleans(tmp_path: Path) -> None:
    findings = check(tmp_path, 'disable-model-invocation: maybe\nuser-invocable: [x]\n')

    assert len(messages(findings, 'error')) == 2


def test_cs_a21_flags_accept_yes_no_on_off_and_digits(tmp_path: Path) -> None:
    assert check(tmp_path, 'disable-model-invocation: No\nuser-invocable: ON\n') == []
    (tmp_path / 'digits').mkdir()
    assert check(tmp_path / 'digits', 'disable-model-invocation: 0\nuser-invocable: 1\n') == []


def test_vs24_both_flags_restrict(tmp_path: Path) -> None:
    extra = 'argument-hint: "[file]"\ndisable-model-invocation: true\nuser-invocable: false\n'

    assert_error(check(tmp_path, extra), 'neither user-invocable nor model-invocable')


def test_vs25_human_only_skill_without_argument_hint(tmp_path: Path) -> None:
    findings = check(tmp_path, 'disable-model-invocation: true\n')

    assert_warning(findings, 'human-only skill has no argument-hint')


def test_vs26a_allowed_tools_empty_string(tmp_path: Path) -> None:
    assert_error(check(tmp_path, 'allowed-tools: ""\n'), 'must not be an empty string')


def test_vs26b_allowed_tools_empty_list(tmp_path: Path) -> None:
    assert_error(check(tmp_path, 'allowed-tools: []\n'), 'must not be an empty list')


def test_vs26e_allowed_tools_empty_entry(tmp_path: Path) -> None:
    assert_error(check(tmp_path, 'allowed-tools: Read,, Grep\n'), 'contains an empty entry')


def test_vs26f_allowed_tools_bad_token(tmp_path: Path) -> None:
    findings = check(tmp_path, 'allowed-tools: Read Bash(git add *\n')

    assert_error(findings, "entry 'Bash(git add *' is not a Claude Code rule")


def test_vs26g_allowed_tools_star_plus_others(tmp_path: Path) -> None:
    assert_warning(check(tmp_path, 'allowed-tools: "* Read"\n'), "contains '*' plus other entries")


def test_cs_a19_allowed_tools_accept_claude_code_rules(tmp_path: Path) -> None:
    forms = (
        'allowed-tools: Bash(uv *) Read Grep\n',
        'allowed-tools: Bash(git add *), Read, mcp__github__create_issue\n',
        'allowed-tools:\n  - Bash(uv run pytest *)\n  - WebFetch(domain:example.com)\n',
    )
    for index, extra in enumerate(forms):
        root = tmp_path / str(index)
        root.mkdir()

        assert check(root, extra) == [], extra


def test_vs27_empty_body(tmp_path: Path) -> None:
    assert_error(check(tmp_path, body='\n'), 'no Markdown body')


def test_vs28a_body_references_missing_file(tmp_path: Path) -> None:
    findings = check(tmp_path, body='# Demo\n\nRun scripts/missing.py first.\n')

    assert_error(findings, 'body references scripts/missing.py but it does not exist')


def test_vs28b_reference_escapes_with_dotdot(tmp_path: Path) -> None:
    findings = check(tmp_path, body='# Demo\n\nSee [notes](../notes.md).\n')

    assert_error(findings, 'reference escapes the skill directory: ../notes.md')


def test_vs28c_symlink_in_resource_dir_points_outside(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path, body='# Demo\n\nRun scripts/host.\n')
    (skill_dir / 'scripts').mkdir()
    (skill_dir / 'scripts' / 'host').symlink_to('/etc/hostname')

    assert_error(check_skill(skill_dir), 'scripts/host is a symlink outside the skill directory')


def test_vs28d_referenced_file_escapes_through_symlink(tmp_path: Path) -> None:
    outside = tmp_path / 'outside.md'
    outside.write_text('x', encoding='utf-8')
    skill_dir = write_skill(tmp_path, body='# Demo\n\nRead references/outside.md.\n')
    (skill_dir / 'references').mkdir()
    (skill_dir / 'references' / 'outside.md').symlink_to(outside)

    assert_error(check_skill(skill_dir), 'escapes the skill directory through a symlink')


def test_vs28e_empty_resource_directory(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path)
    (skill_dir / 'assets').mkdir()

    assert_warning(check_skill(skill_dir), 'assets/ is empty')


def test_vs28f_resource_file_never_referenced(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path)
    (skill_dir / 'references').mkdir()
    (skill_dir / 'references' / 'extra.md').write_text('x', encoding='utf-8')

    assert_warning(check_skill(skill_dir), 'references/extra.md is never referenced')


def test_vs28_referenced_resources_pass(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path, body='# Demo\n\nRead references/extra.md and scripts/.\n')
    (skill_dir / 'references').mkdir()
    (skill_dir / 'references' / 'extra.md').write_text('x', encoding='utf-8')
    (skill_dir / 'scripts').mkdir()
    (skill_dir / 'scripts' / 'run.py').write_text('x', encoding='utf-8')

    assert check_skill(skill_dir) == []


def test_vs29_skill_md_over_500_lines(tmp_path: Path) -> None:
    findings = check(tmp_path, body='# Demo\n' + 'line\n' * 520)

    assert_warning(findings, 'SKILL.md is 525 lines')


def test_invalid_yaml_the_builtin_passed_cannot_be_checked(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path, 'name: demo-skill\ndescription: [unclosed\n')

    with pytest.raises(CannotCheckError, match='field checks could not run'):
        check_skill(skill_dir)


def test_invalid_yaml_the_builtin_reported_keeps_the_own_checks(tmp_path: Path) -> None:
    skill_dir = write_skill(tmp_path, 'name: demo-skill\ndescription: "unclosed\n')

    assert check_skill(skill_dir, builtin_errored=True) == []


def test_empty_link_target_is_not_a_reference(tmp_path: Path) -> None:
    assert check(tmp_path, body='# Demo\n\nSee [the notes]( ) and [more](<>).\n') == []
