"""Official documentation URL policy and version properties."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError
from python_harness.documentation.domain import DocumentationUrl, PythonVersion

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
        assert DocumentationUrl.model_validate(url).root == url

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
        with pytest.raises(ValidationError):
            DocumentationUrl.model_validate(url)

    @given(
        position=st.integers(min_value=0, max_value=len(VALID_URL)),
        character=unsafe_characters,
    )
    def test_rejects_whitespace_and_control_characters_anywhere(
        self, position: int, character: str
    ) -> None:
        with pytest.raises(ValidationError):
            DocumentationUrl.model_validate(VALID_URL[:position] + character + VALID_URL[position:])

    def test_exposes_version_page_and_fragment(self) -> None:
        url = DocumentationUrl.model_validate(VALID_URL)
        assert (url.version, url.page_path, url.fragment, url.page_url.root) == (
            PythonVersion.model_validate('3.13'),
            'library/os.path.html',
            'os.path.join',
            'https://docs.python.org/3.13/library/os.path.html',
        )
