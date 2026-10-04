---
type: llm
focus: { source: file, path: fixtures/new/release-kit/plugin-plan.json }
---

The file is a plugin plan record for a release-process plugin named release-kit. The person said to keep every component as planned.

PASS if all of these hold:
- It has a skill cut-release that only a person can invoke, an agent release-verifier with Read and Bash limited to git and uv, and a hook on the Stop event that blocks finishing while the changelog is missing.
- Any advice given about a component's mechanism is recorded beside the decision "as planned", and no component was switched or dropped.
- There is no MCP server, rule or command component.

FAIL if a component the person asked for is missing or was changed to another mechanism.
