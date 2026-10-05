"""Pure helpers: gate inputs, child environments, output tails and git status entries."""

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from python_harness.gate.domain import GateInputs, GateOptions
from python_harness.survey.domain import ProjectManifest, ProjectSurvey

SEARCH_PATH = 'PATH'
VIRTUAL_ENV = 'VIRTUAL_ENV'
VIRTUALENV_SCRIPTS = 'Scripts' if sys.platform == 'win32' else 'bin'
UNTRACKED_STATUS_CODES = frozenset({'??', '!!'})


def list_declared_distributions(manifest: ProjectManifest | None) -> frozenset[str]:
    if manifest is None:
        return frozenset[str]()
    return manifest.declared_distributions


def gate_inputs_from(survey: ProjectSurvey) -> GateInputs:
    return GateInputs(
        declared_distributions=list_declared_distributions(survey.manifest),
        has_uv_lock=survey.layout.has_uv_lock,
        has_ruff_config=survey.ruff_config is not None,
        domains=frozenset(survey.domains),
        source_roots=survey.source_roots,
    )


def take_output_tail(output: bytes | bytearray, line_count: int) -> str:
    lines = output.decode('utf-8', errors='replace').splitlines()
    return '\n'.join(lines[max(len(lines) - line_count, 0) :])


def remove_search_path_entry(search_path: str, directory: Path) -> str:
    entries = search_path.split(os.pathsep)
    return os.pathsep.join(entry for entry in entries if Path(entry) != directory)


def build_child_environment(parent: Mapping[str, str], options: GateOptions) -> dict[str, str]:
    dropped = options.dropped_environment
    kept = {name: value for name, value in parent.items() if name not in dropped}
    virtual_env = parent.get(VIRTUAL_ENV)
    if virtual_env is not None and SEARCH_PATH in kept:
        scripts = Path(virtual_env, VIRTUALENV_SCRIPTS)
        kept[SEARCH_PATH] = remove_search_path_entry(kept[SEARCH_PATH], scripts)
    return kept | dict(options.child_environment)


def untracked_paths_from_status(status: str, prefix: str) -> frozenset[str]:
    entries = (entry for entry in status.split('\0') if entry)
    untracked = (entry[3:] for entry in entries if entry[:2] in UNTRACKED_STATUS_CODES)
    return frozenset(path.removeprefix(prefix) for path in untracked)
