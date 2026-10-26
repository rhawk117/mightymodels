"""The harness over a real checkout and data directory that the pre-compact tests share."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.edge import PLUGIN_DATA_VARIABLE
from mightymodels_hooks.pre_compact import PreCompactHandler

from tests.hooks.dispatch.dispatch_builders import SLUG

if TYPE_CHECKING:
    import io
    from pathlib import Path

    from tests.hooks.dispatch.dispatch_builders import DispatchHarness

PRE_COMPACT_PAYLOAD_EVENT = 'PreCompact'


@dataclass(slots=True, kw_only=True, frozen=True)
class PreCompactHarness:
    dispatch: DispatchHarness
    stderr: io.StringIO

    @property
    def handoffs(self) -> Path:
        return self.dispatch.checkout.joinpath('.mightymodels', str(SLUG), 'handoffs')

    def handler(self) -> PreCompactHandler:
        environ = {PLUGIN_DATA_VARIABLE: str(self.dispatch.data_directory)}
        return PreCompactHandler(environ=environ, stderr=self.stderr)

    async def compact(self) -> str | None:
        payload = {
            'hook_event_name': PRE_COMPACT_PAYLOAD_EVENT,
            'cwd': str(self.dispatch.checkout),
        }
        return await self.handler().handle(payload)

    def written(self) -> list[str]:
        if not self.handoffs.is_dir():
            return []

        return sorted(entry.name for entry in self.handoffs.iterdir())
