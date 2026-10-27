"""The rulings a PreToolUse gate returns and the hook output that carries them."""

from dataclasses import dataclass

HOOK_EVENT = 'PreToolUse'
DENY = 'deny'
ASK = 'ask'


@dataclass(slots=True, kw_only=True, frozen=True)
class Denied:
    reason: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Asked:
    reason: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Unjudged:
    warning: str


type Ruling = Denied | Asked | Unjudged | None


def hook_output(ruling: Denied | Asked | Unjudged) -> dict[str, object]:
    if isinstance(ruling, Unjudged):
        return {'systemMessage': ruling.warning}

    return {
        'hookSpecificOutput': {
            'hookEventName': HOOK_EVENT,
            'permissionDecision': ASK if isinstance(ruling, Asked) else DENY,
            'permissionDecisionReason': ruling.reason,
        }
    }
