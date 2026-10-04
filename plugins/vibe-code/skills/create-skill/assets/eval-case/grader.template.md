---
type: llm
# weight: 1
# arm: with-only
# focus: last_message
#
# Other types, one per file; replace the keys above with the keys for the type:
#   type: regex        pattern: REGEX  flags: i  match: not_contains  target: last_message
#   type: tool_used    tool: Skill  input_match: '"skill"\s*:\s*"(?:[\w-]+:)?NAME"'  min: 1  max: 3
#   type: tool_order   before: Read  after: Edit
#   type: file_exists  path: GLOB  exists: true
#
# regex target and llm focus: last_message, trace, files, mock_calls,
# or { source: file, path: PATH } for the contents of one produced file.
---

PASS if WHAT_A_CORRECT_RESPONSE_CONTAINS.
FAIL if WHAT_A_WRONG_OR_MISSING_RESPONSE_LOOKS_LIKE.
