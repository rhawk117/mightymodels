"""The heartbeat interval of contract_run, taken from the server's environment.

The default is the run options' own. A value that is not a finite number above zero is an error
that names the variable and the value, never a silent fallback.
"""

import math
from typing import TYPE_CHECKING

from mightymodels_core.contract.runs import RunOptions
from mightymodels_core.primitives.errors import StateError

if TYPE_CHECKING:
    from collections.abc import Mapping

HEARTBEAT_VARIABLE = 'MIGHTYMODELS_CONTRACT_HEARTBEAT_SECONDS'


class InvalidHeartbeatError(StateError):
    def __init__(self, *, given: str) -> None:
        self.given = given
        super().__init__(
            f'{HEARTBEAT_VARIABLE} is {given!r}; it must be a finite number above zero'
        )


def parse_run_options(environ: Mapping[str, str]) -> RunOptions | InvalidHeartbeatError:
    given = environ.get(HEARTBEAT_VARIABLE)
    if given is None:
        return RunOptions()

    try:
        seconds = float(given)
    except ValueError:
        return InvalidHeartbeatError(given=given)

    if not math.isfinite(seconds) or seconds <= 0:
        return InvalidHeartbeatError(given=given)

    return RunOptions(heartbeat_seconds=seconds)
