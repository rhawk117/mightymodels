"""Limits are overridden through PYTHON_HARNESS_DOCS_ environment variables."""

import pytest
from pydantic import ValidationError
from python_harness.documentation.settings import Settings


class TestEnvironmentOverride:
    @pytest.fixture
    def overridden(self, monkeypatch: pytest.MonkeyPatch) -> Settings:
        monkeypatch.setenv('PYTHON_HARNESS_DOCS_SUGGESTION_COUNT', '7')
        return Settings()

    def test_a_field_reads_its_prefixed_variable(self, overridden: Settings) -> None:
        assert overridden.suggestion_count == 7


class TestCapacityRules:
    @pytest.mark.parametrize(
        ('override', 'message'),
        [
            pytest.param(
                {'page_cache_bytes': 1},
                'page_cache_bytes must be at least download_max_bytes',
                id='page-cache-holds-a-download',
            ),
            pytest.param(
                {'section_cache_characters': 1},
                'section_cache_characters must be at least download_max_bytes',
                id='section-cache-holds-a-download',
            ),
            pytest.param(
                {'download_max_bytes': 1},
                'download_max_bytes must be at least download_chunk_bytes',
                id='download-holds-a-chunk',
            ),
            pytest.param(
                {'http_max_connections': 1},
                'http_max_connections must be at least http_max_keepalive_connections',
                id='connections-cover-keepalive',
            ),
        ],
    )
    def test_a_capacity_smaller_than_what_it_must_hold_is_rejected(
        self, override: dict[str, int], message: str
    ) -> None:
        with pytest.raises(ValidationError, match=message):
            Settings.model_validate(override)
