"""Bounded inventory expansion and symbol indexing."""

import zlib

import pytest
from python_harness.documentation.domain import PythonVersion
from python_harness.documentation.errors import (
    CorruptInventoryError,
    DocumentationError,
    EmptyInventoryError,
    InventoryEntryLimitError,
    InventoryTooLargeError,
    MalformedInventoryError,
    UnsupportedInventoryError,
)
from python_harness.documentation.inventory import parse_inventory
from python_harness.documentation.settings import Settings
from python_harness.documentation.tests.support import (
    INDEXED_NAMES,
    STANDARD_ENTRIES,
    InventoryEntry,
    inventory_bytes,
    inventory_plaintext,
)

ESCAPING_ENTRY = InventoryEntry(name='escape', uri='../2.7/library/os.html#$')
FOREIGN_SCOPE_ENTRY = InventoryEntry(name='guide', uri='howto/logging.html#$', indexed=False)
HEADER = inventory_plaintext(()).removesuffix(b'\n')


class TestParseInventory:
    def test_indexes_python_symbols_in_indexed_sections(
        self, settings: Settings, docs_version: PythonVersion
    ) -> None:
        index = parse_inventory(inventory_bytes(), docs_version, settings)
        assert set(index.symbols) == INDEXED_NAMES

    def test_expands_dollar_uris_to_the_symbol_anchor(
        self, settings: Settings, docs_version: PythonVersion
    ) -> None:
        index = parse_inventory(inventory_bytes(), docs_version, settings)
        url = index.symbols['object.__getattr__'].source_url
        assert (
            url.root == 'https://docs.python.org/3.13/reference/datamodel.html#object.__getattr__'
        )

    def test_skips_a_tolerable_share_of_unusable_entries(self, docs_version: PythonVersion) -> None:
        tolerant = Settings(max_malformed_entry_ratio=0.5)
        index = parse_inventory(
            inventory_bytes((*STANDARD_ENTRIES, ESCAPING_ENTRY)), docs_version, tolerant
        )
        assert 'escape' not in index.symbols

    @pytest.mark.parametrize(
        ('content', 'settings_override', 'error'),
        [
            pytest.param(
                inventory_bytes((*STANDARD_ENTRIES, ESCAPING_ENTRY)),
                {},
                MalformedInventoryError,
                id='too-many-unusable',
            ),
            pytest.param(
                inventory_bytes((FOREIGN_SCOPE_ENTRY,)),
                {},
                EmptyInventoryError,
                id='empty',
            ),
            pytest.param(
                b'# Sphinx inventory version 1\n',
                {},
                UnsupportedInventoryError,
                id='header',
            ),
            pytest.param(HEADER + b'\nnot zlib', {}, CorruptInventoryError, id='corrupt'),
            pytest.param(
                HEADER + b'\n' + zlib.compress(b'x' * 4096)[:-4],
                {},
                CorruptInventoryError,
                id='truncated',
            ),
            pytest.param(
                inventory_bytes(),
                {'inventory_max_bytes': 64},
                InventoryTooLargeError,
                id='bytes',
            ),
            pytest.param(
                inventory_bytes(),
                {'inventory_max_entries': 2},
                InventoryEntryLimitError,
                id='entries',
            ),
        ],
    )
    def test_rejects_unusable_inventories(
        self,
        content: bytes,
        settings_override: dict[str, int],
        error: type[DocumentationError],
    ) -> None:
        version = PythonVersion.model_validate('3.13')
        with pytest.raises(error):
            parse_inventory(content, version, Settings.model_validate(settings_override))
