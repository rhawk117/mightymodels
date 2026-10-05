"""asyncio.gather and asyncio.to_thread facts, and the calls that only look alike."""

import pytest
from python_harness.core.sources import ParsedModule
from python_harness.facts.domain import FactKind
from python_harness.facts.services import collect_module_facts
from python_harness.facts.tests.support import (
    KindsAndLines,
    build_detector_catalog,
    kinds_and_lines,
)
from python_harness.facts.util.async_calls import ASYNC_CALL_DETECTORS


class TestAsyncCallDetectors:
    CATALOG = build_detector_catalog(ASYNC_CALL_DETECTORS)

    @pytest.mark.parametrize(
        ('source', 'expected'),
        [
            pytest.param(
                """
                async def run(first, second):
                    await asyncio.gather(first, second)
                """,
                ((FactKind.ASYNCIO_GATHER, 2),),
                id='gather',
            ),
            pytest.param(
                """
                async def run(path):
                    return await asyncio.to_thread(read, path)
                """,
                ((FactKind.ASYNCIO_TO_THREAD, 2),),
                id='to-thread',
            ),
            pytest.param(
                """
                async def run(first):
                    async with asyncio.TaskGroup() as group:
                        group.create_task(first)
                """,
                (),
                id='task-group',
            ),
            pytest.param(
                """
                async def run(results):
                    await results.gather()
                """,
                (),
                id='gather-method-on-another-object',
            ),
        ],
    )
    def test_each_kind_fires_on_its_shape_only(
        self, parsed_module: ParsedModule, expected: KindsAndLines
    ) -> None:
        facts = collect_module_facts(parsed_module, self.CATALOG).facts

        assert kinds_and_lines(facts) == sorted(expected)
