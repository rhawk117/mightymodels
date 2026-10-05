"""Branch and loop facts, and the look-alikes that must not produce them."""

import pytest
from python_harness.core.sources import ParsedModule
from python_harness.facts.domain import ElseBranch, FactKind
from python_harness.facts.services import collect_module_facts
from python_harness.facts.tests.support import (
    Details,
    KindsAndLines,
    build_detector_catalog,
    kinds_and_lines,
)
from python_harness.facts.util.control_flow import CONTROL_FLOW_DETECTORS


class TestControlFlowDetectors:
    CATALOG = build_detector_catalog(CONTROL_FLOW_DETECTORS)
    IF_ELSE = """
        if ready:
            start()
        else:
            wait()
    """
    TRY_ELSE = """
        try:
            connect()
        except OSError:
            retry()
        else:
            close()
    """

    @pytest.mark.parametrize(
        ('source', 'expected'),
        [
            pytest.param(IF_ELSE, ((FactKind.ELSE_BRANCH, 4),), id='if-else'),
            pytest.param(
                """
                if ready:
                    start()
                elif waiting:
                    wait()
                """,
                (),
                id='elif-is-not-an-else',
            ),
            pytest.param(
                """
                if ready:
                    start()
                elif waiting:
                    wait()
                else:
                    stop()
                """,
                ((FactKind.ELSE_BRANCH, 6),),
                id='elif-chain-reports-only-its-final-else',
            ),
            pytest.param(
                """
                if ready:
                    start()
                else:
                    if waiting:
                        wait()
                """,
                ((FactKind.ELSE_BRANCH, 4),),
                id='else-holding-an-if-is-an-else',
            ),
            pytest.param(
                """
                for item in items:
                    if item:
                        break
                else:
                    finish()
                """,
                ((FactKind.BREAK_IN_LOOP, 3), (FactKind.ELSE_BRANCH, 5)),
                id='for-else-with-break',
            ),
            pytest.param(TRY_ELSE, ((FactKind.ELSE_BRANCH, 6),), id='try-else'),
            pytest.param(
                'while True:\n    poll()\n',
                ((FactKind.WHILE_TRUE, 1),),
                id='while-true',
            ),
            pytest.param(
                'while running:\n    poll()\n',
                (),
                id='while-condition-is-not-while-true',
            ),
            pytest.param(
                """
                def find(items):
                    for item in items:
                        if item:
                            return item
                    return None
                """,
                ((FactKind.RETURN_IN_LOOP, 4),),
                id='return-in-loop-body',
            ),
            pytest.param(
                """
                def find(items):
                    while items:
                        items.pop()
                    else:
                        return None
                """,
                ((FactKind.ELSE_BRANCH, 5),),
                id='return-in-loop-else-is-outside-the-body',
            ),
            pytest.param(
                """
                for item in items:
                    def check():
                        return item
                """,
                (),
                id='return-in-function-defined-inside-a-loop',
            ),
            pytest.param(
                """
                match command:
                    case 'go':
                        go()
                """,
                ((FactKind.MATCH_STATEMENT, 1),),
                id='match-statement',
            ),
            pytest.param('del cache[key]\n', ((FactKind.DEL_STATEMENT, 1),), id='del-statement'),
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
            pytest.param(IF_ELSE, (ElseBranch('if'),), id='if'),
            pytest.param(
                """
                async def drain(queue):
                    async for item in queue:
                        handle(item)
                    else:
                        close()
                """,
                (ElseBranch('for'),),
                id='async-for',
            ),
            pytest.param(
                'while running:\n    poll()\nelse:\n    close()\n',
                (ElseBranch('while'),),
                id='while',
            ),
            pytest.param(TRY_ELSE, (ElseBranch('try'),), id='try'),
            pytest.param(
                TRY_ELSE.replace('except OSError', 'except* OSError'),
                (ElseBranch('try'),),
                id='try-star',
            ),
        ],
    )
    def test_else_branch_names_its_statement(
        self, parsed_module: ParsedModule, expected: Details
    ) -> None:
        facts = collect_module_facts(parsed_module, self.CATALOG).facts

        assert tuple(fact.detail for fact in facts) == expected
