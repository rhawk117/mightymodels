"""Loads the shared fixture plugins owned by the concept packages."""

import pytest

CONCEPTS = ('core', 'facts', 'documentation', 'tools')


def pytest_configure(config: pytest.Config) -> None:
    for concept in CONCEPTS:
        config.pluginmanager.import_plugin(f'python_harness.{concept}.tests.fixtures')
