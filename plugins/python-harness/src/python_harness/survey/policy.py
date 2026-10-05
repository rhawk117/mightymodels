"""Inferences drawn from survey facts: library or application mode, and domains in use."""

from collections.abc import Iterable, Iterator

from python_harness.survey.domain import (
    NO_MANIFEST,
    Domain,
    LayoutFacts,
    Mode,
    ModeInference,
    ProjectManifest,
    SurveyOptions,
)

TYPED_CLASSIFIER = 'Typing :: Typed'


def find_application_evidence(manifest: ProjectManifest, layout: LayoutFacts) -> Iterator[str]:
    if manifest.entry_points:
        yield f'entry points: {", ".join(manifest.entry_points)}'
    if layout.has_dunder_main:
        yield '__main__.py present'


def find_library_evidence(manifest: ProjectManifest, layout: LayoutFacts) -> Iterator[str]:
    yield f'build backend {manifest.build_backend} without entry points'
    if layout.has_py_typed:
        yield 'py.typed marker present'
    if TYPED_CLASSIFIER in manifest.classifiers:
        yield f'{TYPED_CLASSIFIER} classifier'


def infer_mode(manifest: ProjectManifest, layout: LayoutFacts) -> ModeInference:
    if manifest is NO_MANIFEST:
        return ModeInference(Mode.APPLICATION, ('no pyproject.toml',))
    if application_evidence := tuple(find_application_evidence(manifest, layout)):
        return ModeInference(Mode.APPLICATION, application_evidence)
    if manifest.build_backend is None:
        reason = 'no build backend: uv application layout'
        return ModeInference(Mode.APPLICATION, (reason,))
    return ModeInference(Mode.LIBRARY, tuple(find_library_evidence(manifest, layout)))


def collect_package_names(
    manifest: ProjectManifest, external_packages: Iterable[str]
) -> frozenset[str]:
    declared = (
        *manifest.dependencies,
        *manifest.dev_dependencies,
        *manifest.optional_dependencies,
    )
    return frozenset((*external_packages, *declared))


def find_layout_domains(manifest: ProjectManifest, layout: LayoutFacts) -> Iterator[Domain]:
    if layout.has_tests_directory:
        yield Domain.PYTEST
    if manifest.entry_points:
        yield Domain.CLI


def detect_domains(
    manifest: ProjectManifest,
    external_packages: Iterable[str],
    layout: LayoutFacts,
    *,
    options: SurveyOptions | None = None,
) -> tuple[Domain, ...]:
    chosen = SurveyOptions() if options is None else options
    names = collect_package_names(manifest, external_packages)
    markers = chosen.domain_markers.items()
    marked = (domain for domain, marker in markers if not marker.isdisjoint(names))
    found = {*marked, *find_layout_domains(manifest, layout)}
    return tuple(domain for domain in Domain if domain in found)
