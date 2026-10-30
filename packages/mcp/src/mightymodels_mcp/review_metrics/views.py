"""The metrics report as it is written: field order is the key order of the JSON object."""

from pydantic import BaseModel, ConfigDict


class PackageMetric(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    modules: int
    classes: int
    abstract_classes: int
    loc: int
    fan_in_ca: int
    fan_out_ce: int
    instability_i: float | None
    abstractness_a: float | None
    distance_d: float | None


class PackageReport(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    packages: dict[str, PackageMetric]
    package_cycles: list[list[str]]


class Violation(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    file: str
    name: str
    line: int
    loc: int
    params: int
    bool_params: int
    max_depth: int | None
    approximate: bool


class ViolationGroup(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    count: int
    worst: list[Violation]


class FileViolation(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    file: str
    loc: int


class Violations(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    functions_over_20_loc: ViolationGroup
    functions_over_3_params: ViolationGroup
    functions_with_bool_params: ViolationGroup
    functions_nested_deeper_than_2: ViolationGroup
    files_over_500_loc: list[FileViolation]
    long_lines_over_120_chars: int


class Totals(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    files: int
    source_files: int
    test_files: int
    source_loc: int
    test_loc: int
    test_to_source_ratio: float | None
    unparsed_files: int
    functions_measured: int
    loc_by_language: dict[str, int]


class ModuleCycles(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    count: int
    cycles: list[list[str]]


class SummaryReport(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    tool: str
    granularity_note: str
    totals: Totals
    component_metrics: PackageReport
    module_cycles_adp: ModuleCycles
    violations: Violations
