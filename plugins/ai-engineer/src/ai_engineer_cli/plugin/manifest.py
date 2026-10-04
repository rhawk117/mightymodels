import msgspec

from ai_engineer_cli.plugin.record import Plan


def manifest_document(plan: Plan) -> dict[str, object]:
    """The `plugin.json` fields the record sets; `author`, `license` and the rest only when set."""
    manifest: dict[str, object] = {
        'name': plan.name,
        'version': plan.version,
        'description': plan.description,
        'keywords': plan.keywords,
    }
    optional = {
        'author': plan.author,
        'license': plan.license,
        'homepage': plan.homepage,
        'repository': plan.repository,
        'userConfig': plan.user_config,
        'dependencies': plan.dependencies,
    }
    manifest.update({key: msgspec.to_builtins(value) for key, value in optional.items() if value})
    return manifest


def manifest_text(plan: Plan) -> str:
    return json_text(manifest_document(plan))


def json_text(document: object) -> str:
    return msgspec.json.format(msgspec.json.encode(document), indent=2).decode() + '\n'
