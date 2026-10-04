from pathlib import Path

import pytest
from vibe_code_cli.cli import main

SECTIONS = ('scope', 'conventions', 'examples', 'anti_patterns', 'verification')
PATH_FRONTMATTER = '---\npaths:\n  - "src/**/*.py"\n---\n'
CLEAN_COUNTS = '0 error(s), 0 warning(s)'


def sections(names: tuple[str, ...] = SECTIONS) -> str:
    return ''.join(f'<{name}>\nText.\n</{name}>\n\n' for name in names)


def rule_text(frontmatter: str = PATH_FRONTMATTER, body: str | None = None) -> str:
    return frontmatter + (sections() if body is None else body)


def paths_frontmatter(*patterns: str) -> str:
    return '---\npaths:\n' + ''.join(f"  - '{pattern}'\n" for pattern in patterns) + '---\n'


def check(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    text: str,
    *options: str,
) -> tuple[int, str]:
    rule = tmp_path / '.claude' / 'rules' / 'x.md'
    rule.parent.mkdir(parents=True, exist_ok=True)
    rule.write_text(text)
    code = main(['instruction', 'validate', str(rule), *options])
    return code, capsys.readouterr().out


def test_group_without_a_command_prints_usage_and_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(['instruction']) == 2
    assert 'usage: vibe-code' in capsys.readouterr().err


def test_validate_help_shows_the_path_and_strict(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(['instruction', 'validate', '--help'])

    out = capsys.readouterr().out
    assert exit_info.value.code == 0
    assert 'PATH' in out
    assert '--strict' in out


def test_passing_rule_with_a_paths_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = check(tmp_path, capsys, rule_text())

    assert code == 0
    assert out == f'PASS x.md: {CLEAN_COUNTS}\n'


def test_failing_rule_exits_one_with_a_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(tmp_path, capsys, rule_text(body='# Just a heading\n'))

    assert code == 1
    assert out.splitlines()[-1].startswith('FAIL x.md: 5 error(s)')


def test_ca7_rule_without_frontmatter_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(tmp_path, capsys, rule_text(frontmatter=''))

    assert code == 0
    assert CLEAN_COUNTS in out


def test_ca7_rule_without_paths_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = check(tmp_path, capsys, rule_text('---\nnote: hi\n---\n'))

    assert code == 0
    assert CLEAN_COUNTS in out


def test_ca6_paths_yaml_list_draws_no_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(tmp_path, capsys, rule_text(paths_frontmatter('src/**/*.ts', 'lib/**/*.ts')))

    assert code == 0
    assert out == f'PASS x.md: {CLEAN_COUNTS}\n'


def test_paths_comma_separated_string_is_split_outside_braces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    frontmatter = '---\npaths: "src/**/*.{ts,tsx}, lib/**/*.ts"\n---\n'

    code, out = check(tmp_path, capsys, rule_text(frontmatter))

    assert code == 0
    assert CLEAN_COUNTS in out


def test_ca9_unknown_frontmatter_keys_draw_no_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    frontmatter = '---\napplyTo: "**/*.py"\ndescription: x\nexcludeAgent: code-review\n---\n'

    code, out = check(tmp_path, capsys, rule_text(frontmatter))

    assert code == 0
    assert out == f'PASS x.md: {CLEAN_COUNTS}\n'


def test_ca1_a_plain_md_name_needs_no_instructions_suffix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _ = check(tmp_path, capsys, rule_text())

    assert code == 0


def test_i2_missing_path_exits_two_without_a_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(['instruction', 'validate', str(tmp_path / 'absent.md')])

    captured = capsys.readouterr()
    assert code == 2
    assert captured.err.startswith('error: ')
    assert captured.out == ''


def test_i2_unreadable_file_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rule = tmp_path / 'x.md'
    rule.write_bytes(b'\xff\xfe\x00bad')

    code = main(['instruction', 'validate', str(rule)])

    captured = capsys.readouterr()
    assert code == 2
    assert 'could not read' in captured.err
    assert captured.out == ''


def test_i4_frontmatter_line_that_is_not_a_key_value_pair(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(
        tmp_path, capsys, rule_text('---\npaths: "src/**"\nthis is not a pair\n---\n')
    )

    assert code == 1
    assert 'error: frontmatter is not valid YAML' in out


def test_i8_empty_paths_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = check(tmp_path, capsys, rule_text('---\npaths:\n---\n'))

    assert code == 1
    assert 'error: paths is empty' in out


@pytest.mark.parametrize('pattern', ['**', '**/*'])
def test_i9_always_on_glob_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], pattern: str
) -> None:
    code, out = check(tmp_path, capsys, rule_text(paths_frontmatter(pattern)))

    assert code == 0
    assert f"warning: paths '{pattern}' matches every file" in out


def test_i10_root_only_glob_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(tmp_path, capsys, rule_text(paths_frontmatter('*.py')))

    assert code == 0
    assert "warning: paths '*.py' matches only the project root" in out


def test_i11_leading_slash_is_a_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = check(tmp_path, capsys, rule_text(paths_frontmatter('/src/**')))

    assert code == 0
    assert "warning: paths '/src/**' starts with '/'" in out


def test_i14_section_closed_out_of_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = sections().replace('</scope>', '</conventions>', 1)

    code, out = check(tmp_path, capsys, rule_text(body=body))

    assert code == 1
    assert 'error: line 3 closes </conventions> but the open section is <scope>' in out


def test_i14_section_never_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = check(tmp_path, capsys, rule_text(body=sections() + '<rationale>\nWhy.\n'))

    assert code == 1
    assert 'error: <rationale> is never closed' in out


def test_i15_non_vocabulary_tag_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(tmp_path, capsys, rule_text(body=sections() + 'Use <name> here.\n'))

    assert code == 0
    assert 'warning: <name> is not a section tag' in out


def test_i16_missing_required_section(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    body = sections(('scope', 'conventions', 'examples', 'verification'))

    code, out = check(tmp_path, capsys, rule_text(body=body))

    assert code == 1
    assert 'error: required section <anti_patterns> is missing' in out


def test_i16_required_sections_out_of_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = sections(('conventions', 'scope', 'examples', 'anti_patterns', 'verification'))

    code, out = check(tmp_path, capsys, rule_text(body=body))

    assert code == 1
    assert 'error: required sections out of order' in out


def test_i16_rationale_is_optional(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    body = sections(('scope', 'rationale', *SECTIONS[1:]))

    code, _ = check(tmp_path, capsys, rule_text(body=body))

    assert code == 0


def test_i17_body_wrapped_in_a_root_element(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(tmp_path, capsys, rule_text(body=f'<rule>\n{sections()}</rule>\n'))

    assert code == 1
    assert 'error: body is wrapped in a single root element <rule>' in out


def test_i18_body_over_200_lines_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(tmp_path, capsys, rule_text(body=sections() + 'filler\n' * 200))

    assert code == 0
    assert 'lines; this loads whenever the rule applies' in out


def test_i19_more_than_one_emphasis_marker_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(tmp_path, capsys, rule_text(body=sections() + 'ALWAYS do it. NEVER skip.\n'))

    assert code == 0
    assert 'warning: 2 emphasis markers' in out


def test_i20_body_that_is_not_strictly_parseable_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(tmp_path, capsys, rule_text(body=sections() + 'Use a < b here.\n'))

    assert code == 0
    assert 'warning: not strictly parseable' in out


def test_i20_a_bare_ampersand_is_parseable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(tmp_path, capsys, rule_text(body=sections() + 'Tom & Jerry.\n'))

    assert code == 0
    assert 'not strictly parseable' not in out


def test_strict_turns_a_warning_into_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(tmp_path, capsys, rule_text(paths_frontmatter('*.py')), '--strict')

    assert code == 1
    assert out.splitlines()[-1].startswith('FAIL ')


def test_cib1_brace_expansion_over_the_budget_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pattern = '{a,b,c,d,e}/{a,b,c,d,e}/{a,b,c,d,e}/{a,b,c,d,e}/{a,b,c,d,e}/*.{ts,tsx}'

    code, out = check(tmp_path, capsys, rule_text(paths_frontmatter(pattern)))

    assert code == 1
    assert 'error: paths expands to 6250 patterns, over the budget of 1000' in out


def test_cib1_the_budget_is_shared_by_the_whole_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pattern = '{a,b,c,d,e}/{a,b,c,d,e}/{a,b,c,d,e}/{a,b,c,d,e}/*.ts'

    code, out = check(tmp_path, capsys, rule_text(paths_frontmatter(pattern, pattern)))

    assert code == 1
    assert 'expands to 1250 patterns' in out


def test_cib1_braces_within_budget_pass_and_plain_patterns_do_not_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    frontmatter = paths_frontmatter('{a,b}/{c,d}/*.{ts,tsx}', 'lib/**/*.ts')

    code, out = check(tmp_path, capsys, rule_text(frontmatter))

    assert code == 0
    assert 'expands' not in out


def test_cib1_nested_braces_are_counted(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pattern = '{a,{b,c}}/{d,e}/{f,g}/{h,i}/{j,k}/{l,m}/{n,o}/{p,q}/{r,s}/{t,u}/{v,w}'

    code, out = check(tmp_path, capsys, rule_text(paths_frontmatter(pattern)))

    assert code == 1
    assert 'expands to 3072 patterns' in out


def test_cib2_unescaped_bracket_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(tmp_path, capsys, rule_text(paths_frontmatter('photos [2024/**')))

    assert code == 0
    assert "warning: paths 'photos [2024/**' has a '['" in out


@pytest.mark.parametrize('pattern', ['src/[abc]/**/*.py', 'src/[!a]/**/*.py', 'photos \\[2024/**'])
def test_cib2_valid_or_escaped_brackets_draw_no_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], pattern: str
) -> None:
    code, out = check(tmp_path, capsys, rule_text(paths_frontmatter(pattern)))

    assert code == 0
    assert out == f'PASS x.md: {CLEAN_COUNTS}\n'
