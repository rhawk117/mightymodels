from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from vibe_code_cli.cli import main
from vibe_code_cli.instruction.tests.support import (
    CLEAN_COUNTS,
    SECTIONS,
    RuleCheck,
    paths_frontmatter,
)

type SectionWriter = Callable[[Sequence[str]], str]


class TestUsage:
    def test_group_without_a_command_prints_usage_and_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['instruction']) == 2
        assert 'usage: vibe-code' in capsys.readouterr().err

    def test_validate_help_shows_the_path_and_strict(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['instruction', 'validate', '--help'])

        out = capsys.readouterr().out
        assert exit_info.value.code == 0
        assert 'PATH' in out
        assert '--strict' in out


class TestRuleVerdict:
    NO_SECTIONS = '# Just a heading\n'
    ONE_WARNING = paths_frontmatter('*.py')

    def test_passing_rule_with_a_paths_list(self, instruction_rule: RuleCheck) -> None:
        code, out = instruction_rule.check()

        assert code == 0
        assert out == f'PASS x.md: {CLEAN_COUNTS}\n'

    def test_failing_rule_exits_one_with_a_verdict(self, instruction_rule: RuleCheck) -> None:
        code, out = instruction_rule.check(body=self.NO_SECTIONS)

        assert code == 1
        assert out.splitlines()[-1].startswith('FAIL x.md: 5 error(s)')

    def test_strict_turns_a_warning_into_exit_one(self, instruction_rule: RuleCheck) -> None:
        code, out = instruction_rule.check(self.ONE_WARNING, options=('--strict',))

        assert code == 1
        assert out.splitlines()[-1].startswith('FAIL ')

    def test_ca1_a_plain_md_name_needs_no_instructions_suffix(
        self, instruction_rule: RuleCheck
    ) -> None:
        code, _ = instruction_rule.check()

        assert code == 0


class TestFrontmatter:
    NO_FRONTMATTER = ''
    NO_PATHS = '---\nnote: hi\n---\n'
    TWO_PATHS = paths_frontmatter('src/**/*.ts', 'lib/**/*.ts')
    COMMA_SEPARATED = '---\npaths: "src/**/*.{ts,tsx}, lib/**/*.ts"\n---\n'
    OTHER_HOSTS_KEYS = '---\napplyTo: "**/*.py"\ndescription: x\nexcludeAgent: code-review\n---\n'
    NOT_A_PAIR = '---\npaths: "src/**"\nthis is not a pair\n---\n'
    EMPTY_PATHS = '---\npaths:\n---\n'

    def test_ca7_rule_without_frontmatter_passes(self, instruction_rule: RuleCheck) -> None:
        code, out = instruction_rule.check(self.NO_FRONTMATTER)

        assert code == 0
        assert CLEAN_COUNTS in out

    def test_ca7_rule_without_paths_passes(self, instruction_rule: RuleCheck) -> None:
        code, out = instruction_rule.check(self.NO_PATHS)

        assert code == 0
        assert CLEAN_COUNTS in out

    def test_ca6_paths_yaml_list_draws_no_warning(self, instruction_rule: RuleCheck) -> None:
        code, out = instruction_rule.check(self.TWO_PATHS)

        assert code == 0
        assert out == f'PASS x.md: {CLEAN_COUNTS}\n'

    def test_paths_comma_separated_string_is_split_outside_braces(
        self, instruction_rule: RuleCheck
    ) -> None:
        code, out = instruction_rule.check(self.COMMA_SEPARATED)

        assert code == 0
        assert CLEAN_COUNTS in out

    def test_ca9_unknown_frontmatter_keys_draw_no_finding(
        self, instruction_rule: RuleCheck
    ) -> None:
        code, out = instruction_rule.check(self.OTHER_HOSTS_KEYS)

        assert code == 0
        assert out == f'PASS x.md: {CLEAN_COUNTS}\n'

    def test_i4_frontmatter_line_that_is_not_a_key_value_pair(
        self, instruction_rule: RuleCheck
    ) -> None:
        code, out = instruction_rule.check(self.NOT_A_PAIR)

        assert code == 1
        assert 'error: frontmatter is not valid YAML' in out

    def test_i8_empty_paths_is_an_error(self, instruction_rule: RuleCheck) -> None:
        code, out = instruction_rule.check(self.EMPTY_PATHS)

        assert code == 1
        assert 'error: paths is empty' in out

    @pytest.mark.parametrize(
        'frontmatter',
        [
            pytest.param('---\npaths: 2024-01-01\n---\n', id='unquoted_date'),
            pytest.param('---\npaths: on\n---\n', id='bool_alias'),
            pytest.param('---\n1: one\n---\n', id='non_string_key'),
        ],
    )
    def test_a_yaml_typed_frontmatter_value_or_key_is_one_finding(
        self,
        instruction_rule: RuleCheck,
        capsys: pytest.CaptureFixture[str],
        frontmatter: str,
    ) -> None:
        code, out = instruction_rule.check(frontmatter)

        assert code == 1
        assert 'Traceback' not in capsys.readouterr().err
        assert 'FAIL x.md: 1 error(s), 0 warning(s)' in out


class TestUnusableInput:
    UNDECODABLE = b'\xff\xfe\x00bad'

    @pytest.fixture
    def unreadable_rule(self, tmp_path: Path) -> Path:
        rule = tmp_path / 'x.md'
        rule.write_bytes(self.UNDECODABLE)
        return rule

    def test_i2_missing_path_exits_two_without_a_verdict(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(['instruction', 'validate', str(tmp_path / 'absent.md')])

        captured = capsys.readouterr()
        assert code == 2
        assert captured.err.startswith('error: ')
        assert captured.out == ''

    def test_i2_unreadable_file_exits_two(
        self, unreadable_rule: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(['instruction', 'validate', str(unreadable_rule)])

        captured = capsys.readouterr()
        assert code == 2
        assert 'could not read' in captured.err
        assert captured.out == ''


class TestGlobPaths:
    ROOT_ONLY = paths_frontmatter('*.py')
    LEADING_SLASH = paths_frontmatter('/src/**')
    UNESCAPED_BRACKET = paths_frontmatter('photos [2024/**')

    @pytest.mark.parametrize(
        'pattern', [pytest.param('**', id='**'), pytest.param('**/*', id='**/*')]
    )
    def test_i9_always_on_glob_is_a_warning(
        self, instruction_rule: RuleCheck, pattern: str
    ) -> None:
        code, out = instruction_rule.check(paths_frontmatter(pattern))

        assert code == 0
        assert f"warning: paths '{pattern}' matches every file" in out

    def test_i10_root_only_glob_is_a_warning(self, instruction_rule: RuleCheck) -> None:
        code, out = instruction_rule.check(self.ROOT_ONLY)

        assert code == 0
        assert "warning: paths '*.py' matches only the project root" in out

    def test_i11_leading_slash_is_a_warning(self, instruction_rule: RuleCheck) -> None:
        code, out = instruction_rule.check(self.LEADING_SLASH)

        assert code == 0
        assert "warning: paths '/src/**' starts with '/'" in out

    def test_cib2_unescaped_bracket_is_a_warning(self, instruction_rule: RuleCheck) -> None:
        code, out = instruction_rule.check(self.UNESCAPED_BRACKET)

        assert code == 0
        assert "warning: paths 'photos [2024/**' has a '['" in out

    @pytest.mark.parametrize(
        'pattern',
        [
            pytest.param('src/[abc]/**/*.py', id='src/[abc]/**/*.py'),
            pytest.param('src/[!a]/**/*.py', id='src/[!a]/**/*.py'),
            pytest.param('photos \\[2024/**', id='photos \\[2024/**'),
        ],
    )
    def test_cib2_valid_or_escaped_brackets_draw_no_warning(
        self, instruction_rule: RuleCheck, pattern: str
    ) -> None:
        code, out = instruction_rule.check(paths_frontmatter(pattern))

        assert code == 0
        assert out == f'PASS x.md: {CLEAN_COUNTS}\n'


class TestBraceBudget:
    OVER_BUDGET = '{a,b,c,d,e}/{a,b,c,d,e}/{a,b,c,d,e}/{a,b,c,d,e}/{a,b,c,d,e}/*.{ts,tsx}'
    SHARED = '{a,b,c,d,e}/{a,b,c,d,e}/{a,b,c,d,e}/{a,b,c,d,e}/*.ts'
    WITHIN_BUDGET = paths_frontmatter('{a,b}/{c,d}/*.{ts,tsx}', 'lib/**/*.ts')
    NESTED = '{a,{b,c}}/{d,e}/{f,g}/{h,i}/{j,k}/{l,m}/{n,o}/{p,q}/{r,s}/{t,u}/{v,w}'

    def test_cib1_brace_expansion_over_the_budget_is_an_error(
        self, instruction_rule: RuleCheck
    ) -> None:
        code, out = instruction_rule.check(paths_frontmatter(self.OVER_BUDGET))

        assert code == 1
        assert 'error: paths expands to 6250 patterns, over the budget of 1000' in out

    def test_cib1_the_budget_is_shared_by_the_whole_list(self, instruction_rule: RuleCheck) -> None:
        code, out = instruction_rule.check(paths_frontmatter(self.SHARED, self.SHARED))

        assert code == 1
        assert 'expands to 1250 patterns' in out

    def test_cib1_braces_within_budget_pass_and_plain_patterns_do_not_count(
        self, instruction_rule: RuleCheck
    ) -> None:
        code, out = instruction_rule.check(self.WITHIN_BUDGET)

        assert code == 0
        assert 'expands' not in out

    def test_cib1_nested_braces_are_counted(self, instruction_rule: RuleCheck) -> None:
        code, out = instruction_rule.check(paths_frontmatter(self.NESTED))

        assert code == 1
        assert 'expands to 3072 patterns' in out


class TestSectionStructure:
    REQUIRED_OUT_OF_ORDER = ('conventions', 'scope', 'examples', 'anti_patterns', 'verification')
    WITHOUT_ANTI_PATTERNS = ('scope', 'conventions', 'examples', 'verification')
    NEVER_CLOSED = '<rationale>\nWhy.\n'
    NON_VOCABULARY_TAG = 'Use <name> here.\n'

    def test_i14_section_closed_out_of_order(
        self, instruction_rule: RuleCheck, sections: SectionWriter
    ) -> None:
        body = sections(SECTIONS).replace('</scope>', '</conventions>', 1)

        code, out = instruction_rule.check(body=body)

        assert code == 1
        assert 'error: line 3 closes </conventions> but the open section is <scope>' in out

    def test_i14_section_never_closed(
        self, instruction_rule: RuleCheck, sections: SectionWriter
    ) -> None:
        code, out = instruction_rule.check(body=sections(SECTIONS) + self.NEVER_CLOSED)

        assert code == 1
        assert 'error: <rationale> is never closed' in out

    def test_i15_non_vocabulary_tag_is_a_warning(
        self, instruction_rule: RuleCheck, sections: SectionWriter
    ) -> None:
        code, out = instruction_rule.check(body=sections(SECTIONS) + self.NON_VOCABULARY_TAG)

        assert code == 0
        assert 'warning: <name> is not a section tag' in out

    def test_i16_missing_required_section(
        self, instruction_rule: RuleCheck, sections: SectionWriter
    ) -> None:
        code, out = instruction_rule.check(body=sections(self.WITHOUT_ANTI_PATTERNS))

        assert code == 1
        assert 'error: required section <anti_patterns> is missing' in out

    def test_i16_required_sections_out_of_order(
        self, instruction_rule: RuleCheck, sections: SectionWriter
    ) -> None:
        code, out = instruction_rule.check(body=sections(self.REQUIRED_OUT_OF_ORDER))

        assert code == 1
        assert 'error: required sections out of order' in out

    def test_i16_rationale_is_optional(
        self, instruction_rule: RuleCheck, sections: SectionWriter
    ) -> None:
        code, _ = instruction_rule.check(body=sections(('scope', 'rationale', *SECTIONS[1:])))

        assert code == 0

    def test_i17_body_wrapped_in_a_root_element(
        self, instruction_rule: RuleCheck, sections: SectionWriter
    ) -> None:
        code, out = instruction_rule.check(body=f'<rule>\n{sections(SECTIONS)}</rule>\n')

        assert code == 1
        assert 'error: body is wrapped in a single root element <rule>' in out


class TestBodyWarnings:
    FILLER = 'filler\n' * 200
    EMPHASIS = 'ALWAYS do it. NEVER skip.\n'
    BARE_LESS_THAN = 'Use a < b here.\n'
    BARE_AMPERSAND = 'Tom & Jerry.\n'

    def test_i18_body_over_200_lines_is_a_warning(
        self, instruction_rule: RuleCheck, sections: SectionWriter
    ) -> None:
        code, out = instruction_rule.check(body=sections(SECTIONS) + self.FILLER)

        assert code == 0
        assert 'lines; this loads whenever the rule applies' in out

    def test_i19_more_than_one_emphasis_marker_is_a_warning(
        self, instruction_rule: RuleCheck, sections: SectionWriter
    ) -> None:
        code, out = instruction_rule.check(body=sections(SECTIONS) + self.EMPHASIS)

        assert code == 0
        assert 'warning: 2 emphasis markers' in out

    def test_i20_body_that_is_not_strictly_parseable_is_a_warning(
        self, instruction_rule: RuleCheck, sections: SectionWriter
    ) -> None:
        code, out = instruction_rule.check(body=sections(SECTIONS) + self.BARE_LESS_THAN)

        assert code == 0
        assert 'warning: not strictly parseable' in out

    def test_i20_a_bare_ampersand_is_parseable(
        self, instruction_rule: RuleCheck, sections: SectionWriter
    ) -> None:
        code, out = instruction_rule.check(body=sections(SECTIONS) + self.BARE_AMPERSAND)

        assert code == 0
        assert 'not strictly parseable' not in out
