import argparse
import sys
from collections.abc import Callable, Sequence

from ai_engineer_cli import create_hooks, create_skill

GroupBuilder = Callable[[argparse.ArgumentParser], None]

GroupHandler = Callable[[argparse.Namespace], int]


class Arguments(argparse.Namespace):
    handler: GroupHandler | None = None


GROUPS: dict[str, GroupBuilder] = {
    'create-skill': create_skill.build_group,
    'create-hooks': create_hooks.build_group,
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
