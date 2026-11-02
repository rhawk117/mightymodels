"""The rulings a PreToolUse gate returns and the hook output that carries them."""

from dataclasses import dataclass

HOOK_EVENT = 'PreToolUse'
DENY = 'deny'


@dataclass(slots=True, kw_only=True, frozen=True)
class Denied:
    reason: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Unjudged:
    warning: str


type Ruling = Denied | Unjudged | None


def hook_output(ruling: Denied | Unjudged) -> dict[str, object]:
    if isinstance(ruling, Unjudged):
        return {'systemMessage': ruling.warning}

    return {
        'hookSpecificOutput': {
            'hookEventName': HOOK_EVENT,
            'permissionDecision': DENY,
            'permissionDecisionReason': ruling.reason,
        }
    }
