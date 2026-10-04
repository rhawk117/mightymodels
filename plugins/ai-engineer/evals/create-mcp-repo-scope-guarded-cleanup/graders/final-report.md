---
type: llm
focus: last_message
---

The final reply is the hand-off for a project-scope MCP server named repo-janitor that serves stdio and HTTP and has one confirming, destructive tool.

PASS if all of these hold:
- It reports the outcome of ruff, ty and pytest for the generated project (results or counts, not only the commands).
- It reports that the MCP config validator passed for the project `.mcp.json`.
- It asks the person to check the confirmation of remove_junk by hand in an interactive Claude Code session.
- It says that Claude Code asks each person to approve a server from a project `.mcp.json` in an interactive session.

FAIL if any of these is missing, or if it says the confirmation was proven in a real Claude Code session when only the in-process tests ran.
