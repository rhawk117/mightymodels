"""The unit-of-work fast paths against state opened through open_state."""

from tests.core.units_of_work.units_of_work_suite import UnitsOfWorkFastPaths


class TestUnitsOfWorkFastPaths(UnitsOfWorkFastPaths):
    """The six fast paths over a database opened on a git checkout."""
