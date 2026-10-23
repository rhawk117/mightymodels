"""The crashout vocabulary: severities and verdicts."""

from typing import Literal

type CrashoutSeverity = Literal['mild-tilt', 'heated', 'crashout', 'full-meltdown']


type Verdict = Literal['deserved', 'split', 'unreasonable']
