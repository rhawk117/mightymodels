"""Route a hook's JSON stdin to the subcommand handler registered for it."""

import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, Self, TextIO, runtime_checkable

import msgspec
from mightymodels_core.edge import create_clock

from mightymodels_hooks.completion_gate import CompletionGateHandler
from mightymodels_hooks.dispatch import DispatchHandler
from mightymodels_hooks.main_thread import MainThreadHandler
from mightymodels_hooks.pre_compact import PreCompactHandler
from mightymodels_hooks.scout_reports import (
    ScoutReportKeeper,
    SubagentHandbackHandler,
    SubagentRecordHandler,
)
from mightymodels_hooks.session_pointer import SessionPointerHandler
from mightymodels_hooks.session_start import SessionStartHandler

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

REFUSED = 2

type HookPayload = dict[str, object]


@runtime_checkable
class HookHandler(Protocol):
    async def handle(self, payload: HookPayload) -> str | None: ...


type HookHandlers = dict[str, HookHandler]


@dataclass(slots=True, kw_only=True, frozen=True)
class HookRouter:
    handlers: HookHandlers = field(default_factory=dict)

    def mount(self, handlers: HookHandlers) -> Self:
        self.handlers.update(handlers)
        return self

    def find_handler(self, name: str) -> HookHandler | None:
        return self.handlers.get(name)


def decode_payload(text: str) -> HookPayload | None:
    decoder = msgspec.json.Decoder[dict[str, object]](dict[str, object])
    try:
        return decoder.decode(text)
    except msgspec.DecodeError:
        return None


def create_hook_router(environ: Mapping[str, str], stderr: TextIO) -> HookRouter:
    session_start = SessionStartHandler(environ=environ, stderr=stderr, clock=create_clock())
    dispatch = DispatchHandler(environ=environ)
    main_thread = MainThreadHandler(environ=environ)
    completion_gate = CompletionGateHandler(environ=environ, stderr=stderr)
    keeper = ScoutReportKeeper(environ=environ, stderr=stderr, clock=create_clock())
    return HookRouter().mount({
        'session-start': session_start,
        'dispatch-hook': dispatch,
        'main-thread-hook': main_thread,
        'completion-gate': completion_gate,
        'pre-compact': PreCompactHandler(environ=environ, stderr=stderr),
        'subagent-record': SubagentRecordHandler(keeper=keeper),
        'subagent-handback': SubagentHandbackHandler(keeper=keeper),
        'session-pointer': SessionPointerHandler(
            environ=environ, stderr=stderr, clock=create_clock()
        ),
    })


@dataclass(slots=True, kw_only=True, frozen=True)
class HookCommand:
    router: HookRouter
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO

    def refuse(self, message: str) -> int:
        self.stderr.write(f'mightymodels-hooks: {message}\n')
        return REFUSED

    async def run(self, argv: Sequence[str]) -> int:
        if len(argv) != 1:
            return self.refuse('expected exactly one subcommand')

        handler = self.router.find_handler(argv[0])
        if handler is None:
            return self.refuse(f'unknown subcommand {argv[0]!r}')

        payload = decode_payload(self.stdin.read())
        if payload is None:
            return self.refuse('stdin is not a JSON object')

        output = await handler.handle(payload)
        if output is not None:
            self.stdout.write(output)

        return 0


def main() -> int:
    command = HookCommand(
        router=create_hook_router(os.environ, sys.stderr),
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    return asyncio.run(command.run(sys.argv[1:]))
