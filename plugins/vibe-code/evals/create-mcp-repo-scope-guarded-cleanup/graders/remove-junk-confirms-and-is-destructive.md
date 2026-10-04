---
type: regex
target: { source: file, path: fixtures/repo/mcp/repo-janitor/src/repo_janitor/server.py }
pattern: '(?=[\s\S]*Annotated\[\s*ElicitationResult\[)(?=[\s\S]*Resolve\()[\s\S]*destructive_hint=True'
---
