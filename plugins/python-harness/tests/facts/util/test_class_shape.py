"""Class decorator, base, special method and ClassVar facts, and their look-alikes."""

import pytest
from python_harness.core.output import to_json_value
from python_harness.core.sources import ParsedModule
from python_harness.facts.domain import (
    ClassMethod,
    ClassVarAnnotation,
    ConstantFlag,
    DataclassDecorator,
    ExpressionFlag,
    FactKind,
    HandwrittenInit,
    OperatorOverload,
    PostInit,
)
from python_harness.facts.services import collect_module_facts
from python_harness.facts.tests.support import (
    Details,
    KindsAndLines,
    build_detector_catalog,
    details_sharing_kinds,
    kinds_and_lines,
)
from python_harness.facts.util.class_shape import CLASS_SHAPE_DETECTORS


class TestClassShapeDetectors:
    CATALOG = build_detector_catalog(CLASS_SHAPE_DETECTORS)
    CLASSMETHOD_FACTORY = """
        class Parser:
            @classmethod
            def build(cls):
                return cls()
    """
    DATACLASS_WITH_CLASSVAR = """
        @dataclass
        class Point:
            origin: ClassVar[int] = 0
    """
    PLAIN_INIT = """
        class Account:
            def __init__(self, owner):
                self.owner = owner
    """
    POST_INIT = """
        @dataclass
        class Account:
            owner: str

            def __post_init__(self):
                check(self.owner)
    """
    DECORATED_POINT = """
        @{decorator}
        class Point:
            x: int
    """

    @pytest.mark.parametrize(
        ('source', 'expected'),
        [
            pytest.param(
                """
                class Parser:
                    @staticmethod
                    def parse(text):
                        return text
                """,
                ((FactKind.STATICMETHOD, 2),),
                id='staticmethod',
            ),
            pytest.param(CLASSMETHOD_FACTORY, ((FactKind.CLASSMETHOD, 2),), id='classmethod'),
            pytest.param(
                'class _Cache:\n    pass\n',
                ((FactKind.PRIVATE_CLASS, 1),),
                id='private-class',
            ),
            pytest.param(
                DECORATED_POINT.format(decorator='dataclass(frozen=True)'),
                ((FactKind.DATACLASS, 1),),
                id='frozen-dataclass-without-classvar',
            ),
            pytest.param(
                DATACLASS_WITH_CLASSVAR,
                ((FactKind.DATACLASS, 1), (FactKind.CLASSVAR, 3)),
                id='classvar-in-dataclass',
            ),
            pytest.param(
                'limit: ClassVar[int] = 3\n', (), id='classvar-annotation-outside-a-class'
            ),
            pytest.param(
                """
                @runtime_checkable
                class Reader(Protocol):
                    def read(self) -> str: ...
                """,
                ((FactKind.RUNTIME_CHECKABLE, 1), (FactKind.PROTOCOL, 2)),
                id='runtime-checkable-protocol',
            ),
            pytest.param(
                'class Reader(Protocol[T]):\n    pass\n',
                ((FactKind.PROTOCOL, 1),),
                id='generic-protocol',
            ),
            pytest.param('class Base(ABC):\n    pass\n', ((FactKind.ABC_BASE, 1),), id='abc-base'),
            pytest.param(
                'class Base(metaclass=abc.ABCMeta):\n    pass\n',
                ((FactKind.ABC_BASE, 1),),
                id='abc-metaclass',
            ),
            pytest.param(PLAIN_INIT, ((FactKind.HANDWRITTEN_INIT, 2),), id='handwritten-init'),
            pytest.param(
                'def __init__(self):\n    pass\n',
                (),
                id='module-function-named-init',
            ),
            pytest.param(
                POST_INIT,
                ((FactKind.DATACLASS, 1), (FactKind.POST_INIT, 5)),
                id='post-init',
            ),
            pytest.param(
                """
                class Money:
                    def __add__(self, other):
                        return other

                    def __eq__(self, other):
                        return True

                    def __repr__(self):
                        return 'Money'
                """,
                ((FactKind.OPERATOR_OVERLOAD, 2), (FactKind.OPERATOR_OVERLOAD, 5)),
                id='operator-dunders-but-not-repr',
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
                DECORATED_POINT.format(decorator='dataclass(frozen=True, slots=True)'),
                (
                    DataclassDecorator(
                        frozen=ConstantFlag(value=True),
                        slots=ConstantFlag(value=True),
                        kw_only=ConstantFlag(value=False),
                    ),
                ),
                id='constant-dataclass-flags',
            ),
            pytest.param(
                DECORATED_POINT.format(decorator='dataclass'),
                (
                    DataclassDecorator(
                        frozen=ConstantFlag(value=False),
                        slots=ConstantFlag(value=False),
                        kw_only=ConstantFlag(value=False),
                    ),
                ),
                id='bare-dataclass-flags-take-their-defaults',
            ),
            pytest.param(
                DECORATED_POINT.format(decorator='dataclasses.dataclass(kw_only=KEYED)'),
                (
                    DataclassDecorator(
                        frozen=ConstantFlag(value=False),
                        slots=ConstantFlag(value=False),
                        kw_only=ExpressionFlag(source='KEYED'),
                    ),
                ),
                id='expression-flag-keeps-its-source',
            ),
            pytest.param(
                CLASSMETHOD_FACTORY,
                (ClassMethod(returns_cls_call=True),),
                id='classmethod-returning-cls-call',
            ),
            pytest.param(
                CLASSMETHOD_FACTORY.replace('return cls()', 'return describe(cls)'),
                (ClassMethod(returns_cls_call=False),),
                id='classmethod-returning-something-else',
            ),
            pytest.param(
                """
                class LimitError(ValueError):
                    def __init__(self, limit):
                        super().__init__(limit)
                        self.limit = limit
                """,
                (HandwrittenInit(statements=2, exception_class=True),),
                id='init-of-an-exception-class',
            ),
            pytest.param(
                PLAIN_INIT,
                (HandwrittenInit(statements=1, exception_class=False),),
                id='init-of-a-plain-class',
            ),
            pytest.param(
                POST_INIT,
                (PostInit(statements=1),),
                id='post-init-statements',
            ),
            pytest.param(
                DATACLASS_WITH_CLASSVAR,
                (ClassVarAnnotation(in_dataclass=True),),
                id='classvar-in-a-dataclass',
            ),
            pytest.param(
                'class Registry:\n    entries: ClassVar[dict[str, int]] = {}\n',
                (ClassVarAnnotation(in_dataclass=False),),
                id='classvar-in-a-plain-class',
            ),
            pytest.param(
                'class Grid:\n    def __getitem__(self, key):\n        return key\n',
                (OperatorOverload(operator='__getitem__'),),
                id='container-dunder',
            ),
        ],
    )
    def test_details_describe_the_class_shape(
        self, parsed_module: ParsedModule, expected: Details
    ) -> None:
        facts = collect_module_facts(parsed_module, self.CATALOG).facts

        assert details_sharing_kinds(facts, expected) == expected


class TestDataclassFlagDocument:
    CATALOG = build_detector_catalog(CLASS_SHAPE_DETECTORS)

    @pytest.mark.parametrize(
        ('source', 'expected'),
        [
            pytest.param(
                """
                @dataclass(frozen=FLAG, slots=True)
                class Point:
                    x: int
                """,
                {
                    'frozen': {'source': 'FLAG', 'kind': 'expression'},
                    'slots': {'value': True, 'kind': 'constant'},
                    'kw_only': {'value': False, 'kind': 'constant'},
                    'kind': 'dataclass',
                },
                id='each-flag-carries-its-kind',
            ),
        ],
    )
    def test_flags_reach_the_document_typed(
        self, parsed_module: ParsedModule, expected: dict[str, object]
    ) -> None:
        facts = collect_module_facts(parsed_module, self.CATALOG).facts

        assert to_json_value(facts[0].detail) == expected
