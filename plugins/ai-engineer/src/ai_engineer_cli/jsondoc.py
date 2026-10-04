import json
from collections import Counter

type JsonObject = dict[str, object]
type Json = dict[str, Json] | list[Json] | str | int | float | bool | None


def as_object(value: object) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    return {key: item for key, item in value.items() if isinstance(key, str)}


def duplicate_keys(text: str) -> tuple[str, ...]:
    """The keys that repeat inside one JSON object of text, which msgspec reads without a word.

    Text that is not valid JSON gives no keys; decode it with msgspec first to learn that.
    """
    duplicates: list[str] = []

    def collect(pairs: list[tuple[str, object]]) -> JsonObject:
        counts = Counter(key for key, _ in pairs)
        duplicates.extend(key for key, count in counts.items() if count > 1)
        return dict(pairs)

    try:
        json.JSONDecoder(object_pairs_hook=collect).decode(text)
    except ValueError:
        return ()
    return tuple(duplicates)
