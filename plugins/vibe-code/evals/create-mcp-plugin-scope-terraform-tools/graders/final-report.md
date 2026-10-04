---
type: llm
focus: last_message
---

The final reply is the hand-off for a plugin-scope MCP server named tf-inspect with two read-only tools.

PASS if all of these hold:
- It reports the outcome of ruff, ty and pytest for the generated project (results or counts, not only the commands).
- It reports that the MCP config validator passed for the plugin `.mcp.json`.
- Where it speaks about the directory the server starts in, it says that is not documented or that the root comes from CLAUDE_PROJECT_DIR.

FAIL if it states as fact that a plugin server starts in the plugin root, or if it asks the person to run a manual elicitation check although no tool pauses to ask.
