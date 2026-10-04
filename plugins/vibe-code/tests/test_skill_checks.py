from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from vibe_code_cli.findings import CannotCheckError, Finding
from vibe_code_cli.skill.command import check_skill
from vibe_code_cli.skill.tests.support import DESCRIPTION, SkillRoot, messages

type FindingAssertion = Callable[[Sequence[Finding], str], None]


class TestSkillFile:
    @pytest.fixture
    def without_skill_md(self, tmp_path: Path) -> Path:
        skill_dir = tmp_path / 'demo-skill'
        skill_dir.mkdir()
        return skill_dir

    def test_clean_skill_has_no_findings(self, skill_root: SkillRoot) -> None:
        assert skill_root.check() == []

    def test_vs3_skill_md_missing(
        self, without_skill_md: Path, assert_error: FindingAssertion
    ) -> None:
        assert_error(check_skill(without_skill_md), 'SKILL.md not found')


class TestFrontmatterKeys:
    UNKNOWN = 'colour: red\n'
    CLAUDE_CODE = (
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
    OTHER_HOSTS = 'handoffs: []\nmcp-servers: {}\ntarget: vscode\n'

    def test_vs13_unknown_frontmatter_field(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        assert_error(skill_root.check(self.UNKNOWN), "unknown frontmatter field 'colour'")

    def test_cs_a17_a18_c11_known_keys_are_claude_codes(self, skill_root: SkillRoot) -> None:
        assert skill_root.check(self.CLAUDE_CODE) == []

    def test_cs_a18_c11_keys_of_other_agent_hosts_are_unknown(self, skill_root: SkillRoot) -> None:
        assert len(messages(skill_root.check(self.OTHER_HOSTS), 'error')) == 3


class TestNameAndDescription:
    NO_NAME = f'description: {DESCRIPTION}\n'
    EMPTY_NAME = f'name: ""\ndescription: {DESCRIPTION}\n'
    EMPTY_DESCRIPTION = 'name: demo-skill\ndescription: ""\n'
    LONG_DESCRIPTION = f'name: demo-skill\ndescription: {"x" * 1100}\n'
    LONG_LISTING = f'when_to_use: {"y" * 1500}\n'
    UPPERCASE_NAME = 'Demo_Skill'
    LONG_NAME = 'n' * 70
    OTHER_NAME = f'name: other-skill\ndescription: {DESCRIPTION}\n'

    def test_vs15a_name_missing(
        self, skill_root: SkillRoot, assert_warning: FindingAssertion
    ) -> None:
        assert_warning(skill_root.check(frontmatter=self.NO_NAME), 'name is missing')

    def test_vs15c_name_empty(self, skill_root: SkillRoot, assert_error: FindingAssertion) -> None:
        assert_error(skill_root.check(frontmatter=self.EMPTY_NAME), 'name must not be empty')

    def test_vs15f_description_empty(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        assert_error(skill_root.check(frontmatter=self.EMPTY_DESCRIPTION), 'description')

    def test_vs16_description_over_1024_chars(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        findings = skill_root.check(frontmatter=self.LONG_DESCRIPTION)

        assert_error(findings, 'description is 1100 chars; the limit is 1024')

    def test_cs_a32_listing_text_over_1536_chars(
        self, skill_root: SkillRoot, assert_warning: FindingAssertion
    ) -> None:
        findings = skill_root.check(self.LONG_LISTING)

        assert_warning(findings, 'Claude Code truncates the skill listing at 1536')

    def test_vs20a_name_fails_lowercase_hyphen_pattern(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        findings = check_skill(skill_root.write(directory=self.UPPERCASE_NAME))

        assert_error(findings, "name 'Demo_Skill' must be 1 to 64 chars")

    def test_vs20b_name_over_64_chars(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        findings = check_skill(skill_root.write(directory=self.LONG_NAME))

        assert_error(findings, 'must be 1 to 64 chars')

    def test_vs21_name_differs_from_directory(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        findings = skill_root.check(frontmatter=self.OTHER_NAME)

        assert_error(findings, "name 'other-skill' must equal the directory name 'demo-skill'")


class TestOptionalFields:
    LICENSE_LIST = 'license: [MIT]\n'
    LICENSE_EMPTY = 'license: ""\n'
    COMPATIBILITY_NUMBER = 'compatibility: 3\n'
    COMPATIBILITY_EMPTY = 'compatibility: ""\n'
    COMPATIBILITY_LONG = f'compatibility: {"c" * 600}\n'
    ARGUMENT_HINT_LIST = 'argument-hint: [file]\n'
    ARGUMENT_HINT_EMPTY = 'argument-hint: ""\n'
    METADATA_NUMBER = 'metadata:\n  version: 2\n'

    def test_vs17a_license_not_a_string(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        findings = skill_root.check(self.LICENSE_LIST)

        assert_error(findings, 'Expected `str`, got `array` - at `$.license`')

    def test_vs17b_license_empty(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        assert_error(skill_root.check(self.LICENSE_EMPTY), 'license must not be empty')

    def test_vs18a_compatibility_not_a_string(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        findings = skill_root.check(self.COMPATIBILITY_NUMBER)

        assert_error(findings, 'Expected `str`, got `int` - at `$.compatibility`')

    def test_vs18b_compatibility_empty(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        assert_error(skill_root.check(self.COMPATIBILITY_EMPTY), 'compatibility must not be empty')

    def test_vs18c_compatibility_over_500_chars(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        findings = skill_root.check(self.COMPATIBILITY_LONG)

        assert_error(findings, 'compatibility is 600 chars; the limit is 500')

    def test_vs19a_argument_hint_not_a_string(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        findings = skill_root.check(self.ARGUMENT_HINT_LIST)

        assert_error(findings, 'Expected `str`, got `array` - at `$.argument-hint`')

    def test_vs19b_argument_hint_empty(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        assert_error(skill_root.check(self.ARGUMENT_HINT_EMPTY), 'argument-hint must not be empty')

    def test_vs22b_metadata_values_not_strings(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        findings = skill_root.check(self.METADATA_NUMBER)

        assert_error(findings, 'Expected `str`, got `int` - at `$.metadata[...]`')


class TestInvocationFlags:
    BOTH_OPEN = 'argument-hint: "[file]"\ndisable-model-invocation: true\nuser-invocable: true\n'
    NOT_BOOLEANS = 'disable-model-invocation: maybe\nuser-invocable: maybe\n'
    WRONG_TYPE = 'user-invocable: [x]\n'
    WORDS = 'disable-model-invocation: No\nuser-invocable: ON\n'
    DIGITS = 'disable-model-invocation: 0\nuser-invocable: 1\n'
    BOTH_RESTRICT = (
        'argument-hint: "[file]"\ndisable-model-invocation: true\nuser-invocable: false\n'
    )
    HUMAN_ONLY = 'disable-model-invocation: true\n'

    @pytest.fixture
    def digits_root(self, tmp_path: Path) -> SkillRoot:
        return SkillRoot(root=tmp_path / 'digits')

    def test_cs_a17_flag_keys_raise_nothing_under_any_mode(self, skill_root: SkillRoot) -> None:
        assert skill_root.check(self.BOTH_OPEN) == []

    def test_vs23_flags_must_be_booleans(self, skill_root: SkillRoot) -> None:
        assert len(messages(skill_root.check(self.NOT_BOOLEANS), 'error')) == 2

    def test_vs23_a_flag_of_the_wrong_type_prints_the_decoder_message(
        self, skill_root: SkillRoot
    ) -> None:
        assert messages(skill_root.check(self.WRONG_TYPE), 'error') == [
            'Expected `bool | int | str`, got `array` - at `$.user-invocable`'
        ]

    def test_cs_a21_flags_accept_yes_no_on_off_and_digits(
        self, skill_root: SkillRoot, digits_root: SkillRoot
    ) -> None:
        assert skill_root.check(self.WORDS) == []
        assert digits_root.check(self.DIGITS) == []

    def test_vs24_both_flags_restrict(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        findings = skill_root.check(self.BOTH_RESTRICT)

        assert_error(findings, 'neither user-invocable nor model-invocable')

    def test_vs25_human_only_skill_without_argument_hint(
        self, skill_root: SkillRoot, assert_warning: FindingAssertion
    ) -> None:
        findings = skill_root.check(self.HUMAN_ONLY)

        assert_warning(findings, 'human-only skill has no argument-hint')


class TestAllowedTools:
    EMPTY_STRING = 'allowed-tools: ""\n'
    EMPTY_LIST = 'allowed-tools: []\n'
    EMPTY_ENTRY = 'allowed-tools: Read,, Grep\n'
    UNCLOSED_RULE = 'allowed-tools: Read Bash(git add *\n'
    STAR_PLUS_OTHERS = 'allowed-tools: "* Read"\n'
    CLAUDE_CODE_RULES = (
        'allowed-tools: Bash(uv *) Read Grep\n',
        'allowed-tools: Bash(git add *), Read, mcp__github__create_issue\n',
        'allowed-tools:\n  - Bash(uv run pytest *)\n  - WebFetch(domain:example.com)\n',
    )

    @pytest.fixture
    def rule_roots(self, tmp_path: Path) -> list[SkillRoot]:
        roots = range(len(self.CLAUDE_CODE_RULES))
        return [SkillRoot(root=tmp_path / str(index)) for index in roots]

    def test_vs26a_allowed_tools_empty_string(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        assert_error(skill_root.check(self.EMPTY_STRING), 'must not be an empty string')

    def test_vs26b_allowed_tools_empty_list(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        assert_error(skill_root.check(self.EMPTY_LIST), 'must not be an empty list')

    def test_vs26e_allowed_tools_empty_entry(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        assert_error(skill_root.check(self.EMPTY_ENTRY), 'contains an empty entry')

    def test_vs26f_allowed_tools_bad_token(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        findings = skill_root.check(self.UNCLOSED_RULE)

        assert_error(findings, "entry 'Bash(git add *' is not a Claude Code rule")

    def test_vs26g_allowed_tools_star_plus_others(
        self, skill_root: SkillRoot, assert_warning: FindingAssertion
    ) -> None:
        findings = skill_root.check(self.STAR_PLUS_OTHERS)

        assert_warning(findings, "contains '*' plus other entries")

    def test_cs_a19_allowed_tools_accept_claude_code_rules(
        self, rule_roots: list[SkillRoot]
    ) -> None:
        for root, extra in zip(rule_roots, self.CLAUDE_CODE_RULES, strict=True):
            assert root.check(extra) == [], extra


class TestBody:
    EMPTY = '\n'
    OVER_500_LINES = '# Demo\n' + 'line\n' * 520
    MISSING_FILE = '# Demo\n\nRun scripts/missing.py first.\n'
    DOTDOT = '# Demo\n\nSee [notes](../notes.md).\n'
    EMPTY_LINK_TARGETS = '# Demo\n\nSee [the notes]( ) and [more](<>).\n'

    def test_vs27_empty_body(self, skill_root: SkillRoot, assert_error: FindingAssertion) -> None:
        assert_error(skill_root.check(body=self.EMPTY), 'no Markdown body')

    def test_vs29_skill_md_over_500_lines(
        self, skill_root: SkillRoot, assert_warning: FindingAssertion
    ) -> None:
        assert_warning(skill_root.check(body=self.OVER_500_LINES), 'SKILL.md is 525 lines')

    def test_vs28a_body_references_missing_file(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        findings = skill_root.check(body=self.MISSING_FILE)

        assert_error(findings, 'body references scripts/missing.py but it does not exist')

    def test_vs28b_reference_escapes_with_dotdot(
        self, skill_root: SkillRoot, assert_error: FindingAssertion
    ) -> None:
        findings = skill_root.check(body=self.DOTDOT)

        assert_error(findings, 'reference escapes the skill directory: ../notes.md')

    def test_empty_link_target_is_not_a_reference(self, skill_root: SkillRoot) -> None:
        assert skill_root.check(body=self.EMPTY_LINK_TARGETS) == []


class TestResourceFiles:
    HOST_BODY = '# Demo\n\nRun scripts/host.\n'
    OUTSIDE_BODY = '# Demo\n\nRead references/outside.md.\n'
    REFERENCING_BODY = '# Demo\n\nRead references/extra.md and scripts/.\n'

    @pytest.fixture
    def symlink_outside(self, skill_root: SkillRoot) -> Path:
        skill_dir = skill_root.write(body=self.HOST_BODY)
        (skill_dir / 'scripts').mkdir()
        (skill_dir / 'scripts' / 'host').symlink_to('/etc/hostname')
        return skill_dir

    @pytest.fixture
    def reference_through_symlink(self, skill_root: SkillRoot) -> Path:
        outside = skill_root.root / 'outside.md'
        outside.write_text('x', encoding='utf-8')
        skill_dir = skill_root.write(body=self.OUTSIDE_BODY)
        (skill_dir / 'references').mkdir()
        (skill_dir / 'references' / 'outside.md').symlink_to(outside)
        return skill_dir

    @pytest.fixture
    def empty_assets(self, skill_root: SkillRoot) -> Path:
        skill_dir = skill_root.write()
        (skill_dir / 'assets').mkdir()
        return skill_dir

    @pytest.fixture
    def unreferenced_file(self, skill_root: SkillRoot) -> Path:
        skill_dir = skill_root.write()
        (skill_dir / 'references').mkdir()
        (skill_dir / 'references' / 'extra.md').write_text('x', encoding='utf-8')
        return skill_dir

    @pytest.fixture
    def referenced_files(self, skill_root: SkillRoot) -> Path:
        skill_dir = skill_root.write(body=self.REFERENCING_BODY)
        (skill_dir / 'references').mkdir()
        (skill_dir / 'references' / 'extra.md').write_text('x', encoding='utf-8')
        (skill_dir / 'scripts').mkdir()
        (skill_dir / 'scripts' / 'run.py').write_text('x', encoding='utf-8')
        return skill_dir

    def test_vs28c_symlink_in_resource_dir_points_outside(
        self, symlink_outside: Path, assert_error: FindingAssertion
    ) -> None:
        findings = check_skill(symlink_outside)

        assert_error(findings, 'scripts/host is a symlink outside the skill directory')

    def test_vs28d_referenced_file_escapes_through_symlink(
        self, reference_through_symlink: Path, assert_error: FindingAssertion
    ) -> None:
        findings = check_skill(reference_through_symlink)

        assert_error(findings, 'escapes the skill directory through a symlink')

    def test_vs28e_empty_resource_directory(
        self, empty_assets: Path, assert_warning: FindingAssertion
    ) -> None:
        assert_warning(check_skill(empty_assets), 'assets/ is empty')

    def test_vs28f_resource_file_never_referenced(
        self, unreferenced_file: Path, assert_warning: FindingAssertion
    ) -> None:
        assert_warning(check_skill(unreferenced_file), 'references/extra.md is never referenced')

    def test_vs28_referenced_resources_pass(self, referenced_files: Path) -> None:
        assert check_skill(referenced_files) == []


class TestInvalidYaml:
    UNCLOSED_LIST = 'name: demo-skill\ndescription: [unclosed\n'
    UNCLOSED_QUOTE = 'name: demo-skill\ndescription: "unclosed\n'

    def test_invalid_yaml_the_builtin_passed_cannot_be_checked(self, skill_root: SkillRoot) -> None:
        with pytest.raises(CannotCheckError, match='field checks could not run'):
            skill_root.check(frontmatter=self.UNCLOSED_LIST)

    def test_invalid_yaml_the_builtin_reported_keeps_the_own_checks(
        self, skill_root: SkillRoot
    ) -> None:
        skill_dir = skill_root.write(self.UNCLOSED_QUOTE)

        assert check_skill(skill_dir, builtin_errored=True) == []
