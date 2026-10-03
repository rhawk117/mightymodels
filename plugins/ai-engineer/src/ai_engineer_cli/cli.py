import argparse
import sys
from collections.abc import Callable, Sequence

GroupBuilder = Callable[[argparse.ArgumentParser], None]

GROUPS: dict[str, GroupBuilder] = {}


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
    parser.parse_args(argv)
    parser.print_help(sys.stderr)
    return 2
