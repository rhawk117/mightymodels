from mightymodels_core.edge import create_clock, create_database_spec
from mightymodels_core.primitives import SystemClock


class TestFactories:
    def test_the_clock_is_the_system_clock(self) -> None:
        assert isinstance(create_clock(), SystemClock)

    def test_the_spec_names_the_packaged_sql(self) -> None:
        spec = create_database_spec()

        assert spec.schema.is_file()
        assert spec.statements.is_file()
        assert spec.declarations
