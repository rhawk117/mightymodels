"""Keeping the state directory out of the repository's own tracking."""

from typing import TYPE_CHECKING

from .paths import STATE_DIRECTORY

if TYPE_CHECKING:
    from pathlib import Path

EXCLUDE_LINE = f'{STATE_DIRECTORY}/'


def exclude_state(common_directory: Path) -> None:
    exclude = common_directory.joinpath('info', 'exclude')
    current = exclude.read_text(encoding='utf-8') if exclude.is_file() else ''
    if EXCLUDE_LINE in current.splitlines():
        return

    exclude.parent.mkdir(parents=True, exist_ok=True)
    separator = '' if not current or current.endswith('\n') else '\n'
    exclude.write_text(f'{current}{separator}{EXCLUDE_LINE}\n', encoding='utf-8')
