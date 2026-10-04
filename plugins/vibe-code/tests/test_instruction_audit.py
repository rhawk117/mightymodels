import shutil
from pathlib import Path

import pytest
from vibe_code_cli.cli import main
from vibe_code_cli.findings import info, report
from vibe_code_cli.instruction.tests.support import RULE, GitRepo, InstructionTree


class TestFixtureTrees:
    INSTRUCTIONS = Path(__file__).resolve().parent / 'fixtures' / 'instructions'

    @pytest.fixture
    def clean_tree(self, tmp_path: Path) -> Path:
        return shutil.copytree(self.INSTRUCTIONS / 'clean', tmp_path / 'clean')

    @pytest.fixture
    def dirty_tree(self, tmp_path: Path) -> Path:
        return shutil.copytree(self.INSTRUCTIONS / 'dirty', tmp_path / 'dirty')

    def test_clean_fixture_passes_with_only_an_info_finding(
        self, instruction_tree: InstructionTree, clean_tree: Path
    ) -> None:
        code, out = instruction_tree.audit(target=clean_tree)

        assert code == 0
        assert 'info: CLAUDE.md:1: `@AGENTS.md` expands at launch' in out
        assert out.splitlines()[-1] == 'PASS clean: 0 error(s), 0 warning(s), 1 info'

    def test_dirty_fixture_exits_one(
        self, instruction_tree: InstructionTree, dirty_tree: Path
    ) -> None:
        code, out = instruction_tree.audit('--strict', target=dirty_tree)

        assert code == 1
        assert out.splitlines()[-1].startswith('FAIL dirty: ')


class TestWhatIsChecked:
    EMPTY_PATHS_RULE = '---\npaths:\n---\n# Rule\n'
    DOCS_SHAPED = '---\npaths:\n  - "src/**/*.py"\n---\n# Python\n\n- Use type hints.\n'
    HEADING = '# Hi\n'
    NO_GITHUB_FILES = '- Indentation: 2 spaces\n' * 300

    def test_directory_runs_the_frontmatter_checks_on_every_rule(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'.claude/rules/a/b.md': self.EMPTY_PATHS_RULE})

        code, out = instruction_tree.audit()

        assert code == 1
        assert 'error: .claude/rules/a/b.md: paths is empty' in out

    def test_directory_does_not_run_the_body_checks_on_a_docs_shaped_rule(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'.claude/rules/py.md': self.DOCS_SHAPED, 'CLAUDE.md': self.HEADING})

        code, out = instruction_tree.audit()

        assert code == 0
        assert 'required section' not in out

    def test_file_mode_runs_the_body_checks_on_a_docs_shaped_rule(
        self, instruction_tree: InstructionTree
    ) -> None:
        rule = instruction_tree.write({'py.md': self.DOCS_SHAPED}) / 'py.md'

        code, out = instruction_tree.audit(target=rule)

        assert code == 1
        assert 'error: required section <scope> is missing' in out

    def test_directory_does_not_run_the_rule_checks_on_claude_md(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'CLAUDE.md': self.HEADING, 'AGENTS.md': self.HEADING})

        code, out = instruction_tree.audit()

        assert code == 0
        assert 'required section' not in out

    def test_directory_without_instruction_files_passes(
        self, instruction_tree: InstructionTree
    ) -> None:
        code, out = instruction_tree.audit()

        assert code == 0
        assert out.endswith('0 error(s), 0 warning(s)\n')

    def test_no_github_files_are_read(self, instruction_tree: InstructionTree) -> None:
        instruction_tree.write(
            {
                '.github/instructions/b.instructions.md': self.NO_GITHUB_FILES,
                '.github/instructions/a.instructions.md': 'no frontmatter\n',
            }
        )

        code, out = instruction_tree.audit()

        assert code == 0
        assert out == f'PASS {instruction_tree.root.name}: 0 error(s), 0 warning(s)\n'


class TestUnusableInput:
    UNDECODABLE = b'\xff\xfe\x00bad'

    def test_missing_directory_exits_two_without_a_verdict(
        self, instruction_tree: InstructionTree
    ) -> None:
        code, out = instruction_tree.audit(target=instruction_tree.root / 'absent')

        assert code == 2
        assert out == ''

    def test_an_unreadable_instruction_file_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / 'CLAUDE.md').write_bytes(self.UNDECODABLE)

        code = main(['instruction', 'validate', str(tmp_path)])

        captured = capsys.readouterr()
        assert code == 2
        assert 'could not read' in captured.err
        assert captured.out == ''


class TestA1FileSize:
    OVER_4_MIB = 'x' * (4 * 1024 * 1024 + 1)
    LONG_UNDER_4_MIB = '- a rule\n' * 1200

    def test_a1_always_on_file_over_4_mib_is_an_error(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'CLAUDE.md': self.OVER_4_MIB})

        code, out = instruction_tree.audit()

        assert code == 1
        assert 'error: CLAUDE.md: over 4 MiB, so Claude Code skips the file entirely' in out

    def test_a1_a_long_file_under_4_mib_is_not_an_error(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'CLAUDE.md': self.LONG_UNDER_4_MIB})

        code, out = instruction_tree.audit()

        assert code == 0
        assert 'error' not in out.replace('0 error(s)', '')


class TestA2LineTarget:
    AT_TARGET = '- a rule\n' * 200
    UNDER_TARGET = '- a rule\n' * 199
    BIG_RULE = RULE + 'filler\n' * 200

    def test_a2_always_on_file_at_200_lines_is_a_warning(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'.claude/CLAUDE.md': self.AT_TARGET})

        code, out = instruction_tree.audit()

        assert code == 0
        assert 'warning: .claude/CLAUDE.md: 200 lines, at or over the 200-line target' in out

    def test_a2_a_file_under_the_target_draws_no_warning(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'CLAUDE.md': self.UNDER_TARGET})

        _, out = instruction_tree.audit()

        assert 'line target' not in out

    def test_a2_a_rule_file_is_not_held_to_the_claude_md_target(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'.claude/rules/big.md': self.BIG_RULE})

        _, out = instruction_tree.audit()

        assert 'line target' not in out


class TestA3LintLeakage:
    LEAKY = '# P\n\n- Indentation: 2 spaces\n'
    FENCED = '# X\n\n```md\n- Indentation: 2 spaces\n```\n'
    LEAKY_RULE = RULE + '- Use snake_case names.\n'

    def test_a3_lint_leakage_is_a_warning(self, instruction_tree: InstructionTree) -> None:
        instruction_tree.write({'CLAUDE.md': self.LEAKY})

        code, out = instruction_tree.audit()

        assert code == 0
        assert 'warning: CLAUDE.md:3: mentions indentation' in out

    def test_a3_lint_leakage_inside_a_code_fence_is_ignored(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'CLAUDE.md': self.FENCED})

        _, out = instruction_tree.audit()

        assert 'mentions' not in out

    def test_a3_lint_leakage_is_found_in_a_rule_file(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'.claude/rules/s.md': self.LEAKY_RULE})

        _, out = instruction_tree.audit()

        assert 'warning: .claude/rules/s.md:' in out
        assert 'mentions naming case' in out


class TestA4BlindReferences:
    BLIND = '# P\n\nSee `docs/plugin-reorg.md`.\n'
    EXPLAINED = '- `docs/auth.md` covers the token flow.\n'

    def test_a4_blind_reference_is_a_warning(self, instruction_tree: InstructionTree) -> None:
        instruction_tree.write({'CLAUDE.md': self.BLIND})

        code, out = instruction_tree.audit()

        assert code == 0
        assert 'warning: CLAUDE.md:3: references `docs/plugin-reorg.md` without saying' in out

    def test_a4_reference_that_says_why_is_fine(self, instruction_tree: InstructionTree) -> None:
        instruction_tree.write({'CLAUDE.md': self.EXPLAINED})

        _, out = instruction_tree.audit()

        assert 'references' not in out


class TestA5ConflictingCommands:
    PNPM = '- Test: `pnpm test`\n'
    NPM = '- `npm test`\n'

    def test_a5_conflicting_commands_across_always_on_files(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'CLAUDE.md': self.PNPM, 'AGENTS.md': self.NPM})

        code, out = instruction_tree.audit()

        assert code == 0
        assert 'multiple test commands across always-on files: `npm test`, `pnpm test`' in out


class TestA8RulePaths:
    NO_PATHS = '---\nnote: 1\n---\n' + RULE.split('---\n')[2]

    def test_a8_rule_without_paths_is_info_and_never_fails(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'.claude/rules/x.md': self.NO_PATHS})

        code, out = instruction_tree.audit('--strict')

        assert code == 0
        assert 'info: .claude/rules/x.md: no paths frontmatter' in out
        assert (
            out.splitlines()[-1]
            == f'PASS {instruction_tree.root.name}: 0 error(s), 0 warning(s), 1 info'
        )

    def test_a8_rule_with_paths_draws_no_info(self, instruction_tree: InstructionTree) -> None:
        instruction_tree.write({'.claude/rules/x.md': RULE})

        _, out = instruction_tree.audit()

        assert 'no paths frontmatter' not in out


class TestA9Imports:
    IMPORT = '@docs/extra.md\n'
    CODE_SPAN_AND_FENCE = 'Write `@README` to mention it.\n\n```\n@docs/x.md\n```\n'

    def test_a9_import_is_info_and_never_fails(self, instruction_tree: InstructionTree) -> None:
        instruction_tree.write({'CLAUDE.md': self.IMPORT})

        code, out = instruction_tree.audit('--strict')

        assert code == 0
        assert 'info: CLAUDE.md:1: `@docs/extra.md` expands at launch' in out

    def test_a9_import_in_a_code_span_or_fence_is_ignored(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'CLAUDE.md': self.CODE_SPAN_AND_FENCE})

        _, out = instruction_tree.audit()

        assert 'info' not in out.replace('info\n', '')
        assert 'expands at launch' not in out


class TestA11AgentsImport:
    HEADING = '# Hi\n'
    AGENTS_IMPORT = '@AGENTS.md\n'

    @pytest.fixture
    def symlinked_claude_md(self, instruction_tree: InstructionTree) -> Path:
        root = instruction_tree.write({'AGENTS.md': self.HEADING})
        (root / 'CLAUDE.md').symlink_to('AGENTS.md')
        return root

    def test_a11_claude_md_without_an_agents_import_is_a_warning(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'CLAUDE.md': self.HEADING, 'AGENTS.md': self.HEADING})

        code, out = instruction_tree.audit()

        assert code == 0
        assert 'warning: AGENTS.md: a CLAUDE.md exists but does not import AGENTS.md' in out

    def test_a11_import_of_agents_md_satisfies_the_check(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'CLAUDE.md': self.AGENTS_IMPORT, 'AGENTS.md': self.HEADING})

        _, out = instruction_tree.audit()

        assert 'does not import' not in out

    @pytest.mark.usefixtures('symlinked_claude_md')
    def test_a11_symlinked_claude_md_satisfies_the_check(
        self, instruction_tree: InstructionTree
    ) -> None:
        _, out = instruction_tree.audit()

        assert 'does not import' not in out

    def test_a11_agents_md_alone_draws_no_finding_about_claude_code_reading_it(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'AGENTS.md': self.HEADING})

        code, out = instruction_tree.audit()

        assert code == 0
        assert out == 'PASS ' + instruction_tree.root.name + ': 0 error(s), 0 warning(s)\n'


class TestA13CommitHistory:
    HEADING = '# Hi\n'
    REVISED = '# Hi again\n'

    @pytest.fixture
    def git(self, instruction_tree: InstructionTree) -> GitRepo:
        return GitRepo(root=instruction_tree.root)

    @pytest.fixture
    def single_commit(self, instruction_tree: InstructionTree, git: GitRepo) -> Path:
        root = instruction_tree.write({'CLAUDE.md': self.HEADING})
        git('init', '-q')
        git('add', 'CLAUDE.md')
        git('commit', '-q', '-m', 'init')
        return root

    @pytest.fixture
    def revised(self, single_commit: Path, git: GitRepo) -> Path:
        (single_commit / 'CLAUDE.md').write_text(self.REVISED)
        git('commit', '-q', '-am', 'revise')
        return single_commit

    @pytest.fixture
    def outside_a_work_tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('GIT_CEILING_DIRECTORIES', str(tmp_path.parent))

    @pytest.fixture
    def without_git(
        self, single_commit: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Path:
        monkeypatch.setenv('PATH', str(tmp_path / 'no-bin'))
        return single_commit

    def test_a13_single_commit_always_on_file_is_a_warning(
        self, instruction_tree: InstructionTree, single_commit: Path
    ) -> None:
        code, out = instruction_tree.audit(target=single_commit)

        assert code == 0
        assert 'warning: CLAUDE.md: only one commit' in out

    def test_a13_a_revised_file_draws_no_warning(
        self, instruction_tree: InstructionTree, revised: Path
    ) -> None:
        _, out = instruction_tree.audit(target=revised)

        assert 'only one commit' not in out

    @pytest.mark.usefixtures('outside_a_work_tree')
    def test_a13_is_skipped_outside_a_git_work_tree(
        self, instruction_tree: InstructionTree
    ) -> None:
        instruction_tree.write({'CLAUDE.md': self.HEADING})

        code, out = instruction_tree.audit()

        assert code == 0
        assert out == f'PASS {instruction_tree.root.name}: 0 error(s), 0 warning(s)\n'

    def test_a13_is_skipped_when_git_is_absent(
        self, instruction_tree: InstructionTree, without_git: Path
    ) -> None:
        code, out = instruction_tree.audit(target=without_git)

        assert code == 0
        assert 'only one commit' not in out


class TestInfoFinding:
    NOTE = 'note'

    def test_info_finding_is_printed_counted_and_never_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = report('x', [info(self.NOTE)], strict=True)

        assert code == 0
        assert capsys.readouterr().out == 'info: note\nPASS x: 0 error(s), 0 warning(s), 1 info\n'
