import pytest
from mightymodels_plugin.routing import ROUTING, Model, Scope, Worker, models_at


class TestRoutingTable:
    EVERY_SCOPE = (Scope.SM, Scope.MED, Scope.LARGE)

    @pytest.mark.parametrize(
        ('worker', 'models'),
        [
            pytest.param('code-scout', ('haiku', 'haiku', 'haiku'), id='code-scout'),
            pytest.param('web-scout', ('haiku', 'haiku', 'haiku'), id='web-scout'),
            pytest.param('qualitylens', ('haiku', 'haiku', 'haiku'), id='qualitylens'),
            pytest.param('gitty-up', ('haiku', 'haiku', 'haiku'), id='gitty-up'),
            pytest.param('engineer', ('sonnet', 'sonnet', 'sonnet'), id='engineer'),
            pytest.param('architect', ('sonnet', 'sonnet', 'opus'), id='architect'),
            pytest.param('uncle-bob-reviewer', ('sonnet', 'sonnet', 'sonnet'), id='uncle-bob'),
            pytest.param('merge-vader-reviewer', ('opus', 'opus', 'opus'), id='merge-vader'),
            pytest.param('wingman', ('opus', 'opus', 'opus'), id='wingman'),
        ],
    )
    def test_routing_table_maps_each_worker_and_scope_to_its_model_alias(
        self, worker: str, models: tuple[str, str, str]
    ) -> None:
        by_scope = ROUTING[Worker(worker)]

        assert tuple(by_scope[scope] for scope in self.EVERY_SCOPE) == models

    def test_routes_every_worker_at_every_scope(self) -> None:
        assert set(ROUTING) == set(Worker)
        assert all(set(by_scope) == set(Scope) for by_scope in ROUTING.values())

    def test_knows_only_the_four_aliases(self) -> None:
        assert [model.value for model in Model] == ['haiku', 'sonnet', 'opus', 'fable']

    def test_routes_nothing_to_fable_yet(self) -> None:
        routed = {model for by_scope in ROUTING.values() for model in by_scope.values()}

        assert Model.FABLE not in routed

    def test_models_at_a_scope_reads_the_one_table(self) -> None:
        assert models_at(Scope.LARGE) == {
            worker: by_scope[Scope.LARGE] for worker, by_scope in ROUTING.items()
        }
