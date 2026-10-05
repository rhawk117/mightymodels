"""Whether every requested target path is a module the project discovered."""

from python_harness.calls.errors import UnknownTargetPathsError
from python_harness.imports.domain import ProjectIndex


def check_targets_known(
    index: ProjectIndex, target_paths: frozenset[str]
) -> UnknownTargetPathsError | None:
    parsed = frozenset(module.source.path for module in index.sources.modules)
    unparsable = frozenset(item.path for item in index.sources.unparsable)
    unknown = target_paths - parsed - unparsable
    if not unknown:
        return None
    return UnknownTargetPathsError(unknown)
