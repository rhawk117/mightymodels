"""The contract vocabulary: receipt outcomes and ticket phases."""

from typing import Literal

type Outcome = Literal['pass', 'fail', 'timeout', 'not-found', 'refused', 'undecodable']


type Phase = Literal['planning', 'task', 'review', 'landing']
