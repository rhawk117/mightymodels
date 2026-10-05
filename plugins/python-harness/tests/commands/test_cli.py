"""The command line edge: process streams, reported failures and closed output pipes."""

import io
import json
import os
from collections.abc import Generator
from pathlib import Path
from types import MappingProxyType
from typing import TextIO

import pytest
from python_harness.cli import main
from python_harness.commands.domain import ProcessEdge
from python_harness.commands.exit_codes import ExitCode
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.workspace import Workspace


@pytest.fixture
def workspace(project_builder: ProjectBuilder) -> Workspace:
    return project_builder.write({'pkg/core.py': 'value = 1\n'})


@pytest.fixture
def stderr() -> io.StringIO:
    return io.StringIO()


class TestProcessStreams:
    def test_without_an_edge_the_document_goes_to_standard_output(
        self, workspace: Workspace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = main(('inspect', 'survey', '--root', str(workspace.root)))

        document = json.loads(capsys.readouterr().out)
        assert (exit_code, document['root']) == (ExitCode.PASSED, str(workspace.root))


class TestReportedFailure:
    @pytest.fixture
    def edge(self, stderr: io.StringIO) -> ProcessEdge:
        return ProcessEdge(io.StringIO(), io.StringIO(), stderr, MappingProxyType({}))

    @pytest.fixture
    def missing(self, project_builder: ProjectBuilder) -> Path:
        return project_builder.root.joinpath('absent')

    def test_reported_failure_exits_error_with_a_message_on_the_error_stream(
        self, edge: ProcessEdge, stderr: io.StringIO, missing: Path
    ) -> None:
        exit_code = main(('inspect', 'survey', '--root', str(missing)), edge=edge)

        assert (exit_code, stderr.getvalue()) == (
            ExitCode.ERROR,
            f'pythonista: workspace root {missing} is not a directory\n',
        )


class TestClosedOutputPipe:
    @pytest.fixture
    def closed_pipe(self) -> Generator[TextIO]:
        read_end, write_end = os.pipe()
        os.close(read_end)
        with os.fdopen(write_end, 'w', encoding='utf-8') as stream:
            yield stream

    @pytest.fixture
    def edge(self, closed_pipe: TextIO, stderr: io.StringIO) -> ProcessEdge:
        return ProcessEdge(io.StringIO(), closed_pipe, stderr, MappingProxyType({}))

    def test_a_reader_that_went_away_ends_the_command_quietly(
        self, workspace: Workspace, edge: ProcessEdge, stderr: io.StringIO
    ) -> None:
        exit_code = main(('inspect', 'survey', '--root', str(workspace.root)), edge=edge)

        assert (exit_code, stderr.getvalue()) == (ExitCode.PASSED, '')
