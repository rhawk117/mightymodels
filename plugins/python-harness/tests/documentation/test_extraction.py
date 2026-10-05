"""One symbol's definition or section, cleaned and rendered as Markdown."""

import pytest
from python_harness.documentation.domain import DocumentationUrl
from python_harness.documentation.errors import MissingAnchorError
from python_harness.documentation.extraction import extract_markdown
from python_harness.documentation.tests.support import FILLER_SENTENCE, OS_PATH_PAGE

PAGE_URL = 'https://docs.python.org/3.13/library/os.path.html'


class TestExtractMarkdown:
    @pytest.fixture
    def join_definition(self) -> str:
        url = DocumentationUrl(text=f'{PAGE_URL}#os.path.join')
        return extract_markdown(OS_PATH_PAGE.encode(), url)

    @pytest.mark.parametrize(
        'expected',
        [
            pytest.param('os.path.join(path, \\*paths)', id='signature'),
            pytest.param('Join one or more path segments', id='body'),
            pytest.param(
                '(https://docs.python.org/3.13/library/os.html#os.sep)',
                id='absolute-link',
            ),
        ],
    )
    def test_definition_keeps_signature_body_and_absolute_links(
        self, join_definition: str, expected: str
    ) -> None:
        assert expected in join_definition

    @pytest.mark.parametrize(
        'unexpected',
        [
            pytest.param('tracking()', id='script'),
            pytest.param('#os.path.join)', id='headerlink'),
            pytest.param('isfile', id='neighbor'),
        ],
    )
    def test_definition_drops_chrome_and_neighbors(
        self, join_definition: str, unexpected: str
    ) -> None:
        assert unexpected not in join_definition

    def test_module_anchor_returns_the_enclosing_section(self) -> None:
        url = DocumentationUrl(text=f'{PAGE_URL}#module-os.path')
        section = extract_markdown(OS_PATH_PAGE.encode(), url)
        assert FILLER_SENTENCE.strip() in section
        assert 'os.path.isfile(path)' in section

    def test_missing_anchor_is_reported(self) -> None:
        url = DocumentationUrl(text=f'{PAGE_URL}#os.path.nothing')
        with pytest.raises(MissingAnchorError):
            extract_markdown(OS_PATH_PAGE.encode(), url)
