---
type: regex
target: { source: file, path: fixtures/new/release-kit/plugin-plan.json }
pattern: '(?=[\s\S]*\bStop\b)(?=[\s\S]*stop_hook_active)(?=[\s\S]*every user)'
flags: i
---
