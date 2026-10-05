"""Collect the facts of every Python module under the requested paths."""

from python_harness.core.workspace import Workspace
from python_harness.facts.domain import FactsReport
from python_harness.facts.services import (
    FactCatalog,
    build_full_catalog,
    build_review_catalog,
    collect_facts,
)
from python_harness.tools.collect_python_facts.schema import FactsRequest


def catalog_for(request: FactsRequest) -> FactCatalog:
    if request.with_function_shapes:
        return build_full_catalog()
    return build_review_catalog()


def run(workspace: Workspace, request: FactsRequest) -> FactsReport:
    return collect_facts(workspace, request.paths, catalog_for(request))
