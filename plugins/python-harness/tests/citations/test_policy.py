"""Quote comparison and per-citation checks against a source file handed in."""

import textwrap

import pytest
from python_harness.citations.domain import Citation, CitationOptions, CitationProblem
from python_harness.citations.policy import check_cited_lines, quote_matches
from python_harness.core.sources import SourceFile


class TestQuoteMatches:
    LINES = ('def place_order(', '    quantity: int,', ') -> int:')

    @pytest.mark.parametrize(
        'quote',
        [
            pytest.param('quantity: int,', id='indented-line'),
            pytest.param('def place_order( quantity: int, ) -> int:', id='wrapped'),
            pytest.param('  def   place_order(\tquantity:  int,', id='extra-whitespace'),
        ],
    )
    def test_whitespace_layout_does_not_matter(self, quote: str) -> None:
        assert quote_matches(quote, self.LINES)

    @pytest.mark.parametrize(
        'quote',
        [
            pytest.param('def place_order(quantity: int)', id='whitespace-removed'),
            pytest.param('def cancel_order(', id='different-code'),
        ],
    )
    def test_different_text_does_not_match(self, quote: str) -> None:
        assert not quote_matches(quote, self.LINES)


class TestCheckCitedLines:
    SOURCE = SourceFile(
        'src/shop/orders.py',
        textwrap.dedent(
            """
            class OrderError(Exception):
                pass


            def place_order(
                quantity: int,
            ) -> int:
                if quantity < 1:
                    raise OrderError('quantity must be positive')
                return quantity
            """
        ).lstrip(),
    )

    @pytest.mark.parametrize(
        ('citation', 'expected'),
        [
            pytest.param(
                Citation(1, 'src/shop/orders.py', 9, 9, "raise OrderError('quantity"),
                None,
                id='valid-with-quote',
            ),
            pytest.param(
                Citation(1, 'src/shop/orders.py', 5, 10, 'return quantity'),
                None,
                id='valid-range-to-last-line',
            ),
            pytest.param(
                Citation(1, 'src/shop/orders.py', 5, 7, 'place_order(  quantity: int,'),
                None,
                id='quote-match-across-wrapped-whitespace',
            ),
            pytest.param(
                Citation(1, 'src/shop/orders.py', 11, 11, 'return quantity'),
                CitationProblem.LINE_OUT_OF_RANGE,
                id='line-past-end-of-file',
            ),
            pytest.param(
                Citation(1, 'src/shop/orders.py', 0, 1, 'class OrderError'),
                CitationProblem.LINE_OUT_OF_RANGE,
                id='line-zero',
            ),
            pytest.param(
                Citation(1, 'src/shop/orders.py', 9, 5, 'raise OrderError'),
                CitationProblem.LINE_OUT_OF_RANGE,
                id='end-before-start',
            ),
            pytest.param(
                Citation(1, 'src/shop/orders.py', 11, 11, None),
                CitationProblem.LINE_OUT_OF_RANGE,
                id='range-is-checked-before-the-quote',
            ),
            pytest.param(
                Citation(1, 'src/shop/orders.py', 9, 9, None),
                CitationProblem.MISSING_QUOTE,
                id='no-quote',
            ),
            pytest.param(
                Citation(1, 'src/shop/orders.py', 6, 6, ':'),
                CitationProblem.MISSING_QUOTE,
                id='one-character-quote',
            ),
            pytest.param(
                Citation(1, 'src/shop/orders.py', 6, 6, '  t  '),
                CitationProblem.MISSING_QUOTE,
                id='short-once-whitespace-collapses',
            ),
            pytest.param(
                Citation(1, 'src/shop/orders.py', 6, 6, 'int'),
                None,
                id='quote-at-the-minimum-length',
            ),
            pytest.param(
                Citation(1, 'src/shop/orders.py', 9, 9, 'raise ValueError'),
                CitationProblem.QUOTE_NOT_FOUND,
                id='quote-mismatch',
            ),
            pytest.param(
                Citation(1, 'src/shop/orders.py', 1, 1, 'pass'),
                CitationProblem.QUOTE_NOT_FOUND,
                id='quote-outside-the-cited-lines',
            ),
        ],
    )
    def test_returns_the_problem_or_none(
        self, citation: Citation, expected: CitationProblem | None
    ) -> None:
        assert check_cited_lines(citation, self.SOURCE) is expected

    def test_minimum_quote_length_comes_from_the_options(self) -> None:
        citation = Citation(1, 'src/shop/orders.py', 6, 6, ':')

        problem = check_cited_lines(
            citation, self.SOURCE, options=CitationOptions(minimum_quote_characters=1)
        )

        assert problem is None
