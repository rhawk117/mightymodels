---
type: regex
target: { source: file, path: fixtures/repo/.mcp.json }
pattern: '(?=[\s\S]*"type"\s*:\s*"stdio")(?=[\s\S]*"timeout"\s*:\s*\d{5,})[\s\S]*mcp/repo-janitor'
---
