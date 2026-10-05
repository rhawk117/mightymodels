"""Comment and docstring facts, their owners, and strings that are neither."""

import pytest
from python_harness.core.sources import ParsedModule
from python_harness.facts.domain import Comment, Docstring, FactKind
from python_harness.facts.services import FactCatalog, collect_module_facts
from python_harness.facts.tests.support import (
    Details,
    KindsAndLines,
    details_sharing_kinds,
    kinds_and_lines,
)
from python_harness.facts.util.comments import (
    DOCSTRING_DETECTORS,
    collect_comment_facts,
)


class TestCommentAndDocstringFacts:
    CATALOG = FactCatalog(
        node_detectors=DOCSTRING_DETECTORS, module_collectors=(collect_comment_facts,)
    )
    DOCUMENTED = """
        '''Module.'''


        class Store:
            '''Store.'''

            def save(self):
                '''Save.'''
    """
    COMMENTED = """
        # top
        class Store:
            def save(self):
                return 1  # inside


        # bottom
    """

    @pytest.mark.parametrize(
        ('source', 'expected'),
        [
            pytest.param('value = 1  # one\n', ((FactKind.COMMENT, 1),), id='trailing-comment'),
            pytest.param("value = '# not a comment'\n", (), id='hash-inside-a-string'),
            pytest.param(
                DOCUMENTED,
                (
                    (FactKind.DOCSTRING, 1),
                    (FactKind.DOCSTRING, 5),
                    (FactKind.DOCSTRING, 8),
                ),
                id='module-class-and-function-docstrings',
            ),
            pytest.param(
                """
                def save():
                    value = 1
                    '''Not a docstring.'''
                """,
                (),
                id='string-after-the-first-statement',
            ),
        ],
    )
    def test_each_kind_fires_on_its_shape_only(
        self, parsed_module: ParsedModule, expected: KindsAndLines
    ) -> None:
        facts = collect_module_facts(parsed_module, self.CATALOG).facts

        assert kinds_and_lines(facts) == sorted(expected)

    @pytest.mark.parametrize(
        ('source', 'expected'),
        [
            pytest.param(
                'value = 1  # keep the cache warm\n',
                (Comment('keep the cache warm'),),
                id='comment-text-without-hash',
            ),
            pytest.param(
                DOCUMENTED,
                (Docstring('module'), Docstring('class'), Docstring('function')),
                id='docstring-owners',
            ),
        ],
    )
    def test_details_describe_the_text(
        self, parsed_module: ParsedModule, expected: Details
    ) -> None:
        facts = collect_module_facts(parsed_module, self.CATALOG).facts

        assert details_sharing_kinds(facts, expected) == expected

    @pytest.mark.parametrize(
        ('source', 'kind', 'expected'),
        [
            pytest.param(
                COMMENTED,
                FactKind.COMMENT,
                (None, 'Store.save', None),
                id='comments-take-the-innermost-definition',
            ),
            pytest.param(
                DOCUMENTED,
                FactKind.DOCSTRING,
                (None, 'Store', 'Store.save'),
                id='docstrings-belong-to-their-owner',
            ),
        ],
    )
    def test_symbols_locate_the_text(
        self,
        parsed_module: ParsedModule,
        kind: FactKind,
        expected: tuple[str | None, ...],
    ) -> None:
        facts = collect_module_facts(parsed_module, self.CATALOG).facts

        assert tuple(fact.symbol for fact in facts if fact.detail.kind is kind) == expected
