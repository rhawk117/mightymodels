"""Hook event payloads shaped like the JSON Claude Code writes to a hook's stdin."""

import json


def bash_payload(command: str, *, cwd: str = '/work/project') -> str:
    return json.dumps(
        {
            'session_id': 'session-1',
            'transcript_path': '/home/user/.claude/projects/demo/session-1.jsonl',
            'cwd': cwd,
            'permission_mode': 'default',
            'hook_event_name': 'PreToolUse',
            'tool_name': 'Bash',
            'tool_input': {'command': command, 'description': 'run it'},
            'tool_use_id': 'toolu_1',
        }
    )


def tool_payload(tool_name: str) -> str:
    return json.dumps(
        {
            'cwd': '/work/project',
            'hook_event_name': 'PreToolUse',
            'tool_name': tool_name,
            'tool_input': {'file_path': '/work/project/a.py'},
        }
    )


def session_payload(cwd: str, *, source: str = 'startup') -> str:
    return json.dumps(
        {
            'session_id': 'session-1',
            'transcript_path': '/home/user/.claude/projects/demo/session-1.jsonl',
            'cwd': cwd,
            'hook_event_name': 'SessionStart',
            'source': source,
            'model': 'claude-opus-5',
        }
    )
