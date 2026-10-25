from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True, kw_only=True, frozen=True)
class StartHarness:
    toplevel: Path
    subdirectory: Path
    data_directory: Path
    outside: Path
