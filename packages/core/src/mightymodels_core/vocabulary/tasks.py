"""The task vocabulary: statuses, workers and architect modes."""

from typing import Literal

type TaskStatus = Literal['pending', 'in-progress', 'verified', 'failed', 'blocked', 'superseded']


type Worker = Literal['engineer', 'architect', 'intern']


type ArchitectMode = Literal['recovery-implementation', 'systemic-refactor', 'diagnose-replan']
