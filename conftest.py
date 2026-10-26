import os
import tomllib
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import pytest
from hypothesis import settings

pytest_plugins = ['pytester']


def resolve_hypothesis_profile() -> str:
    default_value = 'ci' if os.getenv('CI') == 'true' else 'dev'
    return os.getenv('HYPOTHESIS_PROFILE', default_value)


settings.register_profile('dev', max_examples=50, print_blob=True)
settings.register_profile('ci', parent=settings.get_profile('ci'), max_examples=300)
settings.register_profile('thorough', parent=settings.get_profile('ci'), max_examples=1000)
settings.load_profile(resolve_hypothesis_profile())

TIER_DEPTH = 2
CORE_TIER_NAMES = frozenset({'unit', 'integration', 'smoke'})
TIER_NAMES_BY_TREE = {
    'core': CORE_TIER_NAMES,
    'mcp': CORE_TIER_NAMES | {'e2e'},
}


def get_relative_parts(root: Path, path: Path, tree: str) -> tuple[str, ...]:
    return path.relative_to(root.joinpath('tests', tree), walk_up=True).parts


def get_tier_tree(root: Path, path: Path) -> tuple[str, tuple[str, ...]] | None:
    located = ((tree, get_relative_parts(root, path, tree)) for tree in TIER_NAMES_BY_TREE)
    return next(((tree, parts) for tree, parts in located if parts[0] != '..'), None)


def has_tier_directory(tree: str, relative_parts: tuple[str, ...]) -> bool:
    return len(relative_parts) > TIER_DEPTH and relative_parts[1] in TIER_NAMES_BY_TREE[tree]


def is_test_module(config: pytest.Config, file_path: Path) -> bool:
    patterns: list[str] = config.getini('python_files')
    return file_path.suffix == '.py' and any(
        fnmatch(file_path.name, pattern) for pattern in patterns
    )


def pytest_collect_file(file_path: Path, parent: pytest.Collector) -> None:
    if not is_test_module(parent.config, file_path):
        return

    located = get_tier_tree(parent.config.rootpath, file_path)
    if located is None or has_tier_directory(*located):
        return

    tree = located[0]
    tiers = ', '.join(sorted(TIER_NAMES_BY_TREE[tree]))
    message = (
        f'{file_path} is not under tests/{tree}/<concept>/<tier>/, '
        f'where the tier is one of the directories {tiers}'
    )
    raise pytest.UsageError(message)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        located = get_tier_tree(config.rootpath, item.path)
        if located is None or not has_tier_directory(*located):
            continue

        item.add_marker(located[1][1])


@pytest.fixture
def anyio_backend() -> str:
    return 'asyncio'


@pytest.fixture
def isolated_workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path.joinpath('home')
    home.mkdir()

    isolated_environment: dict[str, str] = dict.fromkeys(('HOME', 'USERPROFILE'), str(home))
    isolated_environment.update({
        'XDG_CONFIG_HOME': str(home.joinpath('.config')),
        'XDG_CACHE_HOME': str(home.joinpath('.cache')),
        'XDG_DATA_HOME': str(home.joinpath('.local', 'share')),
    })

    for env_var, value in isolated_environment.items():
        monkeypatch.setenv(env_var, value)

    return home


@pytest.fixture
def repository_root() -> Path:
    return Path(__file__).parent.resolve()


@pytest.fixture
def pyproject_file(repository_root: Path) -> dict[str, Any]:
    contents = repository_root.joinpath('pyproject.toml').read_text('utf-8')
    return tomllib.loads(contents)
