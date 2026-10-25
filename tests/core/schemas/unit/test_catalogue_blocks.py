from mightymodels_core.schemas import DECLARATIONS


def test_every_block_has_a_declaration(blocks: dict[str, str]) -> None:
    assert set(blocks) == {declaration.name for declaration in DECLARATIONS}
