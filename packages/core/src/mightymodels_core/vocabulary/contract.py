"""The contract vocabulary: receipt outcomes, ticket phases and how a command was approved."""

from typing import Literal

type Outcome = Literal['pass', 'fail', 'timeout', 'not-found', 'refused', 'undecodable']


type Phase = Literal['planning', 'task', 'review', 'landing']

type ApprovalSource = Literal['form', 'fallback']
