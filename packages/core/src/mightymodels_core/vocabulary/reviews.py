"""The review vocabulary: scopes, depths, emphases, severities, decisions and results."""

from typing import Literal

type Scope = Literal['diff', 'branch', 'ticket', 'codebase']


type Depth = Literal['quick', 'standard', 'deep']


type Emphasis = Literal['release-readiness', 'maintainability', 'balanced', 'custom']


type FindingSeverity = Literal['Blocker', 'Critical', 'High', 'Medium', 'Low']


type FindingKind = Literal['defect', 'quality']


type EvidenceKind = Literal['metric', 'idiom', 'convention']


type Decision = Literal['fix', 'defer', 'accept-risk', 'dismiss']


type Result = Literal['fixed', 'failed', 'blocked']
