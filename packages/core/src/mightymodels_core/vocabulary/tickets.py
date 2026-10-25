"""The ticket vocabulary: statuses and scopes."""

from typing import Literal

type TicketStatus = Literal['staged', 'in-progress', 'closed']


type TicketScope = Literal['sm', 'med', 'large']
