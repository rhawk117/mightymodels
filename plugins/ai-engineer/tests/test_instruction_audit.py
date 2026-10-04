import shutil
import subprocess
from pathlib import Path

import pytest
from ai_engineer_cli.cli import main
from ai_engineer_cli.findings import info, report

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'instructions'
RULE = '---\npaths:\n  - "src/**/*.py"\n---\n' + ''.join(
    f'<{name}>\nText.\n</{name}>\n\n'
    for name in ('scope', 'conventions', 'examples', 'anti_patterns', 'verification')
)
GIT = ('git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', '-c', 'commit.gpgsign=false')


def project(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def audit(root: Path, capsys: pytest.CaptureFixture[str], *options: str) -> tuple[int, str]:
    code = main(['create-instructions', 'validate', str(root), *options])
    return code, capsys.readouterr().out


def fixture_copy(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    shutil.copytree(FIXTURES / name, root)
    return root


def git(root: Path, *arguments: str) -> None:
    subprocess.run([*GIT, *arguments], cwd=root, check=True, capture_output=True)  # noqa: S603 - fixed argument list in a test, no shell


def test_clean_fixture_passes_with_only_an_info_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = audit(fixture_copy(tmp_path, 'clean'), capsys)

    assert code == 0
    assert 'info: CLAUDE.md:1: `@AGENTS.md` expands at launch' in out
    assert out.splitlines()[-1] == 'PASS clean: 0 error(s), 0 warning(s), 1 info'


def test_dirty_fixture_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = audit(fixture_copy(tmp_path, 'dirty'), capsys, '--strict')

    assert code == 1
    assert out.splitlines()[-1].startswith('FAIL dirty: ')


def test_directory_runs_the_frontmatter_checks_on_every_rule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'.claude/rules/a/b.md': '---\npaths:\n---\n# Rule\n'})

    code, out = audit(root, capsys)

    assert code == 1
    assert 'error: .claude/rules/a/b.md: paths is empty' in out


def test_directory_does_not_run_the_body_checks_on_a_docs_shaped_rule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rule = '---\npaths:\n  - "src/**/*.py"\n---\n# Python\n\n- Use type hints.\n'
    root = project(tmp_path, {'.claude/rules/py.md': rule, 'CLAUDE.md': '# Hi\n'})

    code, out = audit(root, capsys)

    assert code == 0
    assert 'required section' not in out


def test_file_mode_runs_the_body_checks_on_a_docs_shaped_rule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    docs_shaped = '---\npaths:\n  - "src/**/*.py"\n---\n# Python\n\n- Use type hints.\n'
    rule = project(tmp_path, {'py.md': docs_shaped}) / 'py.md'

    code = main(['create-instructions', 'validate', str(rule)])

    assert code == 1
    assert 'error: required section <scope> is missing' in capsys.readouterr().out


def test_directory_does_not_run_the_rule_checks_on_claude_md(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = audit(project(tmp_path, {'CLAUDE.md': '# Hi\n', 'AGENTS.md': '# Hi\n'}), capsys)

    assert code == 0
    assert 'required section' not in out


def test_directory_without_instruction_files_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = audit(tmp_path, capsys)

    assert code == 0
    assert out.endswith('0 error(s), 0 warning(s)\n')


def test_a1_always_on_file_over_4_mib_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'CLAUDE.md': 'x' * (4 * 1024 * 1024 + 1)})

    code, out = audit(root, capsys)

    assert code == 1
    assert 'error: CLAUDE.md: over 4 MiB, so Claude Code skips the file entirely' in out


def test_a1_a_long_file_under_4_mib_is_not_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'CLAUDE.md': '- a rule\n' * 1200})

    code, out = audit(root, capsys)

    assert code == 0
    assert 'error' not in out.replace('0 error(s)', '')


def test_a2_always_on_file_at_200_lines_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'.claude/CLAUDE.md': '- a rule\n' * 200})

    code, out = audit(root, capsys)

    assert code == 0
    assert 'warning: .claude/CLAUDE.md: 200 lines, at or over the 200-line target' in out


def test_a2_a_file_under_the_target_draws_no_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out = audit(project(tmp_path, {'CLAUDE.md': '- a rule\n' * 199}), capsys)

    assert 'line target' not in out


def test_a2_a_rule_file_is_not_held_to_the_claude_md_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out = audit(project(tmp_path, {'.claude/rules/big.md': RULE + 'filler\n' * 200}), capsys)

    assert 'line target' not in out


def test_a3_lint_leakage_is_a_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, {'CLAUDE.md': '# P\n\n- Indentation: 2 spaces\n'})

    code, out = audit(root, capsys)

    assert code == 0
    assert 'warning: CLAUDE.md:3: mentions indentation' in out


def test_a3_lint_leakage_inside_a_code_fence_is_ignored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'CLAUDE.md': '# X\n\n```md\n- Indentation: 2 spaces\n```\n'})

    _, out = audit(root, capsys)

    assert 'mentions' not in out


def test_a3_lint_leakage_is_found_in_a_rule_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'.claude/rules/s.md': RULE + '- Use snake_case names.\n'})

    _, out = audit(root, capsys)

    assert 'warning: .claude/rules/s.md:' in out
    assert 'mentions naming case' in out


def test_a4_blind_reference_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'CLAUDE.md': '# P\n\nSee `docs/plugin-reorg.md`.\n'})

    code, out = audit(root, capsys)

    assert code == 0
    assert 'warning: CLAUDE.md:3: references `docs/plugin-reorg.md` without saying' in out


def test_a4_reference_that_says_why_is_fine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'CLAUDE.md': '- `docs/auth.md` covers the token flow.\n'})

    _, out = audit(root, capsys)

    assert 'references' not in out


def test_a5_conflicting_commands_across_always_on_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'CLAUDE.md': '- Test: `pnpm test`\n', 'AGENTS.md': '- `npm test`\n'})

    code, out = audit(root, capsys)

    assert code == 0
    assert 'multiple test commands across always-on files: `npm test`, `pnpm test`' in out


def test_a8_rule_without_paths_is_info_and_never_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'.claude/rules/x.md': '---\nnote: 1\n---\n' + RULE.split('---\n')[2]})

    code, out = audit(root, capsys, '--strict')

    assert code == 0
    assert 'info: .claude/rules/x.md: no paths frontmatter' in out
    assert out.splitlines()[-1] == f'PASS {root.name}: 0 error(s), 0 warning(s), 1 info'


def test_a8_rule_with_paths_draws_no_info(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out = audit(project(tmp_path, {'.claude/rules/x.md': RULE}), capsys)

    assert 'no paths frontmatter' not in out


def test_a9_import_is_info_and_never_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'CLAUDE.md': '@docs/extra.md\n'})

    code, out = audit(root, capsys, '--strict')

    assert code == 0
    assert 'info: CLAUDE.md:1: `@docs/extra.md` expands at launch' in out


def test_a9_import_in_a_code_span_or_fence_is_ignored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(
        tmp_path, {'CLAUDE.md': 'Write `@README` to mention it.\n\n```\n@docs/x.md\n```\n'}
    )

    _, out = audit(root, capsys)

    assert 'info' not in out.replace('info\n', '')
    assert 'expands at launch' not in out


def test_a11_claude_md_without_an_agents_import_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'CLAUDE.md': '# Hi\n', 'AGENTS.md': '# Hi\n'})

    code, out = audit(root, capsys)

    assert code == 0
    assert 'warning: AGENTS.md: a CLAUDE.md exists but does not import AGENTS.md' in out


def test_a11_import_of_agents_md_satisfies_the_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'CLAUDE.md': '@AGENTS.md\n', 'AGENTS.md': '# Hi\n'})

    _, out = audit(root, capsys)

    assert 'does not import' not in out


def test_a11_symlinked_claude_md_satisfies_the_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'AGENTS.md': '# Hi\n'})
    (root / 'CLAUDE.md').symlink_to('AGENTS.md')

    _, out = audit(root, capsys)

    assert 'does not import' not in out


def test_a11_agents_md_alone_draws_no_finding_about_claude_code_reading_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = audit(project(tmp_path, {'AGENTS.md': '# Hi\n'}), capsys)

    assert code == 0
    assert out == 'PASS ' + tmp_path.name + ': 0 error(s), 0 warning(s)\n'


def test_a13_single_commit_always_on_file_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'CLAUDE.md': '# Hi\n'})
    git(root, 'init', '-q')
    git(root, 'add', 'CLAUDE.md')
    git(root, 'commit', '-q', '-m', 'init')

    code, out = audit(root, capsys)

    assert code == 0
    assert 'warning: CLAUDE.md: only one commit' in out


def test_a13_a_revised_file_draws_no_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path, {'CLAUDE.md': '# Hi\n'})
    git(root, 'init', '-q')
    git(root, 'add', 'CLAUDE.md')
    git(root, 'commit', '-q', '-m', 'init')
    (root / 'CLAUDE.md').write_text('# Hi again\n')
    git(root, 'commit', '-q', '-am', 'revise')

    _, out = audit(root, capsys)

    assert 'only one commit' not in out


def test_a13_is_skipped_outside_a_git_work_tree(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('GIT_CEILING_DIRECTORIES', str(tmp_path.parent))
    root = project(tmp_path, {'CLAUDE.md': '# Hi\n'})

    code, out = audit(root, capsys)

    assert code == 0
    assert out == f'PASS {root.name}: 0 error(s), 0 warning(s)\n'


def test_a13_is_skipped_when_git_is_absent(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = project(tmp_path, {'CLAUDE.md': '# Hi\n'})
    git(root, 'init', '-q')
    git(root, 'add', 'CLAUDE.md')
    git(root, 'commit', '-q', '-m', 'init')
    monkeypatch.setenv('PATH', str(tmp_path / 'no-bin'))

    code, out = audit(root, capsys)

    assert code == 0
    assert 'only one commit' not in out


def test_no_github_files_are_read(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(
        tmp_path,
        {
            '.github/instructions/b.instructions.md': '- Indentation: 2 spaces\n' * 300,
            '.github/instructions/a.instructions.md': 'no frontmatter\n',
        },
    )

    code, out = audit(root, capsys)

    assert code == 0
    assert out == f'PASS {root.name}: 0 error(s), 0 warning(s)\n'


def test_missing_directory_exits_two_without_a_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = audit(tmp_path / 'absent', capsys)

    assert code == 2
    assert out == ''


def test_an_unreadable_instruction_file_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path
    (root / 'CLAUDE.md').write_bytes(b'\xff\xfe\x00bad')

    code = main(['create-instructions', 'validate', str(root)])

    captured = capsys.readouterr()
    assert code == 2
    assert 'could not read' in captured.err
    assert captured.out == ''


def test_info_finding_is_printed_counted_and_never_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = report('x', [info('note')], strict=True)

    assert code == 0
    assert capsys.readouterr().out == 'info: note\nPASS x: 0 error(s), 0 warning(s), 1 info\n'
