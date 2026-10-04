---
type: regex
target: { source: file, path: fixtures/new/release-kit/plugin-plan.json }
pattern: '(?=[\s\S]*release branches get cut without the changelog)(?=[\s\S]*the version bump is forgotten in pyproject)(?=[\s\S]*run the release workflow with the wrong tag)'
---
