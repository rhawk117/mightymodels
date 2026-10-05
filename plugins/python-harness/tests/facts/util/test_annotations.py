"""Annotation facts, and the aliases and expressions that must not produce them."""

import pytest
from python_harness.core.sources import ParsedModule
from python_harness.facts.domain import FactKind
from python_harness.facts.services import collect_module_facts
from python_harness.facts.tests.support import (
    KindsAndLines,
    build_detector_catalog,
    kinds_and_lines,
)
from python_harness.facts.util.annotations import ANNOTATION_DETECTORS


class TestAnnotationDetectors:
    CATALOG = build_detector_catalog(ANNOTATION_DETECTORS)

    @pytest.mark.parametrize(
        ('source', 'expected'),
        [
            pytest.param(
                'def load(path: Annotated[str, Field()]) -> None:\n    pass\n',
                ((FactKind.INLINE_ANNOTATED, 1),),
                id='annotated-parameter',
            ),
            pytest.param(
                'def port() -> Annotated[int, Range(1, 9)]:\n    return 8\n',
                ((FactKind.INLINE_ANNOTATED, 1),),
                id='annotated-return',
            ),
            pytest.param(
                'class Config:\n    port: Annotated[int, Range(1, 9)]\n',
                ((FactKind.INLINE_ANNOTATED, 2),),
                id='annotated-class-field',
            ),
            pytest.param(
                """
                type Port = Annotated[int, Range(1, 9)]


                def connect(port: Port) -> None:
                    pass
                """,
                (),
                id='annotated-behind-a-type-alias',
            ),
            pytest.param(
                """
                def connect():
                    port: Annotated[int, Range(1, 9)] = 8
                    return port
                """,
                (),
                id='annotated-local-variable',
            ),
            pytest.param(
                'from __future__ import annotations\n',
                ((FactKind.FUTURE_ANNOTATIONS, 1),),
                id='future-annotations',
            ),
            pytest.param(
                'from __future__ import generator_stop\n',
                (),
                id='other-future-import',
            ),
            pytest.param(
                'def load(data: Any) -> dict[str, Any]:\n    pass\n',
                ((FactKind.ANY_ANNOTATION, 1), (FactKind.ANY_ANNOTATION, 1)),
                id='any-in-a-signature',
            ),
            pytest.param(
                'class Config:\n    extra: typing.Any\n',
                ((FactKind.ANY_ANNOTATION, 2),),
                id='qualified-any-in-a-field',
            ),
            pytest.param('value = cast(Any, raw)\n', (), id='any-outside-annotations'),
            pytest.param(
                'Port: TypeAlias = int\n',
                ((FactKind.TYPEALIAS_ANNOTATION, 1),),
                id='typealias-annotation',
            ),
            pytest.param('type Port = int\n', (), id='type-statement-alias'),
        ],
    )
    def test_each_kind_fires_on_its_shape_only(
        self, parsed_module: ParsedModule, expected: KindsAndLines
    ) -> None:
        facts = collect_module_facts(parsed_module, self.CATALOG).facts

        assert kinds_and_lines(facts) == sorted(expected)
