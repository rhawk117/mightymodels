from dataclasses import dataclass
from pathlib import Path

import pytest

from vibe_code_cli.findings import Finding
from vibe_code_cli.skill.command import check_skill

DESCRIPTION = 'Summarize a file. Use when the user asks for a summary of a file.'
CLEAN_FRONTMATTER = f'name: demo-skill\ndescription: {DESCRIPTION}\n'
CLEAN_BODY = '# Demo\n\nSummarize the file the user names.\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class SkillRoot:
    root: Path

    def write(
        self,
        frontmatter: str | None = None,
        *,
        body: str = CLEAN_BODY,
        directory: str = 'demo-skill',
    ) -> Path:
        skill_dir = self.root / directory
        skill_dir.mkdir(parents=True)
        frontmatter = frontmatter or f'name: {directory}\ndescription: {DESCRIPTION}\n'
        (skill_dir / 'SKILL.md').write_text(f'---\n{frontmatter}---\n{body}', encoding='utf-8')
        return skill_dir

    def check(
        self, extra: str = '', *, frontmatter: str = CLEAN_FRONTMATTER, body: str = CLEAN_BODY
    ) -> list[Finding]:
        return check_skill(self.write(frontmatter + extra, body=body))


def messages(findings: list[Finding], level: str) -> list[str]:
    return [finding.message for finding in findings if finding.level == level]


@pytest.fixture
def skill_root(tmp_path: Path) -> SkillRoot:
    return SkillRoot(root=tmp_path)
