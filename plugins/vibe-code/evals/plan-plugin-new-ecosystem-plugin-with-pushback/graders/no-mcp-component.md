---
type: regex
target: { source: file, path: fixtures/new/tf-guard/plugin-plan.json }
pattern: '"kind"\s*:\s*"mcp"'
match: not_contains
---
