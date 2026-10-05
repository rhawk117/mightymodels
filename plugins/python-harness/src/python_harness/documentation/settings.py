"""Tunable limits for retrieval, caching, and matching; overridable per environment."""

from typing import Annotated, NamedTuple, Self

from pydantic import (
    AllowInfNan,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from python_harness.documentation.errors import CapacityError

type PositiveSeconds = Annotated[PositiveFloat, AllowInfNan(allow_inf_nan=False)]
type NonNegativeSeconds = Annotated[NonNegativeFloat, AllowInfNan(allow_inf_nan=False)]
type CacheTTL = Annotated[PositiveSeconds, Field(le=24 * 60 * 60)]
type MatchScore = Annotated[float, Field(ge=0, le=100)]
type Ratio = Annotated[float, Field(ge=0, le=1)]


class CapacityRule(NamedTuple):
    larger: str
    smaller: str


CAPACITY_RULES = (
    CapacityRule('page_cache_bytes', 'download_max_bytes'),
    CapacityRule('section_cache_characters', 'download_max_bytes'),
    CapacityRule('download_max_bytes', 'download_chunk_bytes'),
    CapacityRule('http_max_connections', 'http_max_keepalive_connections'),
)


class Settings(BaseSettings):
    """Environment overrides use PYTHON_HARNESS_DOCS_<FIELD_NAME>; sizes are bytes."""

    model_config = SettingsConfigDict(
        env_prefix='PYTHON_HARNESS_DOCS_', frozen=True, extra='forbid'
    )

    download_max_bytes: PositiveInt = 8 * pow(1024, 2)
    inventory_max_bytes: PositiveInt = 16 * pow(1024, 2)
    inventory_max_entries: PositiveInt = 100_000
    max_malformed_entry_ratio: Ratio = 0.02
    indexed_sections: tuple[str, ...] = ('library', 'builtins', 'reference')
    download_chunk_bytes: PositiveInt = 64 * 1024
    inventory_cache_versions: PositiveInt = 8
    page_cache_bytes: PositiveInt = 32 * pow(1024, 2)
    section_cache_characters: PositiveInt = 16 * pow(1024, 2)
    cache_ttl_seconds: CacheTTL = 24 * 60 * 60
    missing_version_ttl_seconds: CacheTTL = 5 * 60
    fuzzy_score_cutoff: MatchScore = 80
    suggestion_count: PositiveInt = 3
    download_concurrency: PositiveInt = 4
    parse_concurrency: PositiveInt = 2
    request_timeout_seconds: PositiveSeconds = 20
    connect_timeout_seconds: PositiveSeconds = 5
    fill_timeout_seconds: PositiveSeconds = 40
    call_timeout_seconds: PositiveSeconds = 45
    shutdown_timeout_seconds: PositiveSeconds = 5
    http_max_connections: PositiveInt = 4
    http_max_keepalive_connections: NonNegativeInt = 4
    http_keepalive_expiry_seconds: NonNegativeSeconds = 5
    pool_timeout_seconds: PositiveSeconds = 5

    @model_validator(mode='after')
    def validate_capacity(self) -> Self:
        if (broken := next(filter(self.breaks, CAPACITY_RULES), None)) is not None:
            raise CapacityError(broken.larger, broken.smaller)
        return self

    def breaks(self, rule: CapacityRule) -> bool:
        return int(getattr(self, rule.larger)) < int(getattr(self, rule.smaller))
