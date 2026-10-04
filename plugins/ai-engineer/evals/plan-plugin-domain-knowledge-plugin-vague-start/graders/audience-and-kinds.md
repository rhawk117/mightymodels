---
type: regex
target: { source: file, path: fixtures/new/release-kit/plugin-plan.json }
pattern: '(?=[\s\S]*"how"\s*:\s*"org")(?=[\s\S]*"kinds"\s*:\s*\[[^\]]*"domain")(?=[\s\S]*"kinds"\s*:\s*\[[^\]]*"workflow")'
---
