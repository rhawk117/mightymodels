import msgspec
from ai_engineer_cli.plugin.record import Component, Plan, decode_plan, normalise


def test_defaults_fill_every_key_the_record_leaves_out() -> None:
    plan = decode_plan({'name': 'p', 'components': [{'kind': 'skill', 'name': 'a'}]})

    assert plan.version == '0.1.0'
    assert plan.license is None
    assert plan.open_questions == []
    assert plan.outside_plugin == []
    assert plan.components[0].status == 'planned'
    assert plan.components[0].answers == {}
    assert plan.components[0].facts == []
    assert plan.components[0].advice is None
    assert plan.components[0].decision == 'as planned'


def test_normalise_sets_each_builder_from_its_kind() -> None:
    plan = Plan(
        components=[
            Component(kind='hook'),
            Component(kind='lsp'),
            Component(kind='skill', builder='create-skill'),
        ]
    )

    assert [item.builder for item in normalise(plan).components] == [
        'create-hooks',
        None,
        'create-skill',
    ]


def test_normalise_trims_a_license_and_drops_a_blank_one() -> None:
    assert normalise(Plan(license=' MIT ')).license == 'MIT'
    assert normalise(Plan(license='  ')).license is None
    assert normalise(Plan()).license is None


def test_the_user_config_key_is_camel_case_in_the_record() -> None:
    plan = msgspec.json.decode(b'{"userConfig": {"k": {"type": "string"}}}', type=Plan)

    assert plan.user_config['k'].type == 'string'
