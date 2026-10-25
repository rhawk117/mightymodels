import re
from base64 import b64decode
from importlib.resources import files
from pathlib import Path

import pytest
from mightymodels_mcp.server.icons import load_icon

ASSETS_DIR = Path(str(files('mightymodels_mcp').joinpath('assets')))


def svg_asset_cases() -> pytest.MarkDecorator:
    svgs = sorted(ASSETS_DIR.glob('*.svg'))
    return pytest.mark.parametrize('svg_path', [pytest.param(p, id=p.name) for p in svgs])


class TestSvgAssets:
    max_bytes = 4096
    badge_fill = '#3F3DBC'
    stroke_width = '3'

    def read_text(self, svg_path: Path) -> str:
        return svg_path.read_text(encoding='utf-8')

    @svg_asset_cases()
    def test_view_box_is_48_square(self, svg_path: Path) -> None:
        assert 'viewBox="0 0 48 48"' in self.read_text(svg_path)

    @svg_asset_cases()
    def test_size_is_within_budget(self, svg_path: Path) -> None:
        assert svg_path.stat().st_size <= self.max_bytes

    @svg_asset_cases()
    def test_badge_uses_the_indigo_fill(self, svg_path: Path) -> None:
        assert f'fill="{self.badge_fill}"' in self.read_text(svg_path)

    @svg_asset_cases()
    def test_every_stroke_is_three_wide(self, svg_path: Path) -> None:
        widths = re.findall(r'stroke-width="([^"]*)"', self.read_text(svg_path))
        assert widths
        assert set(widths) == {self.stroke_width}

    @svg_asset_cases()
    def test_has_no_script_or_text(self, svg_path: Path) -> None:
        text = self.read_text(svg_path).lower()
        assert '<script' not in text
        assert '<text' not in text

    @svg_asset_cases()
    def test_references_are_local_fragments(self, svg_path: Path) -> None:
        references = re.findall(r'href\s*=\s*"([^"]*)"', self.read_text(svg_path))
        assert all(reference.startswith('#') for reference in references)


class TestLoadIcon:
    @pytest.fixture
    def server_svg(self) -> bytes:
        return ASSETS_DIR.joinpath('server.svg').read_bytes()

    def test_src_is_a_base64_svg_data_uri(self) -> None:
        assert load_icon('server').src.startswith('data:image/svg+xml;base64,')

    def test_src_decodes_to_the_file_bytes(self, server_svg: bytes) -> None:
        payload = load_icon('server').src.removeprefix('data:image/svg+xml;base64,')
        assert b64decode(payload) == server_svg

    def test_mime_type_and_sizes(self) -> None:
        icon = load_icon('server')
        assert icon.mime_type == 'image/svg+xml'
        assert icon.sizes == ['any']
