"""Try, handler and raise facts, and the look-alikes that must not produce them."""

import pytest
from python_harness.core.sources import ParsedModule
from python_harness.facts.domain import ExceptionBaseHandler, FactKind, TryBlock
from python_harness.facts.services import collect_module_facts
from python_harness.facts.tests.support import (
    Details,
    KindsAndLines,
    build_detector_catalog,
    details_sharing_kinds,
    kinds_and_lines,
)
from python_harness.facts.util.exceptions import EXCEPTION_DETECTORS


class TestExceptionDetectors:
    CATALOG = build_detector_catalog(EXCEPTION_DETECTORS)
    HANDLED = """
        try:
            connect()
        except {caught}:
            retry()
    """
    RAISED_IN_HANDLER = """
        try:
            connect()
        except OSError as error:
            {statement}
    """

    @pytest.mark.parametrize(
        ('source', 'expected'),
        [
            pytest.param(
                HANDLED.format(caught='OSError'),
                ((FactKind.TRY_BLOCK, 1),),
                id='specific-handler',
            ),
            pytest.param(
                HANDLED.format(caught='Exception'),
                ((FactKind.TRY_BLOCK, 1), (FactKind.EXCEPTION_BASE_HANDLER, 3)),
                id='except-exception',
            ),
            pytest.param(
                HANDLED.replace('except {caught}:', 'except:'),
                ((FactKind.TRY_BLOCK, 1), (FactKind.EXCEPTION_BASE_HANDLER, 3)),
                id='bare-except',
            ),
            pytest.param(
                HANDLED.format(caught='(OSError, BaseException)'),
                ((FactKind.TRY_BLOCK, 1), (FactKind.EXCEPTION_BASE_HANDLER, 3)),
                id='base-exception-inside-a-tuple',
            ),
            pytest.param(
                RAISED_IN_HANDLER.format(statement='raise LostError(host)'),
                ((FactKind.TRY_BLOCK, 1), (FactKind.RAISE_WITHOUT_CAUSE, 4)),
                id='new-exception-raised-in-handler',
            ),
            pytest.param(
                RAISED_IN_HANDLER.format(statement='raise LostError(host) from error'),
                ((FactKind.TRY_BLOCK, 1),),
                id='raise-with-from',
            ),
            pytest.param(
                RAISED_IN_HANDLER.format(statement='raise'),
                ((FactKind.TRY_BLOCK, 1),),
                id='bare-raise-in-handler',
            ),
            pytest.param(
                'def connect(host):\n    raise LostError(host)\n',
                (),
                id='raise-outside-a-handler',
            ),
            pytest.param(
                """
                try:
                    connect()
                except OSError:
                    def report():
                        raise ReportError(host)
                """,
                ((FactKind.TRY_BLOCK, 1),),
                id='raise-in-function-defined-inside-a-handler',
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
                """
                try:
                    connect()
                    send()
                except (OSError, ValueError):
                    retry()
                except KeyError:
                    skip()
                """,
                (
                    TryBlock(
                        handlers=2,
                        statements_in_try=2,
                        caught=('OSError', 'ValueError', 'KeyError'),
                    ),
                ),
                id='try-counts-handlers-and-names-what-they-catch',
            ),
            pytest.param(
                """
                try:
                    if ready:
                        send()
                finally:
                    close()
                """,
                (TryBlock(handlers=0, statements_in_try=2, caught=()),),
                id='try-counts-nested-statements',
            ),
            pytest.param(
                HANDLED.replace('except {caught}:', 'except:'),
                (ExceptionBaseHandler('bare'),),
                id='bare-handler',
            ),
            pytest.param(
                HANDLED.format(caught='Exception'),
                (ExceptionBaseHandler('Exception'),),
                id='exception-handler',
            ),
        ],
    )
    def test_details_describe_the_handlers(
        self, parsed_module: ParsedModule, expected: Details
    ) -> None:
        facts = collect_module_facts(parsed_module, self.CATALOG).facts

        assert details_sharing_kinds(facts, expected) == expected
