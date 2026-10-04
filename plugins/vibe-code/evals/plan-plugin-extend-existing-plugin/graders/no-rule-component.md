---
type: regex
target: { source: file, path: fixtures/plugin/plugin-plan.json }
pattern: '"kind"\s*:\s*"rule"'
match: not_contains
---
