type JsonObject = dict[str, object]
type Json = dict[str, Json] | list[Json] | str | int | float | bool | None


def as_object(value: object) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    return {key: item for key, item in value.items() if isinstance(key, str)}
