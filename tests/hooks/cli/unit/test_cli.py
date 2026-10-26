import io
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_hooks.cli import REFUSED, HookCommand, HookRouter

if TYPE_CHECKING:
    from mightymodels_hooks.cli import HookPayload


@dataclass(slots=True, kw_only=True, frozen=True)
class EchoHandler:
    reply: str | None

    def handle(self, payload: HookPayload) -> str | None:
        return self.reply and f'{self.reply}:{sorted(payload)}'


@dataclass(slots=True, kw_only=True, frozen=True)
class Outcome:
    code: int
    stdout: str
    stderr: str


class TestHookCommand:
    router = HookRouter(
        handlers={'echo': EchoHandler(reply='ok'), 'quiet': EchoHandler(reply=None)}
    )

    def run_command(self, argv: list[str], stdin: str) -> Outcome:
        stdout, stderr = io.StringIO(), io.StringIO()
        command = HookCommand(
            router=self.router, stdin=io.StringIO(stdin), stdout=stdout, stderr=stderr
        )
        return Outcome(code=command.run(argv), stdout=stdout.getvalue(), stderr=stderr.getvalue())

    def test_registered_subcommand_receives_the_payload(self) -> None:
        outcome = self.run_command(['echo'], '{"a": 1}')
        assert (outcome.code, outcome.stdout) == (0, "ok:['a']")

    def test_handler_without_output_writes_nothing(self) -> None:
        outcome = self.run_command(['quiet'], '{}')
        assert (outcome.code, outcome.stdout) == (0, '')

    @pytest.mark.parametrize('argv', [['nope'], [], ['echo', 'extra']])
    def test_bad_subcommand_is_refused(self, argv: list[str]) -> None:
        outcome = self.run_command(argv, '{}')
        assert outcome.code == REFUSED
        assert outcome.stderr.startswith('mightymodels-hooks:')

    @pytest.mark.parametrize('stdin', ['', 'not json', '[1]', '"s"', 'null'])
    def test_non_object_stdin_is_refused(self, stdin: str) -> None:
        outcome = self.run_command(['echo'], stdin)
        assert outcome.code == REFUSED
        assert outcome.stdout == ''
