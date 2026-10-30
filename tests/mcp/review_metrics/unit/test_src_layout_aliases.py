"""Modules under a nested `src` directory are aliased by the path after it."""

from mightymodels_mcp.review_metrics.components import ambiguous_aliases, module_lookup


def test_a_module_is_aliased_by_the_path_after_any_src_component() -> None:
    lookup = module_lookup(['packages.a.src.a_pkg.mod', 'src.top.mod'])

    assert lookup['a_pkg.mod'] == 'packages.a.src.a_pkg.mod'
    assert lookup['top.mod'] == 'src.top.mod'


def test_an_alias_claimed_by_two_modules_is_dropped_and_reported() -> None:
    names = ['packages.a.src.shared.mod', 'packages.b.src.shared.mod', 'src.top.mod']

    lookup = module_lookup(names)

    assert 'shared.mod' not in lookup
    assert lookup['top.mod'] == 'src.top.mod'
    assert ambiguous_aliases(names) == ['shared.mod']
