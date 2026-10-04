---
type: regex
target: { source: file, path: fixtures/new/tf-guard/PLAN.md }
pattern: '#### Phase 1: [^\n]*\n[\s\S]*?##### Session 1\.\d: hook[\s\S]*#### Phase 3: [^\n]*\n[\s\S]*?##### Session 3\.\d: skill[\s\S]*#### Phase 4: '
---
