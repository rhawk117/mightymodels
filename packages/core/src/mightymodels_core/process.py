"""Child processes: the one place the plugin launches them, and what a launch returns.

`ProcessRunner.run` is awaited under any anyio backend. It runs an argument vector without
a shell, with standard input at end of file, and waits at most `timeout` seconds, which
every caller has to name. It returns a `CompletedRun`, or a `FailedRun` whose `kind` says
which of four things happened: the wait ran out, the executable is missing, the system
refused the launch, or the output is not text in the default encoding. None of the four
leaves `run` as an exception, and `detail` carries the cause in words. A program, an
argument or a working directory that holds a NUL is a refused launch too, and so is a
working directory that does not exist. A caller that cancels the run gets its own
cancellation back, and the child is killed either way.

A finished run is decoded as `text=True` decodes it. What a timed-out run printed before
it was killed is decoded with the same encoding and the same newline handling, except
that bytes which are not text are replaced: the kill can cut a character in half, and a
timeout stays a timeout.
"""

import io
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

import anyio

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from anyio.abc import ByteReceiveStream, Process


class FailureKind(StrEnum):
    TIMED_OUT = auto()
    NOT_FOUND = auto()
    REFUSED = auto()
    UNDECODABLE = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class CompletedRun:
    exit: int
    stdout: str
    stderr: str


@dataclass(slots=True, kw_only=True, frozen=True)
class FailedRun:
    kind: FailureKind
    detail: str
    stdout: str
    stderr: str


type RunOutcome = CompletedRun | FailedRun
type LaunchError = OSError | ValueError
type DecodeErrors = Literal['strict', 'replace']


@runtime_checkable
class ProcessRunner(Protocol):
    async def run(
        self, argv: Sequence[str], *, timeout: float, cwd: Path | None = None
    ) -> RunOutcome: ...


def captured_text(captured: bytearray, *, errors: DecodeErrors) -> str:
    encoding = io.text_encoding(None)
    return io.TextIOWrapper(io.BytesIO(captured), encoding=encoding, errors=errors).read()


def failed_run(error: LaunchError, *, program: str) -> FailedRun:
    missing = isinstance(error, FileNotFoundError) and error.filename == program
    kind = FailureKind.NOT_FOUND if missing else FailureKind.REFUSED
    return FailedRun(kind=kind, detail=str(error), stdout='', stderr='')


async def drain_stream(stream: ByteReceiveStream | None, sink: bytearray) -> None:
    if not stream:
        return
    async for chunk in stream:
        sink.extend(chunk)


@dataclass(slots=True, kw_only=True, frozen=True)
class CapturedOutput:
    stdout: bytearray = field(default_factory=bytearray)
    stderr: bytearray = field(default_factory=bytearray)

    async def collect(self, process: Process) -> None:
        async with anyio.create_task_group() as drains:
            drains.start_soon(drain_stream, process.stdout, self.stdout)
            drains.start_soon(drain_stream, process.stderr, self.stderr)

    def decoded_run(self, exit_code: int) -> RunOutcome:
        try:
            stdout = captured_text(self.stdout, errors='strict')
            stderr = captured_text(self.stderr, errors='strict')
        except UnicodeDecodeError as error:
            return FailedRun(kind=FailureKind.UNDECODABLE, detail=str(error), stdout='', stderr='')
        return CompletedRun(exit=exit_code, stdout=stdout, stderr=stderr)

    def timed_out_run(self, timeout: float) -> FailedRun:
        return FailedRun(
            kind=FailureKind.TIMED_OUT,
            detail=f'timed out after {timeout}s',
            stdout=captured_text(self.stdout, errors='replace'),
            stderr=captured_text(self.stderr, errors='replace'),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class SubprocessRunner:
    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        cwd: Path | None = None,
    ) -> RunOutcome:
        try:
            process = await anyio.open_process(list(argv), stdin=subprocess.DEVNULL, cwd=cwd)
        except (OSError, ValueError) as error:
            return failed_run(error, program=argv[0])

        output = CapturedOutput()
        with anyio.move_on_after(timeout):
            async with process:
                await output.collect(process)
                return output.decoded_run(await process.wait())

        return output.timed_out_run(timeout)


def get_process_runner() -> ProcessRunner:
    return SubprocessRunner()
