"""Row and parameter Structs with the statement declarations that use them, by aggregate."""

from typing import TYPE_CHECKING

from . import contract, crashouts, investigations, repositories, tasks, tickets

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration

DECLARATIONS: tuple[Declaration, ...] = (
    *repositories.DECLARATIONS,
    *tickets.DECLARATIONS,
    *investigations.DECLARATIONS,
    *tasks.DECLARATIONS,
    *contract.DECLARATIONS,
    *crashouts.DECLARATIONS,
)
