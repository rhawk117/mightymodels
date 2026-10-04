---
type: regex
target: { source: file, path: fixtures/plugin/plugin-plan.json }
pattern: '(?=[\s\S]*"name"\s*:\s*"tflint-runner")(?=[\s\S]*"builder"\s*:\s*"create-subagent")'
---
