from dataclasses import dataclass, field
from enum import StrEnum

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

PLAIN_TEXT_CONTEXT_EVENTS = frozenset(
    {'UserPromptSubmit', 'UserPromptExpansion', 'SessionStart', 'PostModelSwitch'}
)

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


class LoweredTimeoutEvent(StrEnum):
    USER_PROMPT_SUBMIT = 'UserPromptSubmit'
    PRE_MODEL_SWITCH = 'PreModelSwitch'
    POST_MODEL_SWITCH = 'PostModelSwitch'
    MESSAGE_DISPLAY = 'MessageDisplay'
    SESSION_END = 'SessionEnd'


def lowered_timeouts() -> dict[str, float]:
    return {
        LoweredTimeoutEvent.USER_PROMPT_SUBMIT: 30,
        LoweredTimeoutEvent.PRE_MODEL_SWITCH: 30,
        LoweredTimeoutEvent.POST_MODEL_SWITCH: 30,
        LoweredTimeoutEvent.MESSAGE_DISPLAY: 10,
        LoweredTimeoutEvent.SESSION_END: 1.5,
    }


@dataclass(slots=True, kw_only=True, frozen=True)
class TimeoutDefaults:
    lowered: dict[str, float] = field(default_factory=lowered_timeouts)


SLOW_ENFORCEMENT_SECONDS = 10
