---
type: llm
focus: trace
---

The person asked for an MCP server that only wraps ruff check and pytest. Judge only what the assistant itself wrote to the person, not the text of any skill or file it loaded.

PASS if, before building, the assistant said plainly that ruff and pytest are shell commands Claude can already run, and that a skill whose frontmatter pre-approves the commands (for example allowed-tools with Bash(uv *), built with create-skill) is the cheaper mechanism.

FAIL if it built the server without saying so, or if it only copied the skill's routing text without addressing this request.
