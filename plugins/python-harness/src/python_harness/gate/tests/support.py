"""Observations on gate plans shared by the gate tests."""

from python_harness.gate.domain import GateCommand, GatePlan, GateTool


def command_for(plan: GatePlan, tool: GateTool) -> GateCommand:
    return next(command for command in plan.commands if command.tool is tool)


def argv_for(plan: GatePlan, tool: GateTool) -> tuple[str, ...]:
    return command_for(plan, tool).argv
