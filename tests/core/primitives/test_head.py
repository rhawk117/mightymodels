from mightymodels_core.primitives import short_head


class TestShortHead:
    def test_none_is_unknown(self) -> None:
        assert short_head(None) == 'unknown'

    def test_hash_is_cut_to_twelve_characters(self) -> None:
        assert short_head('07da02a1b2c3d4e5f6a7b8c9') == '07da02a1b2c3'

    def test_short_value_is_kept_whole(self) -> None:
        assert short_head('abc') == 'abc'
