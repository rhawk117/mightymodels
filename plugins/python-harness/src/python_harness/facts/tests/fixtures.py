"""Shared pytest fixture: the parsed module a detector test builds from its snippet."""

import pytest

from python_harness.core.sources import ParsedModule, load_sources
from python_harness.core.tests.fixtures import ProjectBuilder


@pytest.fixture
def parsed_module(project_builder: ProjectBuilder, source: str) -> ParsedModule:
    workspace = project_builder.write({'module.py': source})
    loaded = load_sources(workspace, workspace.python_files('module.py'))
    return loaded.modules[0]
