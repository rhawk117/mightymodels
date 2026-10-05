"""Reading cited sources and checking every citation in a review document."""

import io
import textwrap
from pathlib import Path
from types import MappingProxyType

import pytest
from python_harness.citations.domain import (
    Citation,
    CitationFailure,
    CitationProblem,
)
from python_harness.citations.errors import (
    CitationDocumentMissingError,
    CitationDocumentUnreadableError,
)
from python_harness.citations.services import (
    check_citation,
    check_citations,
    check_citations_in_stream,
)
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.workspace import Workspace

ORDERS_MODULE = """
    def place_order(quantity: int) -> int:
        return quantity
"""
CLEAN_REVIEW = """
    | Location | Quote | Fact |
    | --- | --- | --- |
    | src/shop/orders.py:2 | `return quantity` | returns its input |
"""


class TestCheckCitation:
    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write({'src/shop/orders.py': ORDERS_MODULE})

    @pytest.mark.parametrize(
        ('citation', 'expected'),
        [
            pytest.param(
                Citation(1, 'src/shop/orders.py', 2, 2, 'return quantity'),
                None,
                id='holds',
            ),
            pytest.param(
                Citation(1, 'src/shop/absent.py', 1, 1, 'return quantity'),
                CitationProblem.MISSING_FILE,
                id='missing-file',
            ),
            pytest.param(
                Citation(1, 'src/shop', 1, 1, 'return quantity'),
                CitationProblem.MISSING_FILE,
                id='directory-is-not-a-file',
            ),
            pytest.param(
                Citation(1, '../outside.py', 1, 1, 'return quantity'),
                CitationProblem.OUTSIDE_WORKSPACE,
                id='parent-path-escapes-root',
            ),
            pytest.param(
                Citation(1, '/etc/outside.py', 1, 1, 'return quantity'),
                CitationProblem.OUTSIDE_WORKSPACE,
                id='absolute-path-escapes-root',
            ),
            pytest.param(
                Citation(1, 'src/shop/orders.py', 3, 3, 'return quantity'),
                CitationProblem.LINE_OUT_OF_RANGE,
                id='cited-lines-are-checked-once-read',
            ),
        ],
    )
    def test_returns_the_problem_or_none(
        self, workspace: Workspace, citation: Citation, expected: CitationProblem | None
    ) -> None:
        assert check_citation(workspace, citation) is expected


class TestUnreadableCitedFile:
    CITATION = Citation(1, 'src/shop/latin.py', 1, 1, 'name = 1')

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        workspace = project_builder.write({})
        target = workspace.root.joinpath(self.CITATION.path)
        target.parent.mkdir(parents=True)
        target.write_bytes(b'name = 1\nlabel = "caf\xe9"\n')
        return workspace

    def test_undecodable_file_is_a_problem_not_a_crash(self, workspace: Workspace) -> None:
        assert check_citation(workspace, self.CITATION) is CitationProblem.UNREADABLE_FILE


class TestReportFailures:
    FILES = MappingProxyType(
        {
            'src/shop/orders.py': ORDERS_MODULE,
            'review/REVIEW.md': """
                # Review

                - Location: src/shop/orders.py:1 `def place_order(quantity: int)`
                - Location: src/shop/orders.py:40 `return quantity`

                ```python
                def stub() -> None: ...  # src/shop/ghost.py:1
                ```
            """,
            'review/CLEAN.md': CLEAN_REVIEW,
            'review/UNQUOTED.md': """
                | Location | Quote | Fact |
                | --- | --- | --- |
                | src/shop/orders.py:2 | (none) | returns its input |
            """,
        }
    )
    REVIEW = Path('review/REVIEW.md')
    HALLUCINATED = CitationFailure(
        Citation(4, 'src/shop/orders.py', 40, 40, 'return quantity'),
        CitationProblem.LINE_OUT_OF_RANGE,
    )
    QUOTELESS = CitationFailure(
        Citation(3, 'src/shop/orders.py', 2, 2, None),
        CitationProblem.MISSING_QUOTE,
    )
    UNFENCED_CITATIONS = 2

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    def test_failures_name_the_citation_and_its_problem(self, workspace: Workspace) -> None:
        report = check_citations(workspace, self.REVIEW)

        assert (report.failures, report.passed) == ((self.HALLUCINATED,), False)

    def test_a_citation_without_a_quote_fails(self, workspace: Workspace) -> None:
        report = check_citations(workspace, Path('review/UNQUOTED.md'))

        assert report.failures == (self.QUOTELESS,)

    def test_fenced_citations_are_not_checked(self, workspace: Workspace) -> None:
        report = check_citations(workspace, self.REVIEW)

        assert report.checked == self.UNFENCED_CITATIONS

    def test_passes_when_every_citation_holds(self, workspace: Workspace) -> None:
        report = check_citations(workspace, Path('review/CLEAN.md'))

        assert report.passed


class TestUncitedRows:
    FILES = MappingProxyType(
        {
            'src/shop/orders.py': ORDERS_MODULE,
            'review/PYLENS.md': """
                | Citation | Quote | Fact |
                | --- | --- | --- |
                | src/shop/orders.py:2 | `return quantity` | returns its input |
                | src/shop/orders.py:L2 | `return quantity` | returns its input |
                | src/shop/orders.py#L2 | `return quantity` | returns its input |
            """,
        }
    )
    PYLENS = Path('review/PYLENS.md')
    VERDICT = (1, (), (4, 5), False)

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    def test_rows_without_a_parseable_citation_fail_the_report(self, workspace: Workspace) -> None:
        report = check_citations(workspace, self.PYLENS)

        verdict = (report.checked, report.failures, report.uncited_rows, report.passed)
        assert verdict == self.VERDICT


class TestUnreadableDocument:
    DOCUMENT = Path('review/LATIN.md')

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        workspace = project_builder.write({'src/shop/orders.py': ORDERS_MODULE})
        document = workspace.root.joinpath(self.DOCUMENT)
        document.parent.mkdir()
        document.write_bytes(b'| src/shop/orders.py:2 | `caf\xe9` | x |\n')
        return workspace

    @pytest.fixture
    def undecodable_stream(self) -> io.TextIOWrapper:
        return io.TextIOWrapper(io.BytesIO(b'caf\xe9\n'), encoding='utf-8')

    def test_undecodable_document_file_is_reported(self, workspace: Workspace) -> None:
        with pytest.raises(CitationDocumentUnreadableError) as caught:
            check_citations(workspace, self.DOCUMENT)

        assert caught.value.document == self.DOCUMENT.as_posix()

    def test_undecodable_stream_is_reported(
        self, workspace: Workspace, undecodable_stream: io.TextIOWrapper
    ) -> None:
        with pytest.raises(CitationDocumentUnreadableError) as caught:
            check_citations_in_stream(workspace, undecodable_stream, '<stdin>')

        assert caught.value.document == '<stdin>'


class TestDocumentStream:
    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write({'src/shop/orders.py': ORDERS_MODULE})

    @pytest.fixture
    def stream(self) -> io.StringIO:
        return io.StringIO(textwrap.dedent(CLEAN_REVIEW))

    def test_a_stream_is_checked_under_the_given_name(
        self, workspace: Workspace, stream: io.StringIO
    ) -> None:
        report = check_citations_in_stream(workspace, stream, '<stdin>')

        assert (report.document, report.passed) == ('<stdin>', True)


class TestDocumentLocation:
    FILES = MappingProxyType({'src/shop/orders.py': ORDERS_MODULE, 'review/CLEAN.md': CLEAN_REVIEW})
    CLEAN = Path('review/CLEAN.md')

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    @pytest.fixture
    def outside_document(
        self, workspace: Workspace, tmp_path_factory: pytest.TempPathFactory
    ) -> Path:
        document = tmp_path_factory.mktemp('notes').joinpath('pylens-c01.md')
        document.write_bytes(workspace.root.joinpath(self.CLEAN).read_bytes())
        return document

    def test_document_is_named_relative_to_the_workspace(self, workspace: Workspace) -> None:
        report = check_citations(workspace, workspace.root.joinpath(self.CLEAN))

        assert report.document == self.CLEAN.as_posix()

    def test_document_outside_the_workspace_keeps_its_absolute_name(
        self, workspace: Workspace, outside_document: Path
    ) -> None:
        report = check_citations(workspace, outside_document)

        assert (report.document, report.passed) == (outside_document.as_posix(), True)

    def test_missing_document_is_reported(self, workspace: Workspace) -> None:
        with pytest.raises(CitationDocumentMissingError):
            check_citations(workspace, Path('review/ABSENT.md'))
