"""Route a hook's JSON stdin to the subcommand handler registered for it."""

import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, Self, TextIO

import msgspec
from mightymodels_core.edge import create_clock

from mightymodels_hooks.ask_recorder import AskRecorderHandler
from mightymodels_hooks.completion_gate import CompletionGateHandler, create_implementers
from mightymodels_hooks.dispatch import DispatchHandler, create_dispatch_rules
from mightymodels_hooks.main_thread import MainThreadHandler
from mightymodels_hooks.payloads import (
    PostToolUsePayload,
    PreCompactPayload,
    PreToolUsePayload,
    SessionStartPayload,
    SubagentStopPayload,
)
from mightymodels_hooks.pre_compact import PreCompactHandler
from mightymodels_hooks.scout_reports import (
    ScoutReportKeeper,
    SubagentHandbackHandler,
    SubagentRecordHandler,
    create_scouts,
)
from mightymodels_hooks.session_pointer import SessionPointerHandler, create_pointer_fields
from mightymodels_hooks.session_start import SessionStartHandler

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

REFUSED = 2

type HookPayload = dict[str, object]


class PayloadHandler[Payload](Protocol):
    async def handle(self, payload: Payload) -> str | None: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class Delivery:
    output: str | None


class HookRoute(Protocol):
    async def deliver(self, text: str) -> Delivery | msgspec.DecodeError: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class PayloadRoute[Payload]:
    """A handler with the payload type its stdin decodes into."""

    payload_type: type[Payload]
    handler: PayloadHandler[Payload]

    async def deliver(self, text: str) -> Delivery | msgspec.DecodeError:
        try:
            payload = msgspec.json.decode(text, type=self.payload_type)
        except msgspec.DecodeError as error:
            return error

        return Delivery(output=await self.handler.handle(payload))


def route_dict(handler: PayloadHandler[HookPayload]) -> PayloadRoute[HookPayload]:
    return PayloadRoute(payload_type=dict[str, object], handler=handler)


type HookHandlers = dict[str, HookRoute]


@dataclass(slots=True, kw_only=True, frozen=True)
class HookRouter:
    handlers: HookHandlers = field(default_factory=dict)

    def mount(self, handlers: HookHandlers) -> Self:
        self.handlers.update(handlers)
        return self

    def find_handler(self, name: str) -> HookRoute | None:
        return self.handlers.get(name)


def create_hook_router(environ: Mapping[str, str], stderr: TextIO) -> HookRouter:
    session_start = SessionStartHandler(environ=environ, stderr=stderr, clock=create_clock())
    dispatch = DispatchHandler(environ=environ, rules=create_dispatch_rules())
    main_thread = MainThreadHandler(environ=environ)
    completion_gate = CompletionGateHandler(
        environ=environ, stderr=stderr, implementers=create_implementers()
    )
    keeper = ScoutReportKeeper(
        environ=environ, stderr=stderr, clock=create_clock(), scouts=create_scouts()
    )
    return HookRouter().mount({
        'session-start': PayloadRoute(payload_type=SessionStartPayload, handler=session_start),
        'dispatch-hook': PayloadRoute(payload_type=PreToolUsePayload, handler=dispatch),
        'main-thread-hook': PayloadRoute(payload_type=PreToolUsePayload, handler=main_thread),
        'completion-gate': PayloadRoute(payload_type=SubagentStopPayload, handler=completion_gate),
        'pre-compact': PayloadRoute(
            payload_type=PreCompactPayload,
            handler=PreCompactHandler(environ=environ, stderr=stderr),
        ),
        'subagent-record': PayloadRoute(
            payload_type=SubagentStopPayload, handler=SubagentRecordHandler(keeper=keeper)
        ),
        'subagent-handback': PayloadRoute(
            payload_type=PostToolUsePayload, handler=SubagentHandbackHandler(keeper=keeper)
        ),
        'session-pointer': PayloadRoute(
            payload_type=PostToolUsePayload,
            handler=SessionPointerHandler(
                environ=environ,
                stderr=stderr,
                clock=create_clock(),
                fields=create_pointer_fields(),
            ),
        ),
        'ask-recorder': PayloadRoute(
            payload_type=PostToolUsePayload,
            handler=AskRecorderHandler(environ=environ, stderr=stderr, clock=create_clock()),
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

        route = self.router.find_handler(argv[0])
        if route is None:
            return self.refuse(f'unknown subcommand {argv[0]!r}')

        delivery = await route.deliver(self.stdin.read())
        if isinstance(delivery, msgspec.DecodeError):
            return self.refuse(f'stdin is not a valid hook payload: {delivery}')

        if delivery.output is not None:
            self.stdout.write(delivery.output)

        return 0


def main() -> int:
    command = HookCommand(
        router=create_hook_router(os.environ, sys.stderr),
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    return asyncio.run(command.run(sys.argv[1:]))
