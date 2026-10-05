"""Official documentation URL policy and version properties."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from python_harness.documentation.domain import DocumentationUrl, PythonVersion
from python_harness.documentation.errors import DocumentationError, InvalidVersionError

VALID_URL = 'https://docs.python.org/3.13/library/os.path.html#os.path.join'


class TestDocumentationUrl:
    unsafe_characters = st.characters(categories=['Zs', 'Cc', 'Zl', 'Zp'])

    @pytest.mark.parametrize(
        'url',
        [
            pytest.param(VALID_URL, id='fragment'),
            pytest.param('https://docs.python.org/3.0/library/os.html', id='oldest'),
            pytest.param('https://docs.python.org/3.99/library/os.html', id='future'),
        ],
    )
    def test_accepts_official_versioned_pages(self, url: str) -> None:
        assert DocumentationUrl(text=url).text == url

    @pytest.mark.parametrize(
        'url',
        [
            pytest.param('http://docs.python.org/3.13/library/os.html', id='plain-http'),
            pytest.param('https://evil.example/3.13/library/os.html', id='foreign-host'),
            pytest.param('https://docs.python.org/3.13/library/os.html?', id='empty-query'),
            pytest.param('https://docs.python.org/3.13/', id='no-page'),
            pytest.param('https://docs.python.org/2.7/library/os.html', id='python-two'),
            pytest.param('https://docs.python.org/3.13/../2.7/os.html', id='dot-segment'),
            pytest.param('https://docs.python.org/3.13/library/o%73.html', id='encoded'),
            pytest.param('https://docs.python.org/3.13\\library/os.html', id='backslash'),
        ],
    )
    def test_rejects_ambiguous_or_foreign_urls(self, url: str) -> None:
        with pytest.raises(DocumentationError):
            DocumentationUrl(text=url)

    @given(
        position=st.integers(min_value=0, max_value=len(VALID_URL)),
        character=unsafe_characters,
    )
    def test_rejects_whitespace_and_control_characters_anywhere(
        self, position: int, character: str
    ) -> None:
        with pytest.raises(DocumentationError):
            DocumentationUrl(text=VALID_URL[:position] + character + VALID_URL[position:])

    def test_exposes_version_page_and_fragment(self) -> None:
        url = DocumentationUrl(text=VALID_URL)
        assert (url.version, url.page_path, url.fragment, url.page_url.text) == (
            PythonVersion(text='3.13'),
            'library/os.path.html',
            'os.path.join',
            'https://docs.python.org/3.13/library/os.path.html',
        )


class TestPythonVersion:
    @pytest.mark.parametrize(
        'text',
        [
            pytest.param('3.0', id='oldest'),
            pytest.param('3.13', id='current'),
            pytest.param('3.99', id='future'),
        ],
    )
    def test_accepts_python_three_minor_versions(self, text: str) -> None:
        assert PythonVersion(text=text).base_url == f'https://docs.python.org/{text}/'

    @pytest.mark.parametrize(
        'text',
        [
            pytest.param('2.7', id='python-two'),
            pytest.param('3', id='major-only'),
            pytest.param('3.13.1', id='patch'),
            pytest.param('3.100', id='three-digit-minor'),
            pytest.param('3.01', id='leading-zero'),
            pytest.param('3.13\n', id='trailing-newline'),
            pytest.param(' 3.13', id='leading-space'),
            pytest.param('', id='empty'),
        ],
    )
    def test_rejects_text_outside_the_version_pattern(self, text: str) -> None:
        with pytest.raises(InvalidVersionError):
            PythonVersion(text=text)
