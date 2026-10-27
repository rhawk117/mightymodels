import io
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_hooks.cli import (
    REFUSED,
    HookCommand,
    HookRouter,
    PayloadRoute,
    create_hook_router,
    route_dict,
)
from mightymodels_hooks.payloads import SessionStartPayload

if TYPE_CHECKING:
    from mightymodels_hooks.cli import HookPayload


@dataclass(slots=True, kw_only=True, frozen=True)
class EchoHandler:
    reply: str | None

    async def handle(self, payload: HookPayload) -> str | None:
        return self.reply and f'{self.reply}:{sorted(payload)}'


@dataclass(slots=True, kw_only=True, frozen=True)
class CwdHandler:
    async def handle(self, payload: SessionStartPayload) -> str | None:
        return f'cwd={payload.cwd}'


@dataclass(slots=True, kw_only=True, frozen=True)
class Outcome:
    code: int
    stdout: str
    stderr: str


class TestHookCommand:
    router = HookRouter(
        handlers={
            'echo': route_dict(EchoHandler(reply='ok')),
            'quiet': route_dict(EchoHandler(reply=None)),
            'start': PayloadRoute(payload_type=SessionStartPayload, handler=CwdHandler()),
        }
    )

    async def run_command(self, argv: list[str], stdin: str) -> Outcome:
        stdout, stderr = io.StringIO(), io.StringIO()
        command = HookCommand(
            router=self.router, stdin=io.StringIO(stdin), stdout=stdout, stderr=stderr
        )
        return Outcome(
            code=await command.run(argv), stdout=stdout.getvalue(), stderr=stderr.getvalue()
        )

    async def test_registered_subcommand_receives_the_payload(self) -> None:
        outcome = await self.run_command(['echo'], '{"a": 1}')
        assert (outcome.code, outcome.stdout) == (0, "ok:['a']")

    async def test_handler_without_output_writes_nothing(self) -> None:
        outcome = await self.run_command(['quiet'], '{}')
        assert (outcome.code, outcome.stdout) == (0, '')

    @pytest.mark.parametrize('argv', [['nope'], [], ['echo', 'extra']])
    async def test_bad_subcommand_is_refused(self, argv: list[str]) -> None:
        outcome = await self.run_command(argv, '{}')
        assert outcome.code == REFUSED
        assert outcome.stderr.startswith('mightymodels-hooks:')

    @pytest.mark.parametrize('stdin', ['', 'not json', '[1]', '"s"', 'null'])
    async def test_non_object_stdin_is_refused(self, stdin: str) -> None:
        outcome = await self.run_command(['echo'], stdin)
        assert outcome.code == REFUSED
        assert outcome.stdout == ''

    async def test_typed_subcommand_receives_its_struct(self) -> None:
        stdin = '{"hook_event_name": "SessionStart", "cwd": "/work", "extra": 1}'
        outcome = await self.run_command(['start'], stdin)
        assert (outcome.code, outcome.stdout) == (0, 'cwd=/work')

    @pytest.mark.parametrize(
        'stdin',
        [
            '{"hook_event_name": "PreCompact"}',
            '{"hook_event_name": "SessionStart", "cwd": 7}',
        ],
    )
    async def test_payload_that_does_not_decode_is_refused(self, stdin: str) -> None:
        outcome = await self.run_command(['start'], stdin)
        assert outcome.code == REFUSED
        assert outcome.stdout == ''
        assert outcome.stderr.startswith('mightymodels-hooks: ')
        assert outcome.stderr.count('\n') == 1


class TestHookRouter:
    def test_session_start_is_mounted(self) -> None:
        router = create_hook_router({}, io.StringIO())
        assert router.find_handler('session-start') is not None
