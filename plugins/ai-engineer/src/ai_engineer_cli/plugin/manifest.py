import msgspec

from ai_engineer_cli.plugin.record import Plan

MODELLED_KEYS = (
    'name',
    'version',
    'description',
    'keywords',
    'author',
    'license',
    'homepage',
    'repository',
    'userConfig',
    'dependencies',
)
ALWAYS_WRITTEN = 4


def manifest_document(plan: Plan) -> dict[str, object]:
    """The `plugin.json` fields the record sets; `author`, `license` and the rest only when set."""
    values = (
        plan.name,
        plan.version,
        plan.description,
        plan.keywords,
        plan.author,
        plan.license,
        plan.homepage,
        plan.repository,
        plan.user_config,
        plan.dependencies,
    )
    return {
        key: msgspec.to_builtins(value)
        for position, (key, value) in enumerate(zip(MODELLED_KEYS, values, strict=True))
        if position < ALWAYS_WRITTEN or value
    }


def merged_manifest_text(plan: Plan, existing: dict[str, object]) -> str:
    """The record's keys, then every key of the existing manifest the record does not model."""
    kept = {key: value for key, value in existing.items() if key not in MODELLED_KEYS}
    return json_text({**manifest_document(plan), **kept})


def manifest_text(plan: Plan) -> str:
    return json_text(manifest_document(plan))


def json_text(document: object) -> str:
    return msgspec.json.format(msgspec.json.encode(document), indent=2).decode() + '\n'
