import argparse
import sys
from collections.abc import Callable, Sequence

from ai_engineer_cli.hook import command as create_hooks
from ai_engineer_cli.instruction import command as create_instructions
from ai_engineer_cli.mcp import command as create_mcp
from ai_engineer_cli.skill import command as create_skill
from ai_engineer_cli.subagent import command as create_subagent

GroupBuilder = Callable[[argparse.ArgumentParser], None]

GroupHandler = Callable[[argparse.Namespace], int]


class Arguments(argparse.Namespace):
    handler: GroupHandler | None = None


GROUPS: dict[str, GroupBuilder] = {
    'create-skill': create_skill.build_group,
    'create-hooks': create_hooks.build_group,
    'create-subagent': create_subagent.build_group,
    'create-instructions': create_instructions.build_group,
    'create-mcp': create_mcp.build_group,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='ai-engineer',
        description='Validate and scaffold the artifacts the ai-engineer skills author.',
    )
    subparsers = parser.add_subparsers(dest='group', metavar='GROUP')
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
