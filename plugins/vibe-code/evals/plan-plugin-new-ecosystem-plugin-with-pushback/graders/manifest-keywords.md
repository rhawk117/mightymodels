---
type: regex
target: { source: file, path: fixtures/new/tf-guard/.claude-plugin/plugin.json }
pattern: '(?=[\s\S]*"terraform")(?=[\s\S]*"iac")(?=[\s\S]*"sre")(?=[\s\S]*"plan-review")(?=[\s\S]*"fmt")'
---
