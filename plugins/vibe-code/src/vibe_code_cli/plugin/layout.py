from dataclasses import dataclass, field

from vibe_code_cli.plugin.kinds import KIND_SPECS
from vibe_code_cli.plugin.record import Component, Plan

MANIFEST_PATH = '.claude-plugin/plugin.json'
RENDERED_FILES = (MANIFEST_PATH, 'README.md', 'PLAN.md', 'plugin-plan.json')


@dataclass
class Node:
    note: str = ''
    children: dict[str, 'Node'] = field(default_factory=dict)


def component_files(component: Component) -> list[str]:
    """The files a component owns: the ones recorded for a built component, else its kind's."""
    if component.files:
        return list(component.files)
    package = component.name.replace('-', '_')
    return [
        pattern.format(name=component.name, package=package)
        for pattern in KIND_SPECS[component.kind].files
    ]


def component_directory(component: Component) -> str | None:
    directory = KIND_SPECS[component.kind].directory
    return directory.format(name=component.name) if directory else None


def planned(plan: Plan) -> list[Component]:
    return [component for component in plan.components if component.status == 'planned']


def planned_directories(plan: Plan) -> list[str]:
    """Each directory the planned components own, once, in component order."""
    directories = (component_directory(component) for component in planned(plan))
    return list(dict.fromkeys(directory for directory in directories if directory))


def add_path(root: Node, path: str, note: str) -> None:
    parts = path.rstrip('/').split('/')
    node = root
    for index, part in enumerate(parts):
        is_directory = index < len(parts) - 1 or path.endswith('/')
        node = node.children.setdefault(f'{part}/' if is_directory else part, Node())
    if not node.note:
        node.note = note


def layout_tree(plan: Plan) -> Node:
    root = Node()
    for path in RENDERED_FILES:
        add_path(root, path, 'render')
    if plan.license:
        add_path(root, 'LICENSE', f'add the {plan.license} text; session 4.2 checks it')
    for component in plan.components:
        note = f'{component.kind} {component.name} ({component.status})'
        for path in component_files(component):
            add_path(root, path, note)
    return root


def tree_order(entry: tuple[str, Node]) -> tuple[bool, str]:
    name = entry[0]
    return (name.endswith('/'), name.lower())


def tree_lines(node: Node, prefix: str = '') -> list[str]:
    lines: list[str] = []
    entries = sorted(node.children.items(), key=tree_order)
    width = max((len(name) for name, _ in entries), default=0)
    for index, (name, child) in enumerate(entries):
        last = index == len(entries) - 1
        branch = '└── ' if last else '├── '
        lines.append(f'{prefix}{branch}{name:<{width}}  {child.note}'.rstrip())
        lines += tree_lines(child, prefix + ('    ' if last else '│   '))
    return lines
