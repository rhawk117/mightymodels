import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from vibe_code_cli.cli import main

type SectionWriter = Callable[[Sequence[str]], str]

SECTIONS = ('scope', 'conventions', 'examples', 'anti_patterns', 'verification')
PATH_FRONTMATTER = '---\npaths:\n  - "src/**/*.py"\n---\n'
CLEAN_COUNTS = '0 error(s), 0 warning(s)'
RULE = PATH_FRONTMATTER + ''.join(f'<{name}>\nText.\n</{name}>\n\n' for name in SECTIONS)
GIT = ('git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', '-c', 'commit.gpgsign=false')


def paths_frontmatter(*patterns: str) -> str:
    return '---\npaths:\n' + ''.join(f"  - '{pattern}'\n" for pattern in patterns) + '---\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class InstructionTree:
    root: Path
    capsys: pytest.CaptureFixture[str]

    def write(self, files: Mapping[str, str]) -> Path:
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return self.root

    def audit(self, *options: str, target: Path | None = None) -> tuple[int, str]:
        target = self.root if target is None else target
        code = main(['instruction', 'validate', str(target), *options])
        return code, self.capsys.readouterr().out


@dataclass(slots=True, kw_only=True, frozen=True)
class RuleCheck:
    root: Path
    capsys: pytest.CaptureFixture[str]
    sections: SectionWriter

    def check(
        self,
        frontmatter: str = PATH_FRONTMATTER,
        *,
        body: str | None = None,
        options: Sequence[str] = (),
    ) -> tuple[int, str]:
        rule = self.root / '.claude' / 'rules' / 'x.md'
        rule.parent.mkdir(parents=True, exist_ok=True)
        rule.write_text(frontmatter + (self.sections(SECTIONS) if body is None else body))
        code = main(['instruction', 'validate', str(rule), *options])
        return code, self.capsys.readouterr().out


@dataclass(slots=True, kw_only=True, frozen=True)
class GitRepo:
    root: Path

    def __call__(self, *arguments: str) -> None:
        subprocess.run([*GIT, *arguments], cwd=self.root, check=True, capture_output=True)  # noqa: S603 - fixed argument list in a test, no shell


@pytest.fixture
def instruction_tree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> InstructionTree:
    return InstructionTree(root=tmp_path, capsys=capsys)


@pytest.fixture
def instruction_rule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], sections: SectionWriter
) -> RuleCheck:
    return RuleCheck(root=tmp_path, capsys=capsys, sections=sections)
