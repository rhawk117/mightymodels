---
type: regex
target: { source: file, path: fixtures/plugin/.mcp.json }
pattern: '"tools"\s*:'
match: not_contains
---
