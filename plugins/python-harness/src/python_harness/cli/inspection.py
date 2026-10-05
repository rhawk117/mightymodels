"""The `python-harness inspect` group: facts about a project as JSON, never verdicts."""

import argparse
from pathlib import Path
from types import MappingProxyType
from typing import TextIO

from python_harness.calls.domain import CallsReport, SymbolReferencesReport
from python_harness.calls.services import (
    find_symbol_references_for,
    map_call_sites_for,
)
from python_harness.citations.domain import CitationReport
from python_harness.citations.services import (
    check_citations,
    check_citations_in_stream,
)
from python_harness.cli.domain import (
    CallsRequest,
    CitedDocument,
    CommandDefinition,
    FactsRequest,
    InspectCommand,
    InspectCommands,
    ProcessEdge,
    StandardInput,
)
from python_harness.cli.errors import (
    FallbackRuffConfigMissingError,
    HeadWithoutDiffError,
)
from python_harness.cli.exit_codes import ExitCode, exit_code_for
from python_harness.cli.util import add_command_parsers, build_root_parent
from python_harness.core.output import write_document
from python_harness.core.workspace import Workspace, open_workspace
from python_harness.facts.services import (
    FactCatalog,
    build_full_catalog,
    build_review_catalog,
    collect_facts,
)
from python_harness.gate.domain import GateOptions, GateTool
from python_harness.gate.services import run_gate_for
from python_harness.surface.domain import CodebaseTarget, DiffTarget, SurfaceOptions, Target
from python_harness.surface.services import plan_surface
from python_harness.survey.services import survey_project

STDIN_DOCUMENT = '-'


def run_survey(arguments: argparse.Namespace, edge: ProcessEdge) -> ExitCode:
    workspace = open_workspace(arguments.root)
    write_document(survey_project(workspace), edge.stdout)
    return ExitCode.PASSED


def add_gate_arguments(parser: argparse.ArgumentParser) -> None:
    defaults = GateOptions()
    parser.add_argument('--fallback-ruff-config', type=Path, default=None)
    parser.add_argument('--timeout', type=float, default=defaults.timeout_seconds)
    parser.add_argument(
        '--skip', action='append', default=[], choices=tuple(GateTool), metavar='TOOL'
    )


def locate_fallback_ruff_config(given: Path | None, root: Path) -> Path | None:
    if given is None:
        return None
    located = root.joinpath(given)
    if not located.is_file():
        raise FallbackRuffConfigMissingError(located)
    return located


def gate_options_from(arguments: argparse.Namespace, root: Path) -> GateOptions:
    fallback = locate_fallback_ruff_config(arguments.fallback_ruff_config, root)
    return GateOptions(
        fallback_ruff_config=fallback,
        timeout_seconds=arguments.timeout,
        skipped=frozenset(GateTool(name) for name in arguments.skip),
    )


def run_gate_command(arguments: argparse.Namespace, edge: ProcessEdge) -> ExitCode:
    workspace = open_workspace(arguments.root)
    options = gate_options_from(arguments, workspace.root)
    report = run_gate_for(workspace, options, environment=edge.environment)
    write_document(report, edge.stdout)
    return exit_code_for(passed=report.passed)


def add_surface_arguments(parser: argparse.ArgumentParser) -> None:
    defaults = SurfaceOptions()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--codebase', nargs='*', metavar='PATH')
    target.add_argument('--diff', metavar='BASE')
    parser.add_argument('--head', metavar='REF', help='head revision for --diff')
    parser.add_argument('--max-cluster-lines', type=int, default=defaults.max_cluster_lines)
    parser.add_argument('--budget', type=int, default=defaults.dispatch_budget)


def diff_target_from(base: str, head: str | None) -> DiffTarget:
    if head is None:
        return DiffTarget(base)
    return DiffTarget(base, head)


def codebase_target_from(paths: list[str], head: str | None) -> CodebaseTarget:
    if head is not None:
        raise HeadWithoutDiffError(head)
    if not paths:
        return CodebaseTarget()
    return CodebaseTarget(tuple(paths))


def target_from(arguments: argparse.Namespace) -> Target:
    if arguments.diff is not None:
        return diff_target_from(arguments.diff, arguments.head)
    return codebase_target_from(arguments.codebase, arguments.head)


def surface_options_from(arguments: argparse.Namespace) -> SurfaceOptions:
    return SurfaceOptions(arguments.max_cluster_lines, arguments.budget)


def run_surface(arguments: argparse.Namespace, edge: ProcessEdge) -> ExitCode:
    workspace = open_workspace(arguments.root)
    target = target_from(arguments)
    plan = plan_surface(workspace, target, surface_options_from(arguments))
    write_document(plan, edge.stdout)
    return ExitCode.PASSED


def add_path_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('paths', nargs='+', metavar='PATH')


def add_facts_arguments(parser: argparse.ArgumentParser) -> None:
    add_path_arguments(parser)
    parser.add_argument(
        '--with-function-shapes',
        action='store_true',
        help='also emit one function_shape fact per function',
    )


def catalog_from(arguments: argparse.Namespace) -> FactCatalog:
    if arguments.with_function_shapes:
        return build_full_catalog()
    return build_review_catalog()


def facts_request_from(arguments: argparse.Namespace) -> FactsRequest:
    return FactsRequest(tuple(arguments.paths), catalog_from(arguments))


def run_facts(arguments: argparse.Namespace, edge: ProcessEdge) -> ExitCode:
    workspace = open_workspace(arguments.root)
    request = facts_request_from(arguments)
    report = collect_facts(workspace, request.paths, request.catalog)
    write_document(report, edge.stdout)
    return ExitCode.PASSED


def add_calls_arguments(parser: argparse.ArgumentParser) -> None:
    add_path_arguments(parser)
    parser.add_argument('--symbol', metavar='NAME', help='references of NAME or module.NAME')


def calls_request_from(arguments: argparse.Namespace) -> CallsRequest:
    return CallsRequest(tuple(arguments.paths), arguments.symbol)


def build_calls_report(
    workspace: Workspace, request: CallsRequest
) -> CallsReport | SymbolReferencesReport:
    if request.symbol is None:
        return map_call_sites_for(workspace, request.paths)
    return find_symbol_references_for(workspace, request.paths, request.symbol)


def run_calls(arguments: argparse.Namespace, edge: ProcessEdge) -> ExitCode:
    workspace = open_workspace(arguments.root)
    report = build_calls_report(workspace, calls_request_from(arguments))
    write_document(report, edge.stdout)
    return ExitCode.PASSED


def add_cite_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('document', help="Markdown file, or '-' for stdin")


def cited_document_from(arguments: argparse.Namespace) -> CitedDocument:
    if arguments.document == STDIN_DOCUMENT:
        return StandardInput()
    return Path(arguments.document)


def build_cite_report(
    workspace: Workspace, document: CitedDocument, stdin: TextIO
) -> CitationReport:
    if isinstance(document, StandardInput):
        return check_citations_in_stream(workspace, stdin, document.name)
    return check_citations(workspace, document)


def run_cite(arguments: argparse.Namespace, edge: ProcessEdge) -> ExitCode:
    workspace = open_workspace(arguments.root)
    report = build_cite_report(workspace, cited_document_from(arguments), edge.stdin)
    write_document(report, edge.stdout)
    return exit_code_for(passed=report.passed)


def default_inspect_commands() -> InspectCommands:
    return MappingProxyType(
        {
            InspectCommand.SURVEY: CommandDefinition('mode evidence, domains, configs', run_survey),
            InspectCommand.GATE: CommandDefinition(
                'run ruff, ty and pytest, report results',
                run_gate_command,
                add_gate_arguments,
            ),
            InspectCommand.SURFACE: CommandDefinition(
                'review surface as import-graph clusters',
                run_surface,
                add_surface_arguments,
            ),
            InspectCommand.FACTS: CommandDefinition(
                'mechanical AST facts per module', run_facts, add_facts_arguments
            ),
            InspectCommand.CALLS: CommandDefinition(
                'reference counts and coupling metrics', run_calls, add_calls_arguments
            ),
            InspectCommand.CITE: CommandDefinition(
                'check path:line citations in a document', run_cite, add_cite_arguments
            ),
        }
    )


def register_inspect_commands(group: argparse.ArgumentParser) -> None:
    commands = group.add_subparsers(dest='command', required=True)
    add_command_parsers(commands, default_inspect_commands(), (build_root_parent(),))
