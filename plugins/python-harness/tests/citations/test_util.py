"""Citation, quote and uncited table row parsing from Markdown, skipping fences."""

import pytest
from python_harness.citations.domain import Citation
from python_harness.citations.util import find_uncited_rows, parse_citations


class TestParseCitations:
    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            pytest.param(
                '- Location: src/x.py:12 `def render(self)`',
                (Citation(1, 'src/x.py', 12, 12, 'def render(self)'),),
                id='location-bullet-with-quote',
            ),
            pytest.param(
                '| src/x.py:12 | `raise Error` | fact |',
                (Citation(1, 'src/x.py', 12, 12, 'raise Error'),),
                id='table-row',
            ),
            pytest.param(
                'src/a.py:3 `alpha` and src/b.py:7-9 `beta`',
                (
                    Citation(1, 'src/a.py', 3, 3, 'alpha'),
                    Citation(1, 'src/b.py', 7, 9, 'beta'),
                ),
                id='two-citations-each-with-a-quote',
            ),
            pytest.param(
                'src/a.py:3 then src/b.py:4 `beta`',
                (
                    Citation(1, 'src/a.py', 3, 3, None),
                    Citation(1, 'src/b.py', 4, 4, 'beta'),
                ),
                id='quote-stops-at-the-next-citation',
            ),
            pytest.param(
                'See src/shop/orders.py:42-47.',
                (Citation(1, 'src/shop/orders.py', 42, 47, None),),
                id='range-without-quote',
            ),
            pytest.param(
                '- Location: `src/x.py:12` `def render(self)`',
                (Citation(1, 'src/x.py', 12, 12, 'def render(self)'),),
                id='citation-in-its-own-code-span',
            ),
            pytest.param(
                r'| src/x.py:3 | `def find(key: str) -> int \| None` | fact |',
                (Citation(1, 'src/x.py', 3, 3, 'def find(key: str) -> int | None'),),
                id='escaped-table-pipe-in-quote',
            ),
            pytest.param(
                '# Review\n\nsrc/x.py:5 `x`\n',
                (Citation(3, 'src/x.py', 5, 5, 'x'),),
                id='document-line-is-one-based',
            ),
            pytest.param(
                '```python\nstub src/a.py:1\n```\nsrc/x.py:4\n',
                (Citation(4, 'src/x.py', 4, 4, None),),
                id='fenced-block-ignored',
            ),
            pytest.param(
                '~~~~ mermaid\nsrc/a.py:1\n~~~\n```\n~~~~\nsrc/x.py:6\n',
                (Citation(6, 'src/x.py', 6, 6, None),),
                id='fence-closes-only-on-its-own-marker-at-full-length',
            ),
            pytest.param(
                '```\nsrc/a.py:1\n',
                (),
                id='unclosed-fence-runs-to-the-end',
            ),
            pytest.param(
                'notes.md:3, src/x.pyi:4, src/x.py.bak:5, src/x.py',
                (),
                id='non-python-paths-and-bare-paths-ignored',
            ),
        ],
    )
    def test_finds_citations_and_their_quotes(
        self, text: str, expected: tuple[Citation, ...]
    ) -> None:
        assert parse_citations(text) == expected


class TestFindUncitedRows:
    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            pytest.param(
                '| Citation | Quote | Fact |\n'
                '| --- | --- | --- |\n'
                '| src/x.py:3 | `alpha` | fact |\n'
                '| src/x.py:L4 | `beta` | fact |\n'
                '| src/x.py#L5 | `gamma` | fact |\n',
                (4, 5),
                id='header-and-separator-skipped-malformed-rows-found',
            ),
            pytest.param(
                '| Lens | Fact |\n|:---|---:|\n| state | none found |\n',
                (3,),
                id='aligned-separator-marks-the-header',
            ),
            pytest.param(
                '```\n| src/x.py#L1 | `alpha` | fact |\n```\n',
                (),
                id='fenced-rows-ignored',
            ),
            pytest.param(
                'See src/x.py#L4 for details.\n',
                (),
                id='prose-is-not-a-row',
            ),
            pytest.param(
                '  | src/x.py#L2 | `alpha` | fact |\n',
                (1,),
                id='indented-row',
            ),
            pytest.param(
                '| src/x.py#L2 | `alpha` | fact |\n---\n',
                (1,),
                id='rule-without-pipes-is-not-a-separator',
            ),
            pytest.param(
                '| src/a.py#L1 | `alpha` | see src/b.py:4 `beta` |\n',
                (),
                id='any-parseable-citation-cites-the-row',
            ),
        ],
    )
    def test_finds_data_rows_without_a_parseable_citation(
        self, text: str, expected: tuple[int, ...]
    ) -> None:
        assert find_uncited_rows(text) == expected
