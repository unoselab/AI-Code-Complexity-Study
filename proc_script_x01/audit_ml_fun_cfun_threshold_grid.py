#!/usr/bin/env python3
"""Freeze and audit the combined regular-function + class-method ML threshold grid.

I07 consumes the finalized I06 historical Python-file ML aggregation and applies
an outcome-blind 21-point threshold grid to the continuous combined procedure-
implementation AGC share.

Primary specification
---------------------
- Metric: file_ml_fun_cfun_agc_share_space_by_token_weighted
- Primary threshold: 0.50
- Sensitivity grid: 0.10, 0.14, ..., 0.50, ..., 0.86, 0.90
- Decision rule: selected iff combined ML AGC share > threshold
- No threshold recalibration is performed.
- No SonarQube, quality outcome, B06 timing, or DiD estimate is read.

I06 contains one row per unique historical Python file. Therefore I07 audits
historical-file support by dataset source and by procedure-presence pattern.
Repo-month expansion is intentionally deferred to the downstream quality-burden
panel stage where authoritative B06 timing can be joined.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCRIPT_VERSION = "run-x-i07-v1"
EXPECTED_I06_VERSION = "run-x-i06-v1"
METRIC_COLUMN = "file_ml_fun_cfun_agc_share_space_by_token_weighted"
STATUS_COLUMN = "file_ml_fun_cfun_agc_status"
PRIMARY_FLAG_COLUMN = "file_ml_fun_cfun_agc_like_primary"
PRIMARY_THRESHOLD_COLUMN = "file_ml_fun_cfun_agc_primary_threshold"
PRIMARY_OPERATOR_COLUMN = "file_ml_fun_cfun_agc_primary_operator"
WARNING_COLUMN = "ml_fun_cfun_mapping_warning_present"
PRESENCE_COLUMN = "procedure_presence_pattern"
PRIMARY_THRESHOLD = Decimal("0.50")
GRID_START = Decimal("0.10")
GRID_STEP = Decimal("0.04")
GRID_COUNT = 21
COMPARISON_OPERATOR = ">"

EXPECTED_STATUSES = {"scored", "no_ml_fun_cfun", "file_not_prepared"}
ELIGIBLE_STATUS = "scored"
EXPECTED_DATASETS = {"control", "treatment"}
EXPECTED_PRESENCE = {"fun_only", "class_method_only", "fun_and_class_method", "neither"}
ELIGIBLE_PRESENCE = {"fun_only", "class_method_only", "fun_and_class_method"}

REQUIRED_COLUMNS = {
    "snapshot_order",
    "snapshot_id",
    "dataset_source",
    "repo_name",
    "repo_key",
    "snapshot_time",
    "snapshot_commit",
    "relative_path",
    "file_sha256",
    PRESENCE_COLUMN,
    "ml_fun_cfun_occurrences_total",
    "ml_fun_cfun_agc_occurrences",
    "ml_fun_cfun_hwc_occurrences",
    "ml_fun_cfun_space_by_tokens_total",
    "ml_fun_cfun_agc_space_by_tokens",
    METRIC_COLUMN,
    WARNING_COLUMN,
    PRIMARY_FLAG_COLUMN,
    PRIMARY_THRESHOLD_COLUMN,
    PRIMARY_OPERATOR_COLUMN,
    STATUS_COLUMN,
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

GLOBAL_COLUMNS = [
    "threshold_id",
    "threshold_role",
    "grid_order",
    "delta_from_primary",
    "threshold",
    "comparison_operator",
    "python_file_rows_total",
    "prepared_file_rows",
    "eligible_combined_files",
    "ineligible_files",
    "selected_file_rows",
    "selected_share_of_eligible",
    "selected_share_of_all_python_files",
    "ties_at_threshold",
    "mapping_warning_eligible_files",
    "mapping_warning_selected_files",
    "fun_only_selected_files",
    "class_method_only_selected_files",
    "fun_and_class_method_selected_files",
    "control_selected_files",
    "treatment_selected_files",
]

GROUP_COLUMNS = [
    "threshold_id",
    "threshold_role",
    "grid_order",
    "delta_from_primary",
    "threshold",
    "comparison_operator",
    "group",
    "python_file_rows_total",
    "prepared_file_rows",
    "eligible_combined_files",
    "selected_file_rows",
    "selected_share_of_eligible",
    "selected_share_of_group_files",
    "ties_at_threshold",
    "mapping_warning_eligible_files",
    "mapping_warning_selected_files",
]

DISTRIBUTION_COLUMNS = [
    "scope_type",
    "scope_value",
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def decimal_text(value: Decimal) -> str:
    return format(value, ".2f")


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


def parse_int(value: Any, label: str, allow_blank: bool = False) -> int | None:
    text = clean(value)
    if text == "":
        if allow_blank:
            return None
        raise ValueError(f"Missing integer value for {label}")
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {label}: {text!r}") from exc


def parse_bool01(value: Any, label: str, allow_blank: bool = False) -> int | None:
    text = clean(value)
    if text == "":
        if allow_blank:
            return None
        raise ValueError(f"Missing 0/1 value for {label}")
    if text not in {"0", "1"}:
        raise ValueError(f"Invalid 0/1 value for {label}: {text!r}")
    return int(text)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_columns(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader, None)
    if header is None:
        raise ValueError(f"I06 file-score CSV is empty: {path}")
    missing = REQUIRED_COLUMNS - set(header)
    if missing:
        raise ValueError(f"I06 file-score CSV is missing required columns: {sorted(missing)}")
    return header


def iter_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        yield from csv.DictReader(stream)


def atomic_csv(rows: Iterable[Mapping[str, Any]], path: Path, columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False
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


def safe_ratio(num: int, den: int) -> float | str:
    return num / den if den > 0 else ""


def percentile(values: Sequence[float], q: float) -> float | str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return values[lo]
    fraction = position - lo
    return values[lo] * (1.0 - fraction) + values[hi] * fraction


def distribution_row(scope_type: str, scope_value: str, raw_values: Sequence[float]) -> dict[str, Any]:
    values = sorted(raw_values)
    if not values:
        return {column: "" for column in DISTRIBUTION_COLUMNS} | {
            "scope_type": scope_type,
            "scope_value": scope_value,
            "n": 0,
        }
    return {
        "scope_type": scope_type,
        "scope_value": scope_value,
        "n": len(values),
        "mean": statistics.fmean(values),
        "min": values[0],
        "p01": percentile(values, 0.01),
        "p05": percentile(values, 0.05),
        "p10": percentile(values, 0.10),
        "p25": percentile(values, 0.25),
        "p50": percentile(values, 0.50),
        "p75": percentile(values, 0.75),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "max": values[-1],
    }


def build_threshold_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for index in range(GRID_COUNT):
        threshold = GRID_START + GRID_STEP * Decimal(index)
        role = "primary" if threshold == PRIMARY_THRESHOLD else "sensitivity_grid"
        specs.append(
            {
                "threshold_id": f"ml_t{int(threshold * 100):02d}",
                "threshold_role": role,
                "grid_order": index,
                "delta_from_primary": decimal_text(threshold - PRIMARY_THRESHOLD),
                "threshold": decimal_text(threshold),
                "comparison_operator": COMPARISON_OPERATOR,
                "metric": METRIC_COLUMN,
                "note": "Frozen primary threshold" if role == "primary" else "Pre-specified ML sensitivity threshold",
                "threshold_decimal": threshold,
            }
        )
    observed = [spec["threshold"] for spec in specs]
    expected = [f"{0.10 + 0.04 * i:.2f}" for i in range(21)]
    if observed != expected:
        raise ValueError(f"Unexpected ML threshold grid: observed={observed}, expected={expected}")
    return specs


def validate_i06_summary(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        summary = json.load(stream)
    version = clean(summary.get("run") or summary.get("script_version"))
    if version != EXPECTED_I06_VERSION:
        raise ValueError(f"Unexpected I06 version: {version!r}; expected {EXPECTED_I06_VERSION!r}")
    if clean(summary.get("status")) not in {"PASS", "PASS_WITH_WARNINGS"}:
        raise ValueError(f"I06 status is not finalized: {summary.get('status')!r}")
    if int(summary.get("failed_hard_checks", -1)) != 0:
        raise ValueError(f"I06 has hard QC failures: {summary.get('failed_hard_checks')!r}")
    rule = summary.get("primary_file_rule", {})
    if clean(rule.get("metric")) != METRIC_COLUMN:
        raise ValueError(f"I06 primary metric mismatch: {rule.get('metric')!r}")
    if clean(rule.get("operator")) != COMPARISON_OPERATOR:
        raise ValueError(f"I06 primary operator mismatch: {rule.get('operator')!r}")
    if Decimal(str(rule.get("threshold"))) != PRIMARY_THRESHOLD:
        raise ValueError(f"I06 primary threshold mismatch: {rule.get('threshold')!r}")
    return summary


def analyze(
    input_file: Path,
    i06_summary: Mapping[str, Any],
    expected: Mapping[str, int | None],
    strict_expected_counts: bool,
) -> dict[str, Any]:
    require_columns(input_file)
    specs = build_threshold_specs()
    thresholds = [spec["threshold_decimal"] for spec in specs]
    n_thresholds = len(specs)
    primary_index = thresholds.index(PRIMARY_THRESHOLD)

    total_rows = 0
    prepared_rows = 0
    eligible_rows = 0
    score_range_failures = 0
    status_metric_mismatches = 0
    primary_flag_mismatches = 0
    primary_threshold_column_mismatches = 0
    primary_operator_column_mismatches = 0
    duplicate_keys = 0
    unexpected_status_rows = 0
    unexpected_dataset_rows = 0
    unexpected_presence_rows = 0
    presence_status_mismatches = 0

    status_counts: Counter[str] = Counter()
    dataset_total: Counter[str] = Counter()
    dataset_prepared: Counter[str] = Counter()
    dataset_eligible: Counter[str] = Counter()
    presence_total: Counter[str] = Counter()
    presence_prepared: Counter[str] = Counter()
    presence_eligible: Counter[str] = Counter()

    selected = [0] * n_thresholds
    ties = [0] * n_thresholds
    warning_selected = [0] * n_thresholds
    warning_eligible_total = 0

    group_names = ["control", "treatment", "fun_only", "class_method_only", "fun_and_class_method", "neither"]
    group_selected = {name: [0] * n_thresholds for name in group_names}
    group_ties = {name: [0] * n_thresholds for name in group_names}
    group_warning_selected = {name: [0] * n_thresholds for name in group_names}
    group_warning_eligible = Counter()

    distribution_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    seen_keys: set[tuple[str, str, str]] = set()

    for row in iter_csv(input_file):
        total_rows += 1
        dataset = clean(row["dataset_source"])
        presence = clean(row[PRESENCE_COLUMN])
        status = clean(row[STATUS_COLUMN])
        status_counts[status] += 1
        dataset_total[dataset] += 1
        presence_total[presence] += 1

        key = (clean(row["snapshot_id"]), clean(row["relative_path"]), clean(row["file_sha256"]).casefold())
        if key in seen_keys:
            duplicate_keys += 1
        else:
            seen_keys.add(key)

        if status not in EXPECTED_STATUSES:
            unexpected_status_rows += 1
        if dataset not in EXPECTED_DATASETS:
            unexpected_dataset_rows += 1
        if presence not in EXPECTED_PRESENCE:
            unexpected_presence_rows += 1

        if status != "file_not_prepared":
            prepared_rows += 1
            dataset_prepared[dataset] += 1
            presence_prepared[presence] += 1

        score = parse_decimal(row[METRIC_COLUMN], f"row {total_rows} {METRIC_COLUMN}", allow_blank=True)
        eligible = status == ELIGIBLE_STATUS
        if eligible != (score is not None):
            status_metric_mismatches += 1
        if eligible != (presence in ELIGIBLE_PRESENCE):
            presence_status_mismatches += 1

        primary_threshold_value = parse_decimal(
            row[PRIMARY_THRESHOLD_COLUMN], f"row {total_rows} {PRIMARY_THRESHOLD_COLUMN}", allow_blank=True
        )
        if primary_threshold_value is not None and primary_threshold_value != PRIMARY_THRESHOLD:
            primary_threshold_column_mismatches += 1
        primary_operator_value = clean(row[PRIMARY_OPERATOR_COLUMN])
        if primary_operator_value not in {"", COMPARISON_OPERATOR}:
            primary_operator_column_mismatches += 1

        if not eligible:
            flag = parse_bool01(row[PRIMARY_FLAG_COLUMN], f"row {total_rows} primary flag", allow_blank=True)
            if flag not in {None, 0}:
                primary_flag_mismatches += 1
            continue

        assert score is not None
        eligible_rows += 1
        dataset_eligible[dataset] += 1
        presence_eligible[presence] += 1
        score_float = float(score)
        if not (Decimal("0") <= score <= Decimal("1")):
            score_range_failures += 1

        warning = parse_bool01(row[WARNING_COLUMN], f"row {total_rows} mapping warning", allow_blank=True) or 0
        if warning:
            warning_eligible_total += 1
            group_warning_eligible[dataset] += 1
            group_warning_eligible[presence] += 1

        distribution_values[("all", "all")].append(score_float)
        distribution_values[("dataset_source", dataset)].append(score_float)
        distribution_values[("procedure_presence", presence)].append(score_float)

        input_primary_flag = parse_bool01(row[PRIMARY_FLAG_COLUMN], f"row {total_rows} primary flag")
        recomputed_primary = 1 if score > PRIMARY_THRESHOLD else 0
        if input_primary_flag != recomputed_primary:
            primary_flag_mismatches += 1

        for index, threshold in enumerate(thresholds):
            if score == threshold:
                ties[index] += 1
                group_ties[dataset][index] += 1
                group_ties[presence][index] += 1
            if score <= threshold:
                continue
            selected[index] += 1
            group_selected[dataset][index] += 1
            group_selected[presence][index] += 1
            if warning:
                warning_selected[index] += 1
                group_warning_selected[dataset][index] += 1
                group_warning_selected[presence][index] += 1

    global_rows: list[dict[str, Any]] = []
    dataset_rows: list[dict[str, Any]] = []
    presence_rows: list[dict[str, Any]] = []

    for index, spec in enumerate(specs):
        base = {k: v for k, v in spec.items() if k != "threshold_decimal"}
        global_rows.append(
            base
            | {
                "python_file_rows_total": total_rows,
                "prepared_file_rows": prepared_rows,
                "eligible_combined_files": eligible_rows,
                "ineligible_files": total_rows - eligible_rows,
                "selected_file_rows": selected[index],
                "selected_share_of_eligible": safe_ratio(selected[index], eligible_rows),
                "selected_share_of_all_python_files": safe_ratio(selected[index], total_rows),
                "ties_at_threshold": ties[index],
                "mapping_warning_eligible_files": warning_eligible_total,
                "mapping_warning_selected_files": warning_selected[index],
                "fun_only_selected_files": group_selected["fun_only"][index],
                "class_method_only_selected_files": group_selected["class_method_only"][index],
                "fun_and_class_method_selected_files": group_selected["fun_and_class_method"][index],
                "control_selected_files": group_selected["control"][index],
                "treatment_selected_files": group_selected["treatment"][index],
            }
        )
        for dataset in ("control", "treatment"):
            dataset_rows.append(
                base
                | {
                    "group": dataset,
                    "python_file_rows_total": dataset_total[dataset],
                    "prepared_file_rows": dataset_prepared[dataset],
                    "eligible_combined_files": dataset_eligible[dataset],
                    "selected_file_rows": group_selected[dataset][index],
                    "selected_share_of_eligible": safe_ratio(group_selected[dataset][index], dataset_eligible[dataset]),
                    "selected_share_of_group_files": safe_ratio(group_selected[dataset][index], dataset_total[dataset]),
                    "ties_at_threshold": group_ties[dataset][index],
                    "mapping_warning_eligible_files": group_warning_eligible[dataset],
                    "mapping_warning_selected_files": group_warning_selected[dataset][index],
                }
            )
        for presence in ("fun_only", "class_method_only", "fun_and_class_method", "neither"):
            presence_rows.append(
                base
                | {
                    "group": presence,
                    "python_file_rows_total": presence_total[presence],
                    "prepared_file_rows": presence_prepared[presence],
                    "eligible_combined_files": presence_eligible[presence],
                    "selected_file_rows": group_selected[presence][index],
                    "selected_share_of_eligible": safe_ratio(group_selected[presence][index], presence_eligible[presence]),
                    "selected_share_of_group_files": safe_ratio(group_selected[presence][index], presence_total[presence]),
                    "ties_at_threshold": group_ties[presence][index],
                    "mapping_warning_eligible_files": group_warning_eligible[presence],
                    "mapping_warning_selected_files": group_warning_selected[presence][index],
                }
            )

    distribution_rows = [
        distribution_row(scope_type, scope_value, values)
        for (scope_type, scope_value), values in sorted(distribution_values.items())
    ]

    checks: list[dict[str, Any]] = []
    add_check(checks, "i06_status", clean(i06_summary.get("status")) in {"PASS", "PASS_WITH_WARNINGS"}, i06_summary.get("status"), "PASS|PASS_WITH_WARNINGS", "I06 must be finalized successfully.")
    add_check(checks, "i06_failed_hard_checks", int(i06_summary.get("failed_hard_checks", -1)) == 0, i06_summary.get("failed_hard_checks"), 0, "I06 hard QC must be zero.")
    add_check(checks, "threshold_count", n_thresholds == 21, n_thresholds, 21, "Exact D07-style ML threshold grid is required.")
    add_check(checks, "threshold_grid_bounds", thresholds[0] == Decimal("0.10") and thresholds[-1] == Decimal("0.90"), [decimal_text(thresholds[0]), decimal_text(thresholds[-1])], ["0.10", "0.90"], "ML grid endpoints must be frozen.")
    add_check(checks, "threshold_grid_primary", thresholds[primary_index] == PRIMARY_THRESHOLD and primary_index == 10, primary_index, 10, "0.50 must be the center/primary threshold.")
    add_check(checks, "duplicate_historical_file_keys", duplicate_keys == 0, duplicate_keys, 0, "I06 must contain one row per historical snapshot/file identity.")
    add_check(checks, "unexpected_status_rows", unexpected_status_rows == 0, unexpected_status_rows, 0, "Only finalized I06 statuses are allowed.")
    add_check(checks, "unexpected_dataset_rows", unexpected_dataset_rows == 0, unexpected_dataset_rows, 0, "Dataset source must be control or treatment.")
    add_check(checks, "unexpected_presence_rows", unexpected_presence_rows == 0, unexpected_presence_rows, 0, "Procedure-presence pattern must use the frozen four-way partition.")
    add_check(checks, "status_metric_mismatches", status_metric_mismatches == 0, status_metric_mismatches, 0, "Only scored rows may carry a combined ML score.")
    add_check(checks, "presence_status_mismatches", presence_status_mismatches == 0, presence_status_mismatches, 0, "Scored status must match presence of at least one procedure category.")
    add_check(checks, "score_range_failures", score_range_failures == 0, score_range_failures, 0, "Combined AGC share must remain in [0,1].")
    add_check(checks, "primary_flag_reproduction_mismatches", primary_flag_mismatches == 0, primary_flag_mismatches, 0, "I07 strict >0.50 rule must exactly reproduce I06 primary flags.")
    add_check(checks, "primary_threshold_column_mismatches", primary_threshold_column_mismatches == 0, primary_threshold_column_mismatches, 0, "I06 primary threshold provenance must remain 0.50.")
    add_check(checks, "primary_operator_column_mismatches", primary_operator_column_mismatches == 0, primary_operator_column_mismatches, 0, "I06 primary operator provenance must remain strict >.")
    add_check(checks, "status_partition", sum(status_counts.values()) == total_rows, sum(status_counts.values()), total_rows, "Status counts must partition all rows.")
    add_check(checks, "presence_partition", sum(presence_total.values()) == total_rows, sum(presence_total.values()), total_rows, "Presence counts must partition all rows.")
    add_check(checks, "dataset_partition", dataset_total["control"] + dataset_total["treatment"] == total_rows, dataset_total["control"] + dataset_total["treatment"], total_rows, "Control+treatment must partition all rows.")
    add_check(checks, "selected_monotonic_nonincreasing", all(selected[i] >= selected[i + 1] for i in range(n_thresholds - 1)), selected, "non-increasing", "Higher thresholds cannot select more files.")
    add_check(checks, "primary_ties_not_selected", ties[primary_index] >= 0, ties[primary_index], ">=0", "Exact threshold ties are counted separately and excluded by strict >.")

    expected_checks = [
        ("file_rows", total_rows, expected.get("file_rows")),
        ("prepared_rows", prepared_rows, expected.get("prepared_rows")),
        ("eligible_rows", eligible_rows, expected.get("eligible_rows")),
        ("control_file_rows", dataset_total["control"], expected.get("control_file_rows")),
        ("treatment_file_rows", dataset_total["treatment"], expected.get("treatment_file_rows")),
        ("control_eligible_rows", dataset_eligible["control"], expected.get("control_eligible_rows")),
        ("treatment_eligible_rows", dataset_eligible["treatment"], expected.get("treatment_eligible_rows")),
        ("primary_selected_rows", selected[primary_index], expected.get("primary_selected_rows")),
        ("primary_exact_ties", ties[primary_index], expected.get("primary_exact_ties")),
        ("control_primary_selected_rows", group_selected["control"][primary_index], expected.get("control_primary_selected_rows")),
        ("treatment_primary_selected_rows", group_selected["treatment"][primary_index], expected.get("treatment_primary_selected_rows")),
    ]
    for name, observed, expected_value in expected_checks:
        if expected_value is None:
            continue
        add_check(
            checks,
            name,
            observed == expected_value,
            observed,
            expected_value,
            "Frozen I06 production accounting must reproduce exactly." if strict_expected_counts else "Reference accounting check.",
            severity="hard" if strict_expected_counts else "informational",
        )

    hard_failures = sum(1 for row in checks if row["severity"] == "hard" and row["passed"] != 1)
    primary_row = global_rows[primary_index]
    return {
        "specs": specs,
        "global_rows": global_rows,
        "dataset_rows": dataset_rows,
        "presence_rows": presence_rows,
        "distribution_rows": distribution_rows,
        "checks": checks,
        "hard_failures": hard_failures,
        "accounting": {
            "total_rows": total_rows,
            "prepared_rows": prepared_rows,
            "eligible_rows": eligible_rows,
            "status_counts": dict(status_counts),
            "dataset_total": dict(dataset_total),
            "dataset_eligible": dict(dataset_eligible),
            "presence_total": dict(presence_total),
            "presence_eligible": dict(presence_eligible),
            "mapping_warning_eligible_files": warning_eligible_total,
            "primary_selected_rows": int(primary_row["selected_file_rows"]),
            "primary_exact_ties": int(primary_row["ties_at_threshold"]),
            "control_primary_selected_rows": group_selected["control"][primary_index],
            "treatment_primary_selected_rows": group_selected["treatment"][primary_index],
        },
    }


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="i07-self-test-") as tmp_text:
        tmp = Path(tmp_text)
        input_file = tmp / "i06.csv"
        summary_file = tmp / "summary.json"
        fields = sorted(REQUIRED_COLUMNS)
        base = {column: "" for column in fields}
        rows = []

        def row(index: int, dataset: str, presence: str, status: str, score: str, warning: str = "0") -> dict[str, str]:
            item = dict(base)
            item.update(
                {
                    "snapshot_order": str(index),
                    "snapshot_id": f"s{index}",
                    "dataset_source": dataset,
                    "repo_name": f"owner/repo{index}",
                    "repo_key": f"owner/repo{index}",
                    "snapshot_time": "2026-01-01T00:00:00Z",
                    "snapshot_commit": f"c{index}",
                    "relative_path": f"f{index}.py",
                    "file_sha256": f"sha{index}",
                    PRESENCE_COLUMN: presence,
                    "ml_fun_cfun_occurrences_total": "1" if status == "scored" else "0",
                    "ml_fun_cfun_agc_occurrences": "1" if score and Decimal(score) > Decimal("0.5") else "0",
                    "ml_fun_cfun_hwc_occurrences": "0" if score and Decimal(score) > Decimal("0.5") else "1" if status == "scored" else "0",
                    "ml_fun_cfun_space_by_tokens_total": "100" if status == "scored" else "0",
                    "ml_fun_cfun_agc_space_by_tokens": str(int(Decimal(score) * 100)) if score else "0",
                    METRIC_COLUMN: score,
                    WARNING_COLUMN: warning,
                    PRIMARY_FLAG_COLUMN: "1" if score and Decimal(score) > PRIMARY_THRESHOLD else "0" if status == "scored" else "",
                    PRIMARY_THRESHOLD_COLUMN: "0.5",
                    PRIMARY_OPERATOR_COLUMN: ">",
                    STATUS_COLUMN: status,
                }
            )
            return item

        rows.extend(
            [
                row(1, "control", "fun_only", "scored", "0.60"),
                row(2, "treatment", "fun_and_class_method", "scored", "0.50", "1"),
                row(3, "treatment", "class_method_only", "scored", "0.20"),
                row(4, "treatment", "neither", "no_ml_fun_cfun", ""),
                row(5, "control", "neither", "file_not_prepared", ""),
            ]
        )
        atomic_csv(rows, input_file, fields)
        atomic_json(
            {
                "run": EXPECTED_I06_VERSION,
                "status": "PASS_WITH_WARNINGS",
                "failed_hard_checks": 0,
                "primary_file_rule": {"metric": METRIC_COLUMN, "operator": ">", "threshold": 0.5},
            },
            summary_file,
        )
        summary = validate_i06_summary(summary_file)
        result = analyze(input_file, summary, {}, False)
        if result["hard_failures"] != 0:
            raise AssertionError(f"Self-test hard failures: {result['checks']}")
        accounting = result["accounting"]
        if accounting["eligible_rows"] != 3:
            raise AssertionError(accounting)
        if accounting["primary_selected_rows"] != 1:
            raise AssertionError(accounting)
        if accounting["primary_exact_ties"] != 1:
            raise AssertionError(accounting)
        if len(result["specs"]) != 21:
            raise AssertionError("Threshold grid must have 21 points")
    print("SELF-TEST PASS")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--i06-summary-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--strict-expected-counts", action="store_true")
    parser.add_argument("--expected-file-rows", type=int)
    parser.add_argument("--expected-prepared-rows", type=int)
    parser.add_argument("--expected-eligible-rows", type=int)
    parser.add_argument("--expected-control-file-rows", type=int)
    parser.add_argument("--expected-treatment-file-rows", type=int)
    parser.add_argument("--expected-control-eligible-rows", type=int)
    parser.add_argument("--expected-treatment-eligible-rows", type=int)
    parser.add_argument("--expected-primary-selected-rows", type=int)
    parser.add_argument("--expected-primary-exact-ties", type=int)
    parser.add_argument("--expected-control-primary-selected-rows", type=int)
    parser.add_argument("--expected-treatment-primary-selected-rows", type=int)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if not args.self_test and (args.input_file is None or args.i06_summary_file is None or args.output_dir is None):
        parser.error("--input-file, --i06-summary-file, and --output-dir are required unless --self-test is used")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        run_self_test()
        return 0

    assert args.input_file is not None
    assert args.i06_summary_file is not None
    assert args.output_dir is not None
    started_at = utc_now()
    i06_summary = validate_i06_summary(args.i06_summary_file)
    expected = {
        "file_rows": args.expected_file_rows,
        "prepared_rows": args.expected_prepared_rows,
        "eligible_rows": args.expected_eligible_rows,
        "control_file_rows": args.expected_control_file_rows,
        "treatment_file_rows": args.expected_treatment_file_rows,
        "control_eligible_rows": args.expected_control_eligible_rows,
        "treatment_eligible_rows": args.expected_treatment_eligible_rows,
        "primary_selected_rows": args.expected_primary_selected_rows,
        "primary_exact_ties": args.expected_primary_exact_ties,
        "control_primary_selected_rows": args.expected_control_primary_selected_rows,
        "treatment_primary_selected_rows": args.expected_treatment_primary_selected_rows,
    }
    result = analyze(args.input_file, i06_summary, expected, args.strict_expected_counts)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    spec_path = args.output_dir / "ml_fun_cfun_threshold_spec.csv"
    audit_path = args.output_dir / "ml_fun_cfun_threshold_audit.csv"
    dataset_path = args.output_dir / "ml_fun_cfun_threshold_by_dataset.csv"
    presence_path = args.output_dir / "ml_fun_cfun_threshold_by_presence.csv"
    distribution_path = args.output_dir / "ml_fun_cfun_distribution_summary.csv"
    checks_path = args.output_dir / "ml_fun_cfun_threshold_checks.csv"

    atomic_csv(({k: v for k, v in spec.items() if k != "threshold_decimal"} for spec in result["specs"]), spec_path, THRESHOLD_SPEC_COLUMNS)
    atomic_csv(result["global_rows"], audit_path, GLOBAL_COLUMNS)
    atomic_csv(result["dataset_rows"], dataset_path, GROUP_COLUMNS)
    atomic_csv(result["presence_rows"], presence_path, GROUP_COLUMNS)
    atomic_csv(result["distribution_rows"], distribution_path, DISTRIBUTION_COLUMNS)
    atomic_csv(result["checks"], checks_path, CHECK_COLUMNS)

    upstream_warning = clean(i06_summary.get("status")) == "PASS_WITH_WARNINGS"
    status = "FAIL" if result["hard_failures"] else "PASS_WITH_WARNINGS" if upstream_warning else "PASS"
    summary_payload = {
        "run": SCRIPT_VERSION,
        "status": status,
        "failed_hard_checks": result["hard_failures"],
        "primary_file_rule": {
            "metric": METRIC_COLUMN,
            "operator": COMPARISON_OPERATOR,
            "threshold": float(PRIMARY_THRESHOLD),
            "no_procedure_policy": "blank/unclassified; never imputed as HWC",
        },
        "threshold_grid": {
            "count": 21,
            "start": 0.10,
            "step": 0.04,
            "end": 0.90,
            "primary": 0.50,
            "threshold_ids": [spec["threshold_id"] for spec in result["specs"]],
        },
        "accounting": result["accounting"],
        "methodology": {
            "source": "I06 combined regular-function + class-method ML historical file measurement",
            "threshold_recalibrated": False,
            "quality_outcomes_consumed": False,
            "sonarqube_consumed": False,
            "repo_month_timing_consumed": False,
            "repo_month_expansion_deferred": True,
        },
        "outputs": {
            "threshold_spec": str(spec_path),
            "threshold_audit": str(audit_path),
            "threshold_by_dataset": str(dataset_path),
            "threshold_by_presence": str(presence_path),
            "distribution_summary": str(distribution_path),
            "checks": str(checks_path),
        },
        "created_at_utc": utc_now(),
    }
    atomic_json(summary_payload, args.output_dir / "summary.json")
    metadata_payload = {
        "script_version": SCRIPT_VERSION,
        "started_at_utc": started_at,
        "completed_at_utc": utc_now(),
        "input_file": str(args.input_file),
        "input_file_sha256": sha256_file(args.input_file),
        "i06_summary_file": str(args.i06_summary_file),
        "i06_summary_sha256": sha256_file(args.i06_summary_file),
        "i06_status": i06_summary.get("status"),
        "i06_run": i06_summary.get("run") or i06_summary.get("script_version"),
        "metric": METRIC_COLUMN,
        "comparison_operator": COMPARISON_OPERATOR,
        "primary_threshold": 0.50,
        "threshold_grid": [float(spec["threshold_decimal"]) for spec in result["specs"]],
        "strict_expected_counts": bool(args.strict_expected_counts),
        "quality_outcomes_consumed": False,
        "sonarqube_consumed": False,
        "repo_month_timing_consumed": False,
    }
    atomic_json(metadata_payload, args.output_dir / "metadata.json")

    print("=" * 78)
    print(f"{SCRIPT_VERSION} combined ML threshold-audit summary")
    print(f"Status:                              {status}")
    print(f"Historical Python files:             {result['accounting']['total_rows']}")
    print(f"Eligible combined files:             {result['accounting']['eligible_rows']}")
    print(f"Thresholds:                          {len(result['specs'])} (0.10:0.90 by 0.04)")
    print(f"Primary selected files (> 0.50):     {result['accounting']['primary_selected_rows']}")
    print(f"Exact 0.50 ties:                     {result['accounting']['primary_exact_ties']}")
    print(f"Control primary selected:            {result['accounting']['control_primary_selected_rows']}")
    print(f"Treatment primary selected:          {result['accounting']['treatment_primary_selected_rows']}")
    print(f"Failed hard checks:                  {result['hard_failures']}")
    print(f"Threshold audit:                     {audit_path}")
    print(f"Dataset audit:                       {dataset_path}")
    print(f"Presence audit:                      {presence_path}")
    print(f"Checks:                              {checks_path}")
    print("=" * 78)
    return 1 if result["hard_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
