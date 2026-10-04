# The "no matcher support" rows of the matcher table in the hooks reference.
MATCHERLESS_EVENTS = frozenset(
    {
        'UserPromptSubmit',
        'PostToolBatch',
        'Stop',
        'TeammateIdle',
        'TaskCreated',
        'TaskCompleted',
        'WorktreeCreate',
        'WorktreeRemove',
        'MessageDisplay',
        'CwdChanged',
    }
)

EVERY_TOOL_CALL_EVENTS = frozenset({'PreToolUse', 'PostToolUse'})

ENFORCEMENT_EVENTS = frozenset({'PreToolUse', 'PermissionRequest'})

# The events whose plain-text stdout Claude Code adds to Claude's context.
PLAIN_TEXT_CONTEXT_EVENTS = frozenset(
    {'UserPromptSubmit', 'UserPromptExpansion', 'SessionStart', 'PostModelSwitch'}
)

# The events whose exit-2 row in the hooks reference says the exit code is ignored or not honored.
EXIT_2_IGNORED_EVENTS = frozenset(
    {
        'PermissionRequest',
        'PermissionDenied',
        'Notification',
        'StopFailure',
        'Setup',
        'InstructionsLoaded',
        'MessageDisplay',
    }
)

DEFAULT_TIMEOUT_SECONDS = 600

LOWERED_DEFAULT_TIMEOUT_SECONDS = {
    'UserPromptSubmit': 30,
    'PreModelSwitch': 30,
    'PostModelSwitch': 30,
    'MessageDisplay': 10,
    'SessionEnd': 1.5,
}

SLOW_ENFORCEMENT_SECONDS = 10
