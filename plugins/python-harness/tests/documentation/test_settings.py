"""Limits are overridden through PYTHON_HARNESS_DOCS_ environment variables."""

import pytest
from python_harness.documentation.settings import Settings


class TestEnvironmentOverride:
    @pytest.fixture
    def overridden(self, monkeypatch: pytest.MonkeyPatch) -> Settings:
        monkeypatch.setenv('PYTHON_HARNESS_DOCS_SUGGESTION_COUNT', '7')
        return Settings()

    def test_a_field_reads_its_prefixed_variable(self, overridden: Settings) -> None:
        assert overridden.suggestion_count == 7
