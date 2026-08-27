#!/usr/bin/env python3
"""Freeze and audit the FUN+C_FUN file-NPR threshold grid before FUN+C_FUN quality outcomes are joined.

I02 consumes the I01 repo-month/Python-file FUN+C_FUN NPR artifact and applies a
pre-specified threshold grid to the continuous file-level FUN+C_FUN NPR signal.  It
intentionally does not read SonarQube or any other quality outcome.  The goal is therefore threshold transfer/pre-specification and coverage/sample-composition
auditing for the FUN+C_FUN extension, not treatment-effect estimation.

Primary specification
---------------------
- Metric: file_npr_fun_cfun_space_by_token_weighted
- Primary threshold T: 1.571637
- Main sensitivity grid: T + delta for delta=-0.50,-0.45,...,+0.50
- Legacy benchmark anchor: 1.5183 (reported separately; not part of the grid)
- Decision rule: AGC-like/high-FUN+C_FUN-NPR file iff NPR > threshold
- Threshold provenance: reuse the previously frozen SC2-7B FUN threshold/grid unchanged
- I02 does not recalibrate thresholds from the FUN+C_FUN distribution or quality outcomes

Treatment timing
----------------
I02 follows the normalized Model A timing used by the quality DiD design:
- treatment_group = event_index > 0
- event_time_normalized = time_index - event_index for treatment repositories
- absorbing_treated = event_index > 0 and time_index >= event_index
Legacy treatment/post flags are not used.

Outputs are aggregate audits only. I02 does not generate 22 duplicated
file-level classification datasets; a later I-series quality-panel stage can
reapply the frozen threshold specification when joining I01 file rows to
SonarQube file-level outcomes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCRIPT_VERSION = "run-x-i02-v1"
METRIC_COLUMN = "file_npr_fun_cfun_space_by_token_weighted"
COMPARISON_OPERATOR = ">"
DEFAULT_PRIMARY_THRESHOLD = Decimal("1.571637")
DEFAULT_GRID_STEP = Decimal("0.05")
DEFAULT_GRID_RADIUS = Decimal("0.50")
DEFAULT_LEGACY_THRESHOLD = Decimal("1.5183")
EXPECTED_I01_SCRIPT_VERSION = "run-x-i01-v1"

EXPECTED_FILE_STATUSES = {
    "scored",
    "scored_with_expected_exclusions",
    "no_fun_cfun",
    "fun_cfun_all_excluded",
    "file_not_prepared",
    "unexpected_missing_score",
}
FINITE_FILE_STATUSES = {"scored", "scored_with_expected_exclusions"}

INPUT_REQUIRED_COLUMNS = {
    "repo_id",
    "dataset_source",
    "repo_name",
    "repo_month",
    "time_index",
    "event_index",
    "snapshot_id",
    "snapshot_commit",
    "relative_path",
    "file_sha256",
    "fun_cfun_occurrences_total",
    "fun_cfun_occurrences_scored",
    "fun_cfun_occurrences_excluded",
    "fun_cfun_npr_coverage_ratio",
    METRIC_COLUMN,
    "fun_cfun_expected_exclusion_classes",
    "file_npr_fun_cfun_status",
}

THRESHOLD_SPEC_COLUMNS = [
    "threshold_id",
    "threshold_role",
    "grid_order",
    "delta_from_primary",
    "threshold",
    "comparison_operator",
    "metric",
    "note",
]

GLOBAL_AUDIT_COLUMNS = [
    "threshold_id",
    "threshold_role",
    "grid_order",
    "delta_from_primary",
    "threshold",
    "comparison_operator",
    "repo_month_file_rows_total",
    "eligible_finite_fun_cfun_rows",
    "ineligible_rows",
    "selected_file_rows",
    "selected_share_of_eligible",
    "selected_share_of_all_python_rows",
    "eligible_full_coverage_rows",
    "eligible_partial_coverage_rows",
    "selected_full_coverage_rows",
    "selected_partial_coverage_rows",
    "eligible_rows_with_expected_exclusions",
    "selected_rows_with_expected_exclusions",
    "unique_snapshot_files_total",
    "eligible_unique_snapshot_files",
    "selected_unique_snapshot_files",
    "selected_unique_snapshot_file_share",
    "repositories_with_selected_files",
    "repo_months_with_selected_files",
]

GROUP_AUDIT_COLUMNS = [
    "threshold_id",
    "threshold_role",
    "grid_order",
    "delta_from_primary",
    "threshold",
    "stratum",
    "repo_month_file_rows_total",
    "eligible_finite_fun_cfun_rows",
    "selected_file_rows",
    "selected_share_of_eligible",
    "selected_share_of_all_python_rows",
    "eligible_partial_coverage_rows",
    "selected_partial_coverage_rows",
    "eligible_rows_with_expected_exclusions",
    "selected_rows_with_expected_exclusions",
]

REPO_MONTH_AUDIT_COLUMNS = [
    "threshold_id",
    "threshold_role",
    "grid_order",
    "delta_from_primary",
    "threshold",
    "repo_id",
    "dataset_source",
    "repo_name",
    "repo_month",
    "time_index",
    "event_index",
    "event_time_normalized",
    "treatment_group",
    "absorbing_treated",
    "repo_month_file_rows_total",
    "eligible_finite_fun_cfun_rows",
    "selected_file_rows",
    "selected_share_of_eligible",
    "selected_share_of_all_python_rows",
    "eligible_partial_coverage_rows",
    "selected_partial_coverage_rows",
    "eligible_rows_with_expected_exclusions",
    "selected_rows_with_expected_exclusions",
]

DISTRIBUTION_COLUMNS = [
    "scope",
    "stratum",
    "n",
    "mean",
    "min",
    "p01",
    "p05",
    "p10",
    "p25",
    "p50",
    "p75",
    "p90",
    "p95",
    "p99",
    "max",
]

CHECK_COLUMNS = ["check_name", "severity", "passed", "observed", "expected", "note"]


@dataclass(frozen=True)
class ThresholdSpec:
    threshold_id: str
    threshold_role: str
    grid_order: int | None
    delta: Decimal | None
    threshold: Decimal
    note: str

    def as_row(self) -> dict[str, Any]:
        return {
            "threshold_id": self.threshold_id,
            "threshold_role": self.threshold_role,
            "grid_order": "" if self.grid_order is None else self.grid_order,
            "delta_from_primary": "" if self.delta is None else decimal_text(self.delta),
            "threshold": decimal_text(self.threshold),
            "comparison_operator": COMPARISON_OPERATOR,
            "metric": METRIC_COLUMN,
            "note": self.note,
        }


@dataclass
class ThresholdCounters:
    selected: list[int]
    selected_partial: list[int]
    selected_expected_exclusion: list[int]
    selected_repos: list[set[str]]
    selected_repo_months: list[set[str]]


@dataclass
class GroupCounters:
    total: int = 0
    eligible: int = 0
    eligible_partial: int = 0
    eligible_expected_exclusion: int = 0
    selected: list[int] = field(default_factory=list)
    selected_partial: list[int] = field(default_factory=list)
    selected_expected_exclusion: list[int] = field(default_factory=list)


@dataclass
class RepoMonthCounters:
    repo_id: str
    dataset_source: str
    repo_name: str
    repo_month: str
    time_index: int
    event_index: int
    stratum: str
    total: int = 0
    eligible: int = 0
    eligible_partial: int = 0
    eligible_expected_exclusion: int = 0
    selected: list[int] = field(default_factory=list)
    selected_partial: list[int] = field(default_factory=list)
    selected_expected_exclusion: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class UniqueSnapshotFile:
    npr: Decimal | None
    coverage: float | None
    status: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def parse_decimal(value: Any, label: str, allow_blank: bool = False) -> Decimal | None:
    text = clean(value)
    if text == "":
        if allow_blank:
            return None
        raise ValueError(f"Missing decimal value for {label}")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal value for {label}: {text!r}") from exc
    if not parsed.is_finite():
        raise ValueError(f"Non-finite decimal value for {label}: {text!r}")
    return parsed


def parse_int(value: Any, label: str) -> int:
    text = clean(value)
    if text == "":
        raise ValueError(f"Missing integer value for {label}")
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {label}: {text!r}") from exc


def parse_float(value: Any, label: str, allow_blank: bool = False) -> float | None:
    text = clean(value)
    if text == "":
        if allow_blank:
            return None
        raise ValueError(f"Missing float value for {label}")
    try:
        parsed = float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid float value for {label}: {text!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"Non-finite float value for {label}: {text!r}")
    return parsed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_columns(path: Path, required: set[str], label: str) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader, None)
    if header is None:
        raise ValueError(f"{label} is empty: {path}")
    missing = required - set(header)
    if missing:
        raise ValueError(f"{label} is missing required columns: {sorted(missing)}")
    return header


def iter_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        yield from csv.DictReader(stream)


def atomic_csv_rows(rows: Iterable[Mapping[str, Any]], path: Path, columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as stream:
        tmp = Path(stream.name)
        writer = csv.DictWriter(stream, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    tmp.replace(path)


def atomic_json(payload: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False
    ) as stream:
        tmp = Path(stream.name)
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    tmp.replace(path)


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    observed: Any,
    expected: Any,
    note: str,
    severity: str = "hard",
) -> None:
    checks.append(
        {
            "check_name": name,
            "severity": severity,
            "passed": 1 if passed else 0,
            "observed": json.dumps(observed, sort_keys=True) if isinstance(observed, (dict, list)) else observed,
            "expected": json.dumps(expected, sort_keys=True) if isinstance(expected, (dict, list)) else expected,
            "note": note,
        }
    )


def build_threshold_specs(
    primary: Decimal,
    step: Decimal,
    radius: Decimal,
    legacy: Decimal,
) -> list[ThresholdSpec]:
    if step <= 0:
        raise ValueError("Grid step must be positive")
    if radius < 0:
        raise ValueError("Grid radius must be non-negative")
    quotient = radius / step
    if quotient != quotient.to_integral_value():
        raise ValueError("Grid radius must be an exact multiple of grid step")
    n_side = int(quotient)
    specs: list[ThresholdSpec] = []
    order = 0
    for offset in range(-n_side, n_side + 1):
        delta = step * Decimal(offset)
        threshold = primary + delta
        if offset < 0:
            threshold_id = f"grid_m{abs(offset) * int(step * 100):03d}"
        elif offset > 0:
            threshold_id = f"grid_p{offset * int(step * 100):03d}"
        else:
            threshold_id = "primary"
        role = "primary" if offset == 0 else "sensitivity_grid"
        note = "Frozen primary threshold" if offset == 0 else "Pre-specified symmetric sensitivity threshold"
        specs.append(ThresholdSpec(threshold_id, role, order, delta, threshold, note))
        order += 1
    specs.append(
        ThresholdSpec(
            "legacy_15183",
            "legacy_anchor",
            None,
            legacy - primary,
            legacy,
            "Legacy pre-overlap benchmark threshold; reported separately from the symmetric grid",
        )
    )
    ids = [item.threshold_id for item in specs]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Threshold IDs are not unique: {ids}")
    return specs


def normalized_stratum(time_index: int, event_index: int) -> str:
    if event_index <= 0:
        return "control"
    if time_index < event_index:
        return "treatment_pre"
    return "treatment_post"


def event_time_normalized(time_index: int, event_index: int) -> int | None:
    if event_index <= 0:
        return None
    return time_index - event_index


def is_partial_coverage(coverage: float | None) -> bool:
    return coverage is not None and coverage < 1.0 - 1e-12


def safe_ratio(num: int, den: int) -> float | str:
    return num / den if den > 0 else ""


def percentile(sorted_values: Sequence[float], q: float) -> float | str:
    if not sorted_values:
        return ""
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return sorted_values[lo]
    fraction = position - lo
    return sorted_values[lo] * (1.0 - fraction) + sorted_values[hi] * fraction


def distribution_row(scope: str, stratum: str, values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {column: "" for column in DISTRIBUTION_COLUMNS} | {"scope": scope, "stratum": stratum, "n": 0}
    ordered = sorted(values)
    return {
        "scope": scope,
        "stratum": stratum,
        "n": len(ordered),
        "mean": statistics.fmean(ordered),
        "min": ordered[0],
        "p01": percentile(ordered, 0.01),
        "p05": percentile(ordered, 0.05),
        "p10": percentile(ordered, 0.10),
        "p25": percentile(ordered, 0.25),
        "p50": percentile(ordered, 0.50),
        "p75": percentile(ordered, 0.75),
        "p90": percentile(ordered, 0.90),
        "p95": percentile(ordered, 0.95),
        "p99": percentile(ordered, 0.99),
        "max": ordered[-1],
    }


def validate_i01_summary(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        summary = json.load(stream)
    if clean(summary.get("script_version")) != EXPECTED_I01_SCRIPT_VERSION:
        raise ValueError(
            f"Unexpected I01 script version: {summary.get('script_version')!r}; expected {EXPECTED_I01_SCRIPT_VERSION!r}"
        )
    if int(summary.get("hard_check_failures", -1)) != 0:
        raise ValueError(f"I01 summary reports hard_check_failures={summary.get('hard_check_failures')}")
    status = clean(summary.get("status"))
    if status not in {"PASS", "PASS_WITH_EXPECTED_EXCLUSIONS"}:
        raise ValueError(f"I01 summary status is not a successful terminal state: {status!r}")
    return summary


def audit_input(
    input_path: Path,
    specs: list[ThresholdSpec],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    require_columns(input_path, INPUT_REQUIRED_COLUMNS, "I01 repo-month/file FUN+C_FUN NPR input")
    n_thresholds = len(specs)
    counters = ThresholdCounters(
        selected=[0] * n_thresholds,
        selected_partial=[0] * n_thresholds,
        selected_expected_exclusion=[0] * n_thresholds,
        selected_repos=[set() for _ in specs],
        selected_repo_months=[set() for _ in specs],
    )
    group_names = ["all", "control", "treatment_pre", "treatment_post", "treatment_all"]
    groups = {
        name: GroupCounters(
            selected=[0] * n_thresholds,
            selected_partial=[0] * n_thresholds,
            selected_expected_exclusion=[0] * n_thresholds,
        )
        for name in group_names
    }
    repo_months: dict[str, RepoMonthCounters] = {}
    unique_snapshot_files: dict[tuple[str, str, str], UniqueSnapshotFile] = {}
    repo_group: dict[str, bool] = {}
    status_counts: dict[str, int] = defaultdict(int)
    dataset_source_counts: dict[str, int] = defaultdict(int)
    distribution_values: dict[str, list[float]] = {name: [] for name in group_names}

    total_rows = 0
    eligible_rows = 0
    eligible_partial = 0
    eligible_expected_exclusion = 0
    unexpected_status_rows = 0
    unexpected_missing_rows = 0
    finite_status_mismatch_rows = 0
    coverage_status_mismatch_rows = 0
    threshold_equal_counts = [0] * n_thresholds

    for row in iter_csv(input_path):
        total_rows += 1
        repo_id = clean(row["repo_id"])
        source = clean(row["dataset_source"])
        repo_name = clean(row["repo_name"])
        repo_month = clean(row["repo_month"])
        time_index = parse_int(row["time_index"], f"row {total_rows} time_index")
        event_index = parse_int(row["event_index"], f"row {total_rows} event_index")
        stratum = normalized_stratum(time_index, event_index)
        treatment_group = event_index > 0
        if repo_id == "":
            raise ValueError(f"Missing repo_id at input row {total_rows}")
        if repo_month == "":
            raise ValueError(f"Missing repo_month at input row {total_rows}")

        previous_group = repo_group.get(repo_id)
        if previous_group is None:
            repo_group[repo_id] = treatment_group
        elif previous_group != treatment_group:
            raise ValueError(f"Repository {repo_id} changes treatment-group identity across months")

        repo_month_key = f"{repo_id}\x1f{repo_month}"
        rm = repo_months.get(repo_month_key)
        if rm is None:
            rm = RepoMonthCounters(
                repo_id=repo_id,
                dataset_source=source,
                repo_name=repo_name,
                repo_month=repo_month,
                time_index=time_index,
                event_index=event_index,
                stratum=stratum,
                selected=[0] * n_thresholds,
                selected_partial=[0] * n_thresholds,
                selected_expected_exclusion=[0] * n_thresholds,
            )
            repo_months[repo_month_key] = rm
        else:
            current_metadata = (source, repo_name, time_index, event_index, stratum)
            stored_metadata = (rm.dataset_source, rm.repo_name, rm.time_index, rm.event_index, rm.stratum)
            if current_metadata != stored_metadata:
                raise ValueError(
                    f"Inconsistent repo-month metadata for {repo_id}/{repo_month}: "
                    f"stored={stored_metadata}, observed={current_metadata}"
                )
        rm.total += 1

        status = clean(row["file_npr_fun_cfun_status"])
        status_counts[status] += 1
        dataset_source_counts[source] += 1
        if status not in EXPECTED_FILE_STATUSES:
            unexpected_status_rows += 1
        if status == "unexpected_missing_score":
            unexpected_missing_rows += 1

        npr = parse_decimal(row[METRIC_COLUMN], f"row {total_rows} {METRIC_COLUMN}", allow_blank=True)
        coverage = parse_float(row["fun_cfun_npr_coverage_ratio"], f"row {total_rows} fun_cfun_npr_coverage_ratio", allow_blank=True)
        finite_status = status in FINITE_FILE_STATUSES
        if (npr is not None) != finite_status:
            finite_status_mismatch_rows += 1

        expected_exclusion = status == "scored_with_expected_exclusions"
        partial = is_partial_coverage(coverage)
        if status == "scored" and (coverage is None or abs(coverage - 1.0) > 1e-12):
            coverage_status_mismatch_rows += 1
        if expected_exclusion and (coverage is None or not (0.0 < coverage < 1.0)):
            coverage_status_mismatch_rows += 1

        snapshot_key = (
            clean(row["snapshot_id"]),
            clean(row["relative_path"]),
            clean(row["file_sha256"]).casefold(),
        )
        unique_value = UniqueSnapshotFile(npr=npr, coverage=coverage, status=status)
        prior_unique = unique_snapshot_files.get(snapshot_key)
        if prior_unique is None:
            unique_snapshot_files[snapshot_key] = unique_value
        elif prior_unique != unique_value:
            raise ValueError(f"Repeated snapshot/file has inconsistent FUN+C_FUN NPR fields: {snapshot_key}")

        stratum_names = ["all", stratum]
        if treatment_group:
            stratum_names.append("treatment_all")
        for name in stratum_names:
            groups[name].total += 1

        if npr is None:
            continue

        eligible_rows += 1
        rm.eligible += 1
        if partial:
            eligible_partial += 1
            rm.eligible_partial += 1
        if expected_exclusion:
            eligible_expected_exclusion += 1
            rm.eligible_expected_exclusion += 1
        npr_float = float(npr)
        for name in stratum_names:
            groups[name].eligible += 1
            distribution_values[name].append(npr_float)
            if partial:
                groups[name].eligible_partial += 1
            if expected_exclusion:
                groups[name].eligible_expected_exclusion += 1

        for index, spec in enumerate(specs):
            if npr == spec.threshold:
                threshold_equal_counts[index] += 1
            if npr <= spec.threshold:
                continue
            counters.selected[index] += 1
            counters.selected_repos[index].add(repo_id)
            counters.selected_repo_months[index].add(repo_month_key)
            rm.selected[index] += 1
            if partial:
                counters.selected_partial[index] += 1
                rm.selected_partial[index] += 1
            if expected_exclusion:
                counters.selected_expected_exclusion[index] += 1
                rm.selected_expected_exclusion[index] += 1
            for name in stratum_names:
                groups[name].selected[index] += 1
                if partial:
                    groups[name].selected_partial[index] += 1
                if expected_exclusion:
                    groups[name].selected_expected_exclusion[index] += 1

    unique_eligible = [item for item in unique_snapshot_files.values() if item.npr is not None]
    unique_selected = [0] * n_thresholds
    unique_distribution = [float(item.npr) for item in unique_eligible if item.npr is not None]
    for item in unique_eligible:
        assert item.npr is not None
        for index, spec in enumerate(specs):
            if item.npr > spec.threshold:
                unique_selected[index] += 1

    unique_repo_month_group_counts = defaultdict(int)
    for rm in repo_months.values():
        unique_repo_month_group_counts[rm.stratum] += 1
    unique_repo_month_group_counts["all"] = len(repo_months)
    unique_repo_month_group_counts["treatment_all"] = (
        unique_repo_month_group_counts["treatment_pre"] + unique_repo_month_group_counts["treatment_post"]
    )

    control_repos = sum(1 for is_treatment in repo_group.values() if not is_treatment)
    treatment_repos = sum(1 for is_treatment in repo_group.values() if is_treatment)

    global_rows: list[dict[str, Any]] = []
    for index, spec in enumerate(specs):
        selected = counters.selected[index]
        selected_partial = counters.selected_partial[index]
        global_rows.append(
            spec.as_row()
            | {
                "repo_month_file_rows_total": total_rows,
                "eligible_finite_fun_cfun_rows": eligible_rows,
                "ineligible_rows": total_rows - eligible_rows,
                "selected_file_rows": selected,
                "selected_share_of_eligible": safe_ratio(selected, eligible_rows),
                "selected_share_of_all_python_rows": safe_ratio(selected, total_rows),
                "eligible_full_coverage_rows": eligible_rows - eligible_partial,
                "eligible_partial_coverage_rows": eligible_partial,
                "selected_full_coverage_rows": selected - selected_partial,
                "selected_partial_coverage_rows": selected_partial,
                "eligible_rows_with_expected_exclusions": eligible_expected_exclusion,
                "selected_rows_with_expected_exclusions": counters.selected_expected_exclusion[index],
                "unique_snapshot_files_total": len(unique_snapshot_files),
                "eligible_unique_snapshot_files": len(unique_eligible),
                "selected_unique_snapshot_files": unique_selected[index],
                "selected_unique_snapshot_file_share": safe_ratio(unique_selected[index], len(unique_eligible)),
                "repositories_with_selected_files": len(counters.selected_repos[index]),
                "repo_months_with_selected_files": len(counters.selected_repo_months[index]),
            }
        )

    group_rows: list[dict[str, Any]] = []
    for index, spec in enumerate(specs):
        for name in group_names:
            group = groups[name]
            group_rows.append(
                spec.as_row()
                | {
                    "stratum": name,
                    "repo_month_file_rows_total": group.total,
                    "eligible_finite_fun_cfun_rows": group.eligible,
                    "selected_file_rows": group.selected[index],
                    "selected_share_of_eligible": safe_ratio(group.selected[index], group.eligible),
                    "selected_share_of_all_python_rows": safe_ratio(group.selected[index], group.total),
                    "eligible_partial_coverage_rows": group.eligible_partial,
                    "selected_partial_coverage_rows": group.selected_partial[index],
                    "eligible_rows_with_expected_exclusions": group.eligible_expected_exclusion,
                    "selected_rows_with_expected_exclusions": group.selected_expected_exclusion[index],
                }
            )

    repo_month_rows: list[dict[str, Any]] = []
    sorted_repo_months = sorted(repo_months.values(), key=lambda item: (item.repo_id, item.repo_month))
    for index, spec in enumerate(specs):
        for rm in sorted_repo_months:
            treatment_group = 1 if rm.event_index > 0 else 0
            event_time = event_time_normalized(rm.time_index, rm.event_index)
            repo_month_rows.append(
                spec.as_row()
                | {
                    "repo_id": rm.repo_id,
                    "dataset_source": rm.dataset_source,
                    "repo_name": rm.repo_name,
                    "repo_month": rm.repo_month,
                    "time_index": rm.time_index,
                    "event_index": rm.event_index,
                    "event_time_normalized": "" if event_time is None else event_time,
                    "treatment_group": treatment_group,
                    "absorbing_treated": 1 if treatment_group and rm.time_index >= rm.event_index else 0,
                    "repo_month_file_rows_total": rm.total,
                    "eligible_finite_fun_cfun_rows": rm.eligible,
                    "selected_file_rows": rm.selected[index],
                    "selected_share_of_eligible": safe_ratio(rm.selected[index], rm.eligible),
                    "selected_share_of_all_python_rows": safe_ratio(rm.selected[index], rm.total),
                    "eligible_partial_coverage_rows": rm.eligible_partial,
                    "selected_partial_coverage_rows": rm.selected_partial[index],
                    "eligible_rows_with_expected_exclusions": rm.eligible_expected_exclusion,
                    "selected_rows_with_expected_exclusions": rm.selected_expected_exclusion[index],
                }
            )

    distribution_rows = [distribution_row("repo_month_file", name, distribution_values[name]) for name in group_names]
    distribution_rows.append(distribution_row("unique_snapshot_file", "all", unique_distribution))

    diagnostics = {
        "input_rows": total_rows,
        "eligible_finite_fun_cfun_rows": eligible_rows,
        "ineligible_rows": total_rows - eligible_rows,
        "unique_snapshot_files": len(unique_snapshot_files),
        "eligible_unique_snapshot_files": len(unique_eligible),
        "repo_months": len(repo_months),
        "repositories": len(repo_group),
        "control_repositories": control_repos,
        "treatment_repositories": treatment_repos,
        "repo_month_group_counts": dict(sorted(unique_repo_month_group_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "dataset_source_file_row_counts": dict(sorted(dataset_source_counts.items())),
        "eligible_partial_coverage_rows": eligible_partial,
        "eligible_rows_with_expected_exclusions": eligible_expected_exclusion,
        "unexpected_status_rows": unexpected_status_rows,
        "unexpected_missing_score_rows": unexpected_missing_rows,
        "finite_status_mismatch_rows": finite_status_mismatch_rows,
        "coverage_status_mismatch_rows": coverage_status_mismatch_rows,
        "rows_equal_threshold": {
            spec.threshold_id: threshold_equal_counts[index] for index, spec in enumerate(specs)
        },
    }
    return diagnostics, global_rows, group_rows, repo_month_rows, distribution_rows


def make_checks(
    specs: list[ThresholdSpec],
    diagnostics: Mapping[str, Any],
    global_rows: list[dict[str, Any]],
    group_rows: list[dict[str, Any]],
    repo_month_rows: list[dict[str, Any]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    grid = [spec for spec in specs if spec.threshold_role != "legacy_anchor"]
    legacy = [spec for spec in specs if spec.threshold_role == "legacy_anchor"]
    primary = [spec for spec in specs if spec.threshold_role == "primary"]

    add_check(checks, "threshold_grid_count", len(grid) == 21, len(grid), 21, "Symmetric grid must contain T plus ten thresholds on each side.")
    add_check(checks, "threshold_total_count_with_legacy", len(specs) == 22, len(specs), 22, "I02 must have the 21-point grid plus one named legacy anchor.")
    add_check(checks, "primary_threshold_count", len(primary) == 1, len(primary), 1, "Exactly one primary threshold is allowed.")
    if primary:
        add_check(checks, "primary_threshold_value", primary[0].threshold == DEFAULT_PRIMARY_THRESHOLD, decimal_text(primary[0].threshold), decimal_text(DEFAULT_PRIMARY_THRESHOLD), "Primary threshold is frozen before quality outcomes are consumed.")
    add_check(checks, "legacy_threshold_count", len(legacy) == 1, len(legacy), 1, "Exactly one legacy benchmark anchor is retained.")
    if legacy:
        add_check(checks, "legacy_threshold_value", legacy[0].threshold == DEFAULT_LEGACY_THRESHOLD, decimal_text(legacy[0].threshold), decimal_text(DEFAULT_LEGACY_THRESHOLD), "Legacy threshold is reported separately from the main sensitivity grid.")
    grid_values = [spec.threshold for spec in sorted(grid, key=lambda item: int(item.grid_order or 0))]
    add_check(checks, "grid_lower_bound", grid_values[0] == Decimal("1.071637"), decimal_text(grid_values[0]), "1.071637", "Lower bound must equal T-0.50.")
    add_check(checks, "grid_upper_bound", grid_values[-1] == Decimal("2.071637"), decimal_text(grid_values[-1]), "2.071637", "Upper bound must equal T+0.50.")
    step_ok = all((right - left) == DEFAULT_GRID_STEP for left, right in zip(grid_values, grid_values[1:]))
    add_check(checks, "grid_step", step_ok, [decimal_text(right - left) for left, right in zip(grid_values, grid_values[1:])], decimal_text(DEFAULT_GRID_STEP), "Every adjacent main-grid threshold must differ by exactly 0.05.")

    if args.strict_expected_counts:
        expected_pairs = [
            ("input_repo_month_file_rows", diagnostics["input_rows"], args.expected_input_rows),
            ("eligible_repo_month_file_rows", diagnostics["eligible_finite_fun_cfun_rows"], args.expected_eligible_rows),
            ("unique_snapshot_files", diagnostics["unique_snapshot_files"], args.expected_unique_snapshot_files),
            ("eligible_unique_snapshot_files", diagnostics["eligible_unique_snapshot_files"], args.expected_eligible_unique_snapshot_files),
            ("repo_months", diagnostics["repo_months"], args.expected_repo_months),
            ("repositories", diagnostics["repositories"], args.expected_repositories),
            ("control_repositories", diagnostics["control_repositories"], args.expected_control_repositories),
            ("treatment_repositories", diagnostics["treatment_repositories"], args.expected_treatment_repositories),
            ("control_repo_months", diagnostics["repo_month_group_counts"].get("control", 0), args.expected_control_repo_months),
            ("treatment_pre_repo_months", diagnostics["repo_month_group_counts"].get("treatment_pre", 0), args.expected_treatment_pre_repo_months),
            ("treatment_post_repo_months", diagnostics["repo_month_group_counts"].get("treatment_post", 0), args.expected_treatment_post_repo_months),
        ]
        for name, observed, expected in expected_pairs:
            add_check(checks, name, observed == expected, observed, expected, "Strict production-count reconciliation against the completed I01 FUN+C_FUN/Model A sample.")

        primary_row = next(row for row in global_rows if clean(row["threshold_id"]) == "primary")
        primary_expected_pairs = [
            ("primary_selected_file_rows", int(primary_row["selected_file_rows"]), args.expected_primary_selected_rows),
            ("primary_selected_unique_snapshot_files", int(primary_row["selected_unique_snapshot_files"]), args.expected_primary_selected_unique_snapshot_files),
            ("primary_selected_repositories", int(primary_row["repositories_with_selected_files"]), args.expected_primary_selected_repositories),
            ("primary_selected_repo_months", int(primary_row["repo_months_with_selected_files"]), args.expected_primary_selected_repo_months),
        ]
        for name, observed, expected in primary_expected_pairs:
            add_check(
                checks,
                name,
                observed == expected,
                observed,
                expected,
                "Strict regression gate for the frozen I01 combined-NPR primary-threshold support.",
            )

    add_check(checks, "unexpected_file_status_rows", diagnostics["unexpected_status_rows"] == 0, diagnostics["unexpected_status_rows"], 0, "I02 accepts only I01 v1 FUN+C_FUN file-status values.")
    add_check(checks, "unexpected_missing_score_rows", diagnostics["unexpected_missing_score_rows"] == 0, diagnostics["unexpected_missing_score_rows"], 0, "I01 unexpected_missing_score must remain zero before thresholding.")
    add_check(checks, "finite_status_consistency", diagnostics["finite_status_mismatch_rows"] == 0, diagnostics["finite_status_mismatch_rows"], 0, "Finite file NPR must occur exactly on scored/scored_with_expected_exclusions rows.")
    add_check(checks, "coverage_status_consistency", diagnostics["coverage_status_mismatch_rows"] == 0, diagnostics["coverage_status_mismatch_rows"], 0, "Coverage must be 1 for scored rows and strictly between 0 and 1 for scored_with_expected_exclusions rows.")

    global_by_id = {clean(row["threshold_id"]): row for row in global_rows}
    grid_selected = [int(global_by_id[spec.threshold_id]["selected_file_rows"]) for spec in sorted(grid, key=lambda item: int(item.grid_order or 0))]
    monotone = all(left >= right for left, right in zip(grid_selected, grid_selected[1:]))
    add_check(checks, "grid_selected_count_monotone", monotone, grid_selected, "non-increasing", "Selected file-row count must weakly decrease as the threshold increases.")

    if legacy:
        lower = next(spec for spec in grid if spec.threshold == Decimal("1.471637"))
        upper = next(spec for spec in grid if spec.threshold == Decimal("1.521637"))
        legacy_selected = int(global_by_id[legacy[0].threshold_id]["selected_file_rows"])
        lower_selected = int(global_by_id[lower.threshold_id]["selected_file_rows"])
        upper_selected = int(global_by_id[upper.threshold_id]["selected_file_rows"])
        bracket_ok = lower_selected >= legacy_selected >= upper_selected
        add_check(checks, "legacy_selected_count_bracket", bracket_ok, {"T-0.10": lower_selected, "legacy": legacy_selected, "T-0.05": upper_selected}, "T-0.10 >= legacy >= T-0.05", "The legacy 1.5183 threshold lies numerically between T-0.10 and T-0.05.")

    groups_by_threshold: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in group_rows:
        groups_by_threshold[clean(row["threshold_id"])][clean(row["stratum"])] = row
    for spec in specs:
        rows = groups_by_threshold[spec.threshold_id]
        selected_sum = sum(int(rows[name]["selected_file_rows"]) for name in ("control", "treatment_pre", "treatment_post"))
        global_selected = int(global_by_id[spec.threshold_id]["selected_file_rows"])
        add_check(checks, f"group_selected_reconcile::{spec.threshold_id}", selected_sum == global_selected, selected_sum, global_selected, "Control + treatment-pre + treatment-post selected rows must equal the global selected count.")

    repo_month_selected = defaultdict(int)
    for row in repo_month_rows:
        repo_month_selected[clean(row["threshold_id"])] += int(row["selected_file_rows"])
    for spec in specs:
        global_selected = int(global_by_id[spec.threshold_id]["selected_file_rows"])
        add_check(checks, f"repo_month_selected_reconcile::{spec.threshold_id}", repo_month_selected[spec.threshold_id] == global_selected, repo_month_selected[spec.threshold_id], global_selected, "Summed repo-month selected rows must equal the global selected count.")

    return checks


def self_test() -> None:
    specs = build_threshold_specs(
        DEFAULT_PRIMARY_THRESHOLD,
        DEFAULT_GRID_STEP,
        DEFAULT_GRID_RADIUS,
        DEFAULT_LEGACY_THRESHOLD,
    )
    assert len(specs) == 22
    grid = [spec for spec in specs if spec.threshold_role != "legacy_anchor"]
    assert grid[0].threshold == Decimal("1.071637")
    assert grid[10].threshold == DEFAULT_PRIMARY_THRESHOLD
    assert grid[-1].threshold == Decimal("2.071637")
    assert normalized_stratum(4, 0) == "control"
    assert normalized_stratum(4, 5) == "treatment_pre"
    assert normalized_stratum(5, 5) == "treatment_post"
    assert event_time_normalized(7, 5) == 2
    assert event_time_normalized(7, 0) is None
    primary = next(spec for spec in specs if spec.threshold_role == "primary")
    assert Decimal("1.571637") <= primary.threshold
    assert not (Decimal("1.571637") > primary.threshold)
    assert Decimal("1.571638") > primary.threshold
    legacy = next(spec for spec in specs if spec.threshold_role == "legacy_anchor")
    assert Decimal("1.471637") < legacy.threshold < Decimal("1.521637")
    assert is_partial_coverage(0.999)
    assert not is_partial_coverage(1.0)
    values = [1.0, 2.0, 3.0]
    assert percentile(values, 0.5) == 2.0
    print("audit_fun_cfun_npr_threshold_grid self-test: PASS")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path, help="I01 python_fun_cfun_repo_month_file_npr_scores.csv")
    parser.add_argument("--i01-summary-file", type=Path, help="I01 summary.json adjacent to the input artifact")
    parser.add_argument("--output-dir", type=Path, help="I02 output directory")
    parser.add_argument("--primary-threshold", type=Decimal, default=DEFAULT_PRIMARY_THRESHOLD)
    parser.add_argument("--grid-step", type=Decimal, default=DEFAULT_GRID_STEP)
    parser.add_argument("--grid-radius", type=Decimal, default=DEFAULT_GRID_RADIUS)
    parser.add_argument("--legacy-threshold", type=Decimal, default=DEFAULT_LEGACY_THRESHOLD)
    parser.add_argument("--strict-expected-counts", action="store_true")
    parser.add_argument("--expected-input-rows", type=int, default=510297)
    parser.add_argument("--expected-eligible-rows", type=int, default=359057)
    parser.add_argument("--expected-unique-snapshot-files", type=int, default=494592)
    parser.add_argument("--expected-eligible-unique-snapshot-files", type=int, default=347173)
    parser.add_argument("--expected-repo-months", type=int, default=1954)
    parser.add_argument("--expected-repositories", type=int, default=167)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repo-months", type=int, default=1040)
    parser.add_argument("--expected-treatment-pre-repo-months", type=int, default=551)
    parser.add_argument("--expected-treatment-post-repo-months", type=int, default=363)
    parser.add_argument("--expected-primary-selected-rows", type=int, default=17071)
    parser.add_argument("--expected-primary-selected-unique-snapshot-files", type=int, default=15726)
    parser.add_argument("--expected-primary-selected-repositories", type=int, default=123)
    parser.add_argument("--expected-primary-selected-repo-months", type=int, default=1411)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if args.input_file is None or args.i01_summary_file is None or args.output_dir is None:
        raise SystemExit("--input-file, --i01-summary-file, and --output-dir are required unless --self-test is used")

    args.input_file = args.input_file.expanduser().resolve()
    args.i01_summary_file = args.i01_summary_file.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()
    for path in (args.input_file, args.i01_summary_file):
        if not path.is_file():
            raise FileNotFoundError(path)

    if args.primary_threshold != DEFAULT_PRIMARY_THRESHOLD:
        raise ValueError(f"I02 v1 freezes primary threshold at {DEFAULT_PRIMARY_THRESHOLD}; observed override={args.primary_threshold}")
    if args.grid_step != DEFAULT_GRID_STEP:
        raise ValueError(f"I02 v1 freezes grid step at {DEFAULT_GRID_STEP}; observed override={args.grid_step}")
    if args.grid_radius != DEFAULT_GRID_RADIUS:
        raise ValueError(f"I02 v1 freezes grid radius at {DEFAULT_GRID_RADIUS}; observed override={args.grid_radius}")
    if args.legacy_threshold != DEFAULT_LEGACY_THRESHOLD:
        raise ValueError(f"I02 v1 freezes legacy threshold at {DEFAULT_LEGACY_THRESHOLD}; observed override={args.legacy_threshold}")

    started = utc_now()
    i01_summary = validate_i01_summary(args.i01_summary_file)
    specs = build_threshold_specs(args.primary_threshold, args.grid_step, args.grid_radius, args.legacy_threshold)
    diagnostics, global_rows, group_rows, repo_month_rows, distribution_rows = audit_input(args.input_file, specs)
    checks = make_checks(specs, diagnostics, global_rows, group_rows, repo_month_rows, args)
    hard_failures = [row for row in checks if row["severity"] == "hard" and int(row["passed"]) == 0]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    spec_path = args.output_dir / "fun_cfun_npr_threshold_spec.csv"
    global_path = args.output_dir / "fun_cfun_npr_threshold_audit.csv"
    group_path = args.output_dir / "fun_cfun_npr_threshold_by_treatment_timing.csv"
    repo_month_path = args.output_dir / "fun_cfun_npr_threshold_repo_month_audit.csv"
    distribution_path = args.output_dir / "fun_cfun_npr_distribution_summary.csv"
    checks_path = args.output_dir / "fun_cfun_npr_threshold_checks.csv"

    atomic_csv_rows((spec.as_row() for spec in specs), spec_path, THRESHOLD_SPEC_COLUMNS)
    atomic_csv_rows(global_rows, global_path, GLOBAL_AUDIT_COLUMNS)
    atomic_csv_rows(group_rows, group_path, GROUP_AUDIT_COLUMNS)
    atomic_csv_rows(repo_month_rows, repo_month_path, REPO_MONTH_AUDIT_COLUMNS)
    atomic_csv_rows(distribution_rows, distribution_path, DISTRIBUTION_COLUMNS)
    atomic_csv_rows(checks, checks_path, CHECK_COLUMNS)

    global_by_id = {clean(row["threshold_id"]): row for row in global_rows}
    primary_row = global_by_id["primary"]
    legacy_row = global_by_id["legacy_15183"]
    summary = {
        "status": "PASS" if not hard_failures else "FAIL",
        "script_version": SCRIPT_VERSION,
        "started_utc": started,
        "completed_utc": utc_now(),
        "quality_outcome_inputs_consumed": False,
        "methodology": {
            "metric": METRIC_COLUMN,
            "comparison_operator": COMPARISON_OPERATOR,
            "primary_threshold": decimal_text(DEFAULT_PRIMARY_THRESHOLD),
            "grid_step": decimal_text(DEFAULT_GRID_STEP),
            "grid_radius": decimal_text(DEFAULT_GRID_RADIUS),
            "grid_points": 21,
            "legacy_threshold": decimal_text(DEFAULT_LEGACY_THRESHOLD),
            "threshold_total_including_legacy": 22,
            "treatment_group": "event_index > 0",
            "event_time_normalized": "time_index - event_index for treatment repositories",
            "absorbing_treated": "event_index > 0 and time_index >= event_index",
            "legacy_treatment_flags_used": False,
            "threshold_selection_note": "The previously frozen SC2-7B FUN threshold/grid is transferred unchanged to FUN+C_FUN and audited without reading SonarQube or any quality outcome; I02 performs no FUN+C_FUN recalibration.",
        },
        "input": diagnostics,
        "i01": {
            "status": i01_summary.get("status"),
            "script_version": i01_summary.get("script_version"),
            "hard_check_failures": i01_summary.get("hard_check_failures"),
        },
        "primary_threshold_result": primary_row,
        "legacy_threshold_result": legacy_row,
        "hard_check_failures": len(hard_failures),
        "hard_check_failure_names": [clean(row["check_name"]) for row in hard_failures],
        "outputs": {
            "threshold_spec": str(spec_path),
            "global_threshold_audit": str(global_path),
            "treatment_timing_audit": str(group_path),
            "repo_month_threshold_audit": str(repo_month_path),
            "distribution_summary": str(distribution_path),
            "checks": str(checks_path),
        },
    }
    atomic_json(summary, args.output_dir / "summary.json")
    atomic_json(
        {
            "script_version": SCRIPT_VERSION,
            "created_utc": utc_now(),
            "inputs": {
                "i01_repo_month_file_npr": str(args.input_file),
                "i01_repo_month_file_npr_sha256": sha256_file(args.input_file),
                "i01_summary": str(args.i01_summary_file),
                "i01_summary_sha256": sha256_file(args.i01_summary_file),
            },
            "frozen_thresholds": [spec.as_row() for spec in specs],
            "quality_outcome_inputs_consumed": False,
        },
        args.output_dir / "metadata.json",
    )

    print("=" * 80)
    print("run-x-i02 FUN+C_FUN file-NPR threshold-grid audit")
    print(f"Status:                              {summary['status']}")
    print(f"Input repo-month/file rows:          {diagnostics['input_rows']}")
    print(f"Eligible finite FUN+C_FUN NPR rows:    {diagnostics['eligible_finite_fun_cfun_rows']}")
    print(f"Unique snapshot/files:               {diagnostics['unique_snapshot_files']}")
    print(f"Eligible unique snapshot/files:      {diagnostics['eligible_unique_snapshot_files']}")
    print(f"Repo-months:                         {diagnostics['repo_months']}")
    print(f"Repositories:                        {diagnostics['repositories']}")
    print(f"Control/treatment repositories:      {diagnostics['control_repositories']} / {diagnostics['treatment_repositories']}")
    print(
        "Control / treatment-pre / post:     "
        f"{diagnostics['repo_month_group_counts'].get('control', 0)} / "
        f"{diagnostics['repo_month_group_counts'].get('treatment_pre', 0)} / "
        f"{diagnostics['repo_month_group_counts'].get('treatment_post', 0)}"
    )
    print(f"Thresholds (grid + legacy):          21 + 1")
    print(f"Primary threshold:                   {decimal_text(DEFAULT_PRIMARY_THRESHOLD)}")
    print(f"Primary selected rows:               {primary_row['selected_file_rows']}")
    print(f"Primary selected share eligible:     {float(primary_row['selected_share_of_eligible']):.6f}")
    print(f"Legacy threshold:                    {decimal_text(DEFAULT_LEGACY_THRESHOLD)}")
    print(f"Legacy selected rows:                {legacy_row['selected_file_rows']}")
    print(f"Hard QC failures:                    {len(hard_failures)}")
    print(f"Threshold spec:                      {spec_path}")
    print(f"Global audit:                        {global_path}")
    print(f"Treatment-timing audit:              {group_path}")
    print(f"Repo-month audit:                    {repo_month_path}")
    print(f"Distribution summary:                {distribution_path}")
    print("=" * 80)
    return 0 if not hard_failures else 5


if __name__ == "__main__":
    raise SystemExit(main())
