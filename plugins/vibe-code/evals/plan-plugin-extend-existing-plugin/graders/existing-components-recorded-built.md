---
type: regex
target: { source: file, path: fixtures/plugin/plugin-plan.json }
pattern: '(?=[\s\S]*tf-plan)(?=[\s\S]*tf-refactor)(?=[\s\S]*"name"\s*:\s*"tflint")(?=[\s\S]*"status"\s*:\s*"built")'
---
