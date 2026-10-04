---
type: regex
target: { source: file, path: fixtures/plugin/PLAN.md }
pattern: '(?=[\s\S]*#### Phase 3: [^\n]*\n[\s\S]*?##### Session 3\.\d: agent `tflint-runner`)(?=[\s\S]*##### Session 4\.1)(?![\s\S]*##### Session 1\.)'
---
