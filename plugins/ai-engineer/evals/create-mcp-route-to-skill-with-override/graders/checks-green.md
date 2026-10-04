---
type: llm
focus: last_message
---

PASS if the final reply reports passing results for ruff, ty and pytest of the generated project and that the MCP config validator passed.

FAIL if any of the four is missing from the report or reported as failing without saying what was left undone.
