"""Child processes: the one place the plugin launches them, and what a launch returns.

`ProcessRunner.run` is awaited under any anyio backend. It runs an argument vector without
a shell, with standard input at end of file, and waits at most `timeout` seconds, which
every caller has to name. It returns a `CompletedRun`, or a `FailedRun` whose `kind` says
which of four things happened: the wait ran out, the executable is missing, the system
refused the launch, or the output is not text in the default encoding. None of the four
leaves `run` as an exception, and `detail` carries the cause in words. A program, an
argument or a working directory that holds a NUL is a refused launch too, and so is a
working directory that does not exist. A caller that cancels the run gets its own
cancellation back. The child starts in a session of its own, and a timeout or a
cancellation ends the whole process group, so a grandchild does not outlive the run.
`env` is the child's whole environment; left out, the child inherits the parent's.

A finished run is decoded as `text=True` decodes it. What a timed-out run printed before
it was killed is decoded with the same encoding and the same newline handling, except
that bytes which are not text are replaced: the kill can cut a character in half, and a
timeout stays a timeout.
"""

import contextlib
import io
import os
import signal
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

import anyio

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from anyio.abc import ByteReceiveStream, Process


type FailureKind = Literal['timed_out', 'not_found', 'refused', 'undecodable']


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
    async def run(  # noqa: PLR0913  the contract runner needs the working directory and the environment next to the argument vector and timeout
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> RunOutcome: ...


def captured_text(captured: bytearray, *, errors: DecodeErrors) -> str:
    encoding = io.text_encoding(None)
    return io.TextIOWrapper(io.BytesIO(captured), encoding=encoding, errors=errors).read()


def failed_run(error: LaunchError, *, program: str) -> FailedRun:
    missing = isinstance(error, FileNotFoundError) and error.filename == program
    kind: FailureKind = 'not_found' if missing else 'refused'
    return FailedRun(kind=kind, detail=str(error), stdout='', stderr='')


def end_group(process: Process) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.kill(-process.pid, signal.Signals['SIGKILL'])


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
            return FailedRun(kind='undecodable', detail=str(error), stdout='', stderr='')
        return CompletedRun(exit=exit_code, stdout=stdout, stderr=stderr)

    def timed_out_run(self, timeout: float) -> FailedRun:
        return FailedRun(
            kind='timed_out',
            detail=f'timed out after {timeout}s',
            stdout=captured_text(self.stdout, errors='replace'),
            stderr=captured_text(self.stderr, errors='replace'),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class SubprocessRunner:
    async def run(  # noqa: PLR0913  the ProcessRunner Protocol fixes this signature
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> RunOutcome:
        try:
            process = await anyio.open_process(
                list(argv),
                stdin=subprocess.DEVNULL,
                cwd=cwd,
                env=env,
                start_new_session=True,
            )
        except (OSError, ValueError) as error:
            return failed_run(error, program=argv[0])

        output = CapturedOutput()
        exit_code: int | None = None
        async with process:
            try:
                with anyio.move_on_after(timeout):
                    await output.collect(process)
                    exit_code = await process.wait()
            finally:
                if exit_code is None:
                    end_group(process)

        if exit_code is None:
            return output.timed_out_run(timeout)

        return output.decoded_run(exit_code)


def get_process_runner() -> ProcessRunner:
    return SubprocessRunner()
