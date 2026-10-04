import argparse
import sys
from collections.abc import Callable, Sequence

from ai_engineer_cli.hook import command as hook_command
from ai_engineer_cli.instruction import command as instruction_command
from ai_engineer_cli.mcp import command as mcp_group
from ai_engineer_cli.skill import command as skill_command
from ai_engineer_cli.subagent import command as subagent_command

GroupBuilder = Callable[[argparse.ArgumentParser], None]

GroupHandler = Callable[[argparse.Namespace], int]


class Arguments(argparse.Namespace):
    handler: GroupHandler | None = None


GROUPS: dict[str, GroupBuilder] = {
    'skill': skill_command.build_group,
    'hook': hook_command.build_group,
    'subagent': subagent_command.build_group,
    'instruction': instruction_command.build_group,
    'mcp': mcp_group.build_group,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='ai-engineer',
        description='Validate and scaffold the artifacts the ai-engineer skills author.',
    )
    subparsers = parser.add_subparsers(dest='group')
    for name, build_group in GROUPS.items():
        build_group(subparsers.add_parser(name))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv, namespace=Arguments())
    if arguments.handler is None:
        parser.print_help(sys.stderr)
        return 2
    return arguments.handler(arguments)
