"""Row and parameter Structs with the statement declarations that use them, by aggregate.

Each aggregate's Params (write, keyed by the parent) and Row (read, keyed by id or a join key)
Structs keep separate field lists on purpose. python.md allows no per-aggregate field base, and the
codec binds and decodes flat Structs, so a nested Struct would bind as one JSON parameter.
tests/core/schemas/unit/test_mirrored_fields.py guards the duplication: it fails when the shared
fields of a mirrored pair differ in name or type.
"""

from typing import TYPE_CHECKING

from . import (
    contract,
    crashouts,
    investigations,
    repositories,
    reviews,
    scout_reports,
    similarity,
    tasks,
    tickets,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration

DECLARATIONS: tuple[Declaration, ...] = (
    *repositories.DECLARATIONS,
    *tickets.DECLARATIONS,
    *investigations.DECLARATIONS,
    *tasks.DECLARATIONS,
    *contract.DECLARATIONS,
    *crashouts.DECLARATIONS,
    *reviews.DECLARATIONS,
    *similarity.DECLARATIONS,
    *scout_reports.DECLARATIONS,
)
