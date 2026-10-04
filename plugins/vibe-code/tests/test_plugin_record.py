import msgspec
import pytest
from vibe_code_cli.plugin.record import Component, Plan, decode_plan, normalise


class TestDefaults:
    @pytest.fixture
    def plan(self) -> Plan:
        return decode_plan({'name': 'p', 'components': [{'kind': 'skill', 'name': 'a'}]})

    def test_defaults_fill_every_key_the_record_leaves_out(self, plan: Plan) -> None:
        assert plan.version == '0.1.0'
        assert plan.license is None
        assert plan.open_questions == []
        assert plan.outside_plugin == []
        assert plan.components[0].status == 'planned'
        assert plan.components[0].answers == {}
        assert plan.components[0].facts == []
        assert plan.components[0].advice is None
        assert plan.components[0].decision == 'as planned'


class TestNormalise:
    EXPECTED_BUILDERS = ('create-hooks', None, 'create-skill')

    @pytest.fixture
    def plan_with_each_kind(self) -> Plan:
        return Plan(
            components=[
                Component(kind='hook'),
                Component(kind='lsp'),
                Component(kind='skill', builder='create-skill'),
            ]
        )

    def test_normalise_sets_each_builder_from_its_kind(self, plan_with_each_kind: Plan) -> None:
        builders = tuple(item.builder for item in normalise(plan_with_each_kind).components)

        assert builders == self.EXPECTED_BUILDERS

    def test_normalise_trims_a_license_and_drops_a_blank_one(self) -> None:
        assert normalise(Plan(license=' MIT ')).license == 'MIT'
        assert normalise(Plan(license='  ')).license is None
        assert normalise(Plan()).license is None


class TestUserConfigKey:
    CAMEL_CASE = b'{"userConfig": {"k": {"type": "string"}}}'

    def test_the_user_config_key_is_camel_case_in_the_record(self) -> None:
        plan = msgspec.json.decode(self.CAMEL_CASE, type=Plan)

        assert plan.user_config['k'].type == 'string'
