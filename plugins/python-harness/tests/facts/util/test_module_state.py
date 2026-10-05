"""Module-level state and process state facts, and the look-alikes that must not fire."""

import pytest
from python_harness.core.sources import ParsedModule
from python_harness.facts.domain import FactKind, ModuleLevelCall, MutableModuleGlobal
from python_harness.facts.services import collect_module_facts
from python_harness.facts.tests.support import (
    Details,
    KindsAndLines,
    build_detector_catalog,
    details_sharing_kinds,
    kinds_and_lines,
)
from python_harness.facts.util.module_state import MODULE_STATE_DETECTORS


class TestModuleStateDetectors:
    CATALOG = build_detector_catalog(MODULE_STATE_DETECTORS)
    MAIN_GUARDED = """
        if {guard}:
            main()
    """

    @pytest.mark.parametrize(
        ('source', 'expected'),
        [
            pytest.param(
                'REGISTRY = []\n',
                ((FactKind.MUTABLE_MODULE_GLOBAL, 1),),
                id='list-literal-global',
            ),
            pytest.param(
                'CACHE = defaultdict(list)\n',
                ((FactKind.MUTABLE_MODULE_GLOBAL, 1),),
                id='defaultdict-global',
            ),
            pytest.param(
                'ORDER = collections.OrderedDict()\n',
                ((FactKind.MUTABLE_MODULE_GLOBAL, 1),),
                id='qualified-ordered-dict-global',
            ),
            pytest.param("NAMES = ('alpha', 'beta')\n", (), id='tuple-global'),
            pytest.param(
                'def build():\n    items = []\n    return items\n',
                (),
                id='list-inside-a-function',
            ),
            pytest.param(
                'def bump():\n    global counter\n    counter += 1\n',
                ((FactKind.GLOBAL_STATEMENT, 2),),
                id='global-statement',
            ),
            pytest.param(
                'logging.basicConfig()\n',
                ((FactKind.MODULE_LEVEL_CALL, 1),),
                id='module-level-call',
            ),
            pytest.param(
                MAIN_GUARDED.format(guard="__name__ == '__main__'"),
                (),
                id='call-under-main-guard',
            ),
            pytest.param(
                MAIN_GUARDED.format(guard="'__main__' == __name__"),
                (),
                id='call-under-reversed-main-guard',
            ),
            pytest.param(
                """
                if __name__ == '__main__':
                    main()
                else:
                    register()
                """,
                ((FactKind.MODULE_LEVEL_CALL, 4),),
                id='call-in-the-else-of-a-main-guard',
            ),
            pytest.param('def run():\n    main()\n', (), id='call-inside-a-function'),
            pytest.param(
                "import sys\nsys.path.insert(0, 'src')\n",
                ((FactKind.MODULE_LEVEL_CALL, 2), (FactKind.SYS_PATH_MUTATION, 2)),
                id='sys-path-insert-at-import-time',
            ),
            pytest.param(
                'def reset():\n    sys.path[:] = []\n',
                ((FactKind.SYS_PATH_MUTATION, 2),),
                id='sys-path-slice-assignment',
            ),
            pytest.param('def roots():\n    return list(sys.path)\n', (), id='sys-path-read'),
            pytest.param(
                "def token():\n    return os.environ['TOKEN']\n",
                ((FactKind.OS_ENVIRON, 2),),
                id='os-environ',
            ),
            pytest.param(
                "HANDLERS = {'stop': lambda: None}\n",
                ((FactKind.MUTABLE_MODULE_GLOBAL, 1), (FactKind.LAMBDA_IN_COLLECTION, 1)),
                id='lambda-in-dict-global',
            ),
            pytest.param(
                """
                def order(items):
                    return sorted(items, key=lambda item: item.rank)
                """,
                (),
                id='lambda-as-call-argument',
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
                'ITEMS: list[str] = []\n',
                (MutableModuleGlobal('ITEMS'),),
                id='annotated-global-name',
            ),
            pytest.param(
                'FIRST = SECOND = {}\n',
                (MutableModuleGlobal('FIRST'), MutableModuleGlobal('SECOND')),
                id='chained-assignment-names-each-target',
            ),
            pytest.param(
                'app.run(debug=True)\n',
                (ModuleLevelCall('app.run'),),
                id='dotted-callee',
            ),
        ],
    )
    def test_details_name_the_state(self, parsed_module: ParsedModule, expected: Details) -> None:
        facts = collect_module_facts(parsed_module, self.CATALOG).facts

        assert details_sharing_kinds(facts, expected) == expected
