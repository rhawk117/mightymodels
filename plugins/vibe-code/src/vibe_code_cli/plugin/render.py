from pathlib import Path

import msgspec

from vibe_code_cli.jsondoc import as_object
from vibe_code_cli.plugin.layout import MANIFEST_PATH, planned_directories
from vibe_code_cli.plugin.manifest import json_text, manifest_text, merged_manifest_text
from vibe_code_cli.plugin.plan_md import render_plan_md, render_readme
from vibe_code_cli.plugin.record import Plan


class RenderRefusedError(Exception):
    """The target cannot take the plugin shell; nothing was written."""


def plan_files(plan: Plan, root: Path) -> dict[str, str]:
    return {
        MANIFEST_PATH: manifest_text(plan),
        'README.md': render_readme(plan),
        'PLAN.md': render_plan_md(plan, str(root)),
        'plugin-plan.json': json_text(msgspec.to_builtins(plan)),
    }


def inside(root: Path, relative: str) -> Path:
    """The path under root, resolved, or a refusal when it leaves root."""
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        message = f'{relative} resolves outside {root}'
        raise RenderRefusedError(message)
    return path


def forced_manifest_text(plan: Plan, manifest: Path) -> str:
    """The manifest text to write over an existing one; a refusal when that is not a JSON object."""
    try:
        existing = as_object(msgspec.json.decode(manifest.read_bytes()))
    except msgspec.DecodeError:
        existing = None
    if existing is None:
        message = f'{manifest} is not a JSON object; fix or remove it before --force'
        raise RenderRefusedError(message)
    return merged_manifest_text(plan, existing)


def render(plan: Plan, target: Path, *, force: bool) -> list[str]:
    """Write the four plan files and the planned directories under target; return their paths.

    Every path is resolved inside target before the first write, and nothing is deleted.
    Over an existing manifest, keys the record does not model are kept.
    """
    root = target.resolve()
    if root.exists() and not root.is_dir():
        message = f'{target} is not a directory'
        raise RenderRefusedError(message)
    files = {inside(root, name): text for name, text in plan_files(plan, root).items()}
    directories = [inside(root, name) for name in planned_directories(plan)]
    manifest = inside(root, MANIFEST_PATH)
    if manifest.exists() and not force:
        message = f'{target / MANIFEST_PATH} exists; pass --force to rewrite the plan files'
        raise RenderRefusedError(message)
    if manifest.exists():
        files[manifest] = forced_manifest_text(plan, manifest)
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    return [str(path.relative_to(root)) for path in [*files, *directories]]
