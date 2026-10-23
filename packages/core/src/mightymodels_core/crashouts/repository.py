"""The seam under the crashout service: the journal of a repository's crashouts.

`journal` adds the crashout and returns its number, the count of the repository's crashouts
including this one. `latest_crashouts` returns the newest `JOURNAL_WINDOW.rows` crashouts, oldest
first, and says whether older ones were left out. `latest_crashout` returns the newest crashout, or
`None` when the journal is empty. Recording the root cause for similarity search is the service's
work, not the repository's.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from mightymodels_core.crashouts.records import CrashoutRecord
    from mightymodels_core.primitives import Latest


@runtime_checkable
class CrashoutRepository(Protocol):
    def latest_crashouts(self) -> Latest[CrashoutRecord]: ...

    def latest_crashout(self) -> CrashoutRecord | None: ...

    def journal(self, crashout: CrashoutRecord) -> int: ...
