#!/usr/bin/env python3
"""Prepare zero-inclusive DiD inputs for three regular-function outcomes.

The three outcomes use one identical locked repository-month model sample:

1. testing: AGC-like regular functions related to testing or test support;
2. other_functions: AGC-like regular functions unrelated to testing;
3. all_regular_functions: all AGC-like regular functions.

The run-py-7f07 body-month assignments are aggregated by repository-month and
left-joined to the run-py-7e model-ready panel. Missing group counts become
zeros. The binary-group sum must reproduce the original run-py-7e outcome on
every row. This script prepares inputs only; it does not estimate ATT or any
uncertainty statistic.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCRIPT_VERSION = "run-py-7f08-v1"
UPSTREAM_SCHEMA_VERSION = "run-py-7f07-v1"
TAXONOMY_STATUS = "FROZEN_BINARY"
TAXONOMY_VERSION = "testing-vs-other-functions-v1"
READY_COLUMN = (
    "analysis_ready_regular_module_function_agc_unique_body_"
    "python_snapshot_ncloc"
)
PANEL_KEY = ["dataset_source", "repo_name", "time"]
ASSIGNMENT_KEY = [*PANEL_KEY, "function_body_sha256"]
GROUPS = ["testing", "other_functions"]
OUTCOME_GROUPS = ["testing", "other_functions", "all_regular_functions"]

COUNT_COLUMN = "npr_agc_regular_module_function_unique_bodies"
LOG_COLUMN = "log1p_npr_agc_regular_module_function_unique_bodies"
HAS_COLUMN = "has_npr_agc_regular_module_function_unique_body"
ZERO_COLUMN = "zero_npr_agc_regular_module_function_unique_body_month"

OUTCOME_LABELS = {
    "testing": "AGC-like testing and test-support regular-function unique bodies",
    "other_functions": "AGC-like non-testing regular-function unique bodies",
    "all_regular_functions": "All AGC-like regular-function unique bodies",
}
OUTCOME_DEFINITIONS = {
    "testing": (
        "Distinct AGC-like regular synchronous module-function bodies with the "
        "frozen testing signal in a repository-month."
    ),
    "other_functions": (
        "Distinct AGC-like regular synchronous module-function bodies without "
        "the frozen testing signal in a repository-month."
    ),
    "all_regular_functions": (
        "Distinct AGC-like regular synchronous module-function bodies from both "
        "frozen binary groups in a repository-month."
    ),
}

OUTPUT_FILES = {
    "testing": "run-py-7f08-did-input-testing-regular-functions.csv",
    "other_functions": "run-py-7f08-did-input-other-regular-functions.csv",
    "all_regular_functions": "run-py-7f08-did-input-all-regular-functions.csv",
    "wide": "run-py-7f08-zero-inclusive-binary-outcomes-wide.csv",
    "summary": "run-py-7f08-outcome-summary.csv",
    "qc": "run-py-7f08-did-input-qc.csv",
    "metadata": "run-py-7f08-did-input-metadata.json",
}

REQUIRED_PANEL_COLUMNS = {
    *PANEL_KEY,
    "event",
    "time_to_event",
    "post_event",
    "has_parse_exclusion",
    "npr_detection_complete",
    "npr_specification",
    "treatment_group",
    COUNT_COLUMN,
    LOG_COLUMN,
    HAS_COLUMN,
    ZERO_COLUMN,
    "regular_function_scope",
    "agc_count_unit",
    "agc_outcome_scale",
    READY_COLUMN,
}

REQUIRED_ASSIGNMENT_COLUMNS = {
    *ASSIGNMENT_KEY,
    "testing_signal",
    "function_group",
    "taxonomy_status",
    "taxonomy_version",
}

PROVENANCE_COLUMNS = [
    "regular_function_outcome_group",
    "regular_function_outcome_label",
    "regular_function_outcome_definition",
    "regular_function_outcome_schema_version",
    "regular_function_taxonomy_status",
    "regular_function_taxonomy_version",
]


class ValidationError(RuntimeError):
    """Raised when an input or cross-artifact invariant is violated."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-panel", type=Path)
    parser.add_argument("--assignments", type=Path)
    parser.add_argument("--taxonomy-metadata", type=Path)
    parser.add_argument("--taxonomy-qc", type=Path)
    parser.add_argument("--binary-taxonomy", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-base-panel-rows", type=int, default=1536)
    parser.add_argument("--expected-model-ready-rows", type=int, default=1521)
    parser.add_argument("--expected-body-months", type=int, default=2249)
    parser.add_argument("--expected-testing", type=int, default=627)
    parser.add_argument("--expected-other-functions", type=int, default=1622)
    parser.add_argument("--expected-testing-positive-rows", type=int, default=198)
    parser.add_argument("--expected-other-positive-rows", type=int, default=417)
    parser.add_argument("--expected-all-positive-rows", type=int, default=486)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--self-test-only", action="store_true")
    return parser.parse_args(argv)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"Expected a JSON object in {path}")
    return value


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValidationError(f"CSV has no header: {path}")
            return list(reader.fieldnames), list(reader)
    except OSError as exc:
        raise ValidationError(f"Cannot read CSV {path}: {exc}") from exc


def parse_bool01(value: str, label: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true"}:
        return True
    if normalized in {"0", "false"}:
        return False
    raise ValidationError(f"{label} must be 0/1 or true/false; found {value!r}")


def parse_nonnegative_integer(value: str, label: str) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} must be numeric; found {value!r}") from exc
    if not math.isfinite(numeric) or numeric < 0 or not numeric.is_integer():
        raise ValidationError(
            f"{label} must be a nonnegative integer; found {value!r}"
        )
    return int(numeric)


def require_positive(value: int, label: str) -> None:
    if value <= 0:
        raise ValidationError(f"{label} must be positive; found {value}")


def validate_upstream_contract(
    metadata: Mapping[str, Any],
    qc_path: Path,
    taxonomy: Mapping[str, Any],
) -> None:
    if metadata.get("schema_version") != UPSTREAM_SCHEMA_VERSION:
        raise ValidationError(
            "Unexpected run-py-7f07 schema_version: "
            f"{metadata.get('schema_version')!r}"
        )
    if metadata.get("status") != "PASS":
        raise ValidationError("run-py-7f07 metadata status must be PASS")
    if metadata.get("taxonomy_status") != TAXONOMY_STATUS:
        raise ValidationError("run-py-7f07 taxonomy_status must be FROZEN_BINARY")
    if metadata.get("taxonomy_version") != TAXONOMY_VERSION:
        raise ValidationError("Unexpected run-py-7f07 taxonomy_version")

    scope = metadata.get("scientific_scope")
    if not isinstance(scope, dict):
        raise ValidationError("run-py-7f07 scientific_scope is missing")
    if scope.get("binary_taxonomy_frozen") is not True:
        raise ValidationError("run-py-7f07 binary taxonomy must be frozen")
    if scope.get("att_or_uncertainty_computed") is not False:
        raise ValidationError("run-py-7f07 must not compute ATT or uncertainty")

    qc_fields, qc_rows = read_csv(qc_path)
    required_qc = {"check_name", "severity", "passed"}
    if not required_qc.issubset(qc_fields) or not qc_rows:
        raise ValidationError("Unexpected or empty run-py-7f07 QC")
    failed_critical = [
        row["check_name"]
        for row in qc_rows
        if row["severity"] == "critical"
        and not parse_bool01(row["passed"], "run-py-7f07 QC passed")
    ]
    if failed_critical:
        raise ValidationError(
            "run-py-7f07 has failed critical QC checks: "
            + ", ".join(failed_critical)
        )

    if taxonomy.get("schema_version") != UPSTREAM_SCHEMA_VERSION:
        raise ValidationError("Unexpected binary-taxonomy schema_version")
    if taxonomy.get("taxonomy_status") != TAXONOMY_STATUS:
        raise ValidationError("Binary taxonomy is not frozen")
    group_ids = {
        item.get("id")
        for item in taxonomy.get("groups", [])
        if isinstance(item, dict)
    }
    if group_ids != set(GROUPS):
        raise ValidationError(
            f"Binary taxonomy must contain exactly {GROUPS}; found {group_ids}"
        )


def load_model_panel(
    path: Path,
    expected_base_rows: int,
    expected_model_rows: int,
) -> tuple[list[str], list[dict[str, str]]]:
    fields, rows = read_csv(path)
    missing = sorted(REQUIRED_PANEL_COLUMNS - set(fields))
    if missing:
        raise ValidationError("Base panel is missing columns: " + ", ".join(missing))
    if len(rows) != expected_base_rows:
        raise ValidationError(
            f"Base panel rows={len(rows)}; expected {expected_base_rows}"
        )

    all_keys: set[tuple[str, str, str]] = set()
    model_rows: list[dict[str, str]] = []
    for row_number, row in enumerate(rows, start=2):
        key = tuple(row[column].strip() for column in PANEL_KEY)
        if any(not value for value in key):
            raise ValidationError(f"base-panel row {row_number} has an empty key")
        if key in all_keys:
            raise ValidationError(f"base-panel row {row_number} duplicates key {key}")
        all_keys.add(key)

        ready = parse_bool01(row[READY_COLUMN], f"base-panel row {row_number} ready")
        if not ready:
            continue
        if parse_bool01(
            row["has_parse_exclusion"],
            f"base-panel row {row_number} has_parse_exclusion",
        ):
            raise ValidationError(
                f"model-ready base-panel row {row_number} has a parse exclusion"
            )
        if not parse_bool01(
            row["npr_detection_complete"],
            f"base-panel row {row_number} npr_detection_complete",
        ):
            raise ValidationError(
                f"model-ready base-panel row {row_number} is NPR-incomplete"
            )
        if row["regular_function_scope"].strip() != "module_function":
            raise ValidationError(
                f"model-ready base-panel row {row_number} has wrong function scope"
            )
        if row["agc_outcome_scale"].strip() != "raw_count":
            raise ValidationError(
                f"model-ready base-panel row {row_number} has wrong outcome scale"
            )
        model_rows.append(row)

    if len(model_rows) != expected_model_rows:
        raise ValidationError(
            f"Model-ready panel rows={len(model_rows)}; expected {expected_model_rows}"
        )
    return fields, model_rows


def aggregate_assignments(
    path: Path,
    valid_panel_keys: set[tuple[str, str, str]],
    expected_body_months: int,
) -> tuple[
    dict[tuple[str, str, str], Counter[str]],
    Counter[str],
    int,
]:
    fields, rows = read_csv(path)
    missing = sorted(REQUIRED_ASSIGNMENT_COLUMNS - set(fields))
    if missing:
        raise ValidationError(
            "run-py-7f07 assignments are missing columns: " + ", ".join(missing)
        )
    if len(rows) != expected_body_months:
        raise ValidationError(
            f"Assignment rows={len(rows)}; expected {expected_body_months}"
        )

    seen: set[tuple[str, str, str, str]] = set()
    by_panel: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    group_totals: Counter[str] = Counter()
    outside_panel = 0

    for row_number, row in enumerate(rows, start=2):
        assignment_key = tuple(row[column].strip() for column in ASSIGNMENT_KEY)
        if any(not value for value in assignment_key):
            raise ValidationError(f"assignment row {row_number} has an empty key")
        if assignment_key in seen:
            raise ValidationError(
                f"assignment row {row_number} duplicates key {assignment_key}"
            )
        seen.add(assignment_key)

        panel_key = assignment_key[:3]
        if panel_key not in valid_panel_keys:
            outside_panel += 1
        group = row["function_group"].strip()
        if group not in GROUPS:
            raise ValidationError(
                f"assignment row {row_number} has invalid group {group!r}"
            )
        testing_signal = parse_bool01(
            row["testing_signal"], f"assignment row {row_number} testing_signal"
        )
        if testing_signal != (group == "testing"):
            raise ValidationError(
                f"assignment row {row_number} has a testing/group mismatch"
            )
        if row["taxonomy_status"].strip() != TAXONOMY_STATUS:
            raise ValidationError(
                f"assignment row {row_number} taxonomy is not frozen"
            )
        if row["taxonomy_version"].strip() != TAXONOMY_VERSION:
            raise ValidationError(
                f"assignment row {row_number} has unexpected taxonomy version"
            )
        by_panel[panel_key][group] += 1
        group_totals[group] += 1

    return by_panel, group_totals, outside_panel


def outcome_values(count: int) -> dict[str, str]:
    return {
        COUNT_COLUMN: str(count),
        LOG_COLUMN: repr(math.log1p(count)),
        HAS_COLUMN: "1" if count > 0 else "0",
        ZERO_COLUMN: "1" if count == 0 else "0",
    }


def build_outputs(
    panel_fields: Sequence[str],
    model_rows: Sequence[Mapping[str, str]],
    counts_by_panel: Mapping[tuple[str, str, str], Mapping[str, int]],
) -> tuple[
    dict[str, list[dict[str, str]]],
    list[dict[str, str]],
    dict[str, dict[str, int]],
    int,
]:
    output_panels: dict[str, list[dict[str, str]]] = {
        group: [] for group in OUTCOME_GROUPS
    }
    wide_rows: list[dict[str, str]] = []
    stats = {
        group: {
            "panel_rows": 0,
            "positive_rows": 0,
            "zero_rows": 0,
            "total_count": 0,
        }
        for group in OUTCOME_GROUPS
    }
    reconciliation_mismatches = 0

    for row_number, base_row in enumerate(model_rows, start=2):
        key = tuple(base_row[column].strip() for column in PANEL_KEY)
        group_counts = counts_by_panel.get(key, {})
        testing = int(group_counts.get("testing", 0))
        other = int(group_counts.get("other_functions", 0))
        combined = testing + other
        original = parse_nonnegative_integer(
            base_row[COUNT_COLUMN], f"model-ready row {row_number} original outcome"
        )
        if combined != original:
            reconciliation_mismatches += 1

        counts = {
            "testing": testing,
            "other_functions": other,
            "all_regular_functions": combined,
        }
        for group, count in counts.items():
            output_row = dict(base_row)
            output_row.update(outcome_values(count))
            output_row.update(
                {
                    "regular_function_outcome_group": group,
                    "regular_function_outcome_label": OUTCOME_LABELS[group],
                    "regular_function_outcome_definition": OUTCOME_DEFINITIONS[group],
                    "regular_function_outcome_schema_version": SCRIPT_VERSION,
                    "regular_function_taxonomy_status": TAXONOMY_STATUS,
                    "regular_function_taxonomy_version": TAXONOMY_VERSION,
                }
            )
            output_panels[group].append(output_row)
            stats[group]["panel_rows"] += 1
            stats[group]["positive_rows"] += int(count > 0)
            stats[group]["zero_rows"] += int(count == 0)
            stats[group]["total_count"] += count

        wide_row = dict(base_row)
        for group, count in counts.items():
            prefix = f"npr_agc_{group}_unique_bodies"
            wide_row[prefix] = str(count)
            wide_row[f"log1p_{prefix}"] = repr(math.log1p(count))
            wide_row[f"has_{prefix}"] = "1" if count > 0 else "0"
            wide_row[f"zero_{group}_month"] = "1" if count == 0 else "0"
        wide_row["binary_group_sum"] = str(combined)
        wide_row["original_total_minus_binary_group_sum"] = str(original - combined)
        wide_row["regular_function_taxonomy_status"] = TAXONOMY_STATUS
        wide_row["regular_function_taxonomy_version"] = TAXONOMY_VERSION
        wide_rows.append(wide_row)

    return output_panels, wide_rows, stats, reconciliation_mismatches


def make_summary_rows(
    output_panels: Mapping[str, Sequence[Mapping[str, str]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in OUTCOME_GROUPS:
        panel = output_panels[group]
        for source in ["all", "control", "treatment"]:
            selected = (
                list(panel)
                if source == "all"
                else [row for row in panel if row["dataset_source"] == source]
            )
            counts = [parse_nonnegative_integer(row[COUNT_COLUMN], COUNT_COLUMN) for row in selected]
            positive_repositories = {
                row["repo_name"]
                for row, count in zip(selected, counts)
                if count > 0
            }
            rows.append(
                {
                    "outcome_group": group,
                    "outcome_label": OUTCOME_LABELS[group],
                    "dataset_source": source,
                    "panel_rows": len(selected),
                    "positive_rows": sum(count > 0 for count in counts),
                    "zero_rows": sum(count == 0 for count in counts),
                    "total_unique_bodies": sum(counts),
                    "repositories_with_positive_outcome": len(positive_repositories),
                }
            )
    return rows


def qc_row(
    name: str,
    passed: bool,
    observed: Any,
    expected: Any,
    note: str,
) -> dict[str, Any]:
    return {
        "check_name": name,
        "severity": "critical",
        "passed": passed,
        "observed": observed,
        "expected": expected,
        "note": note,
    }


def build_qc(
    *,
    base_panel_rows: int,
    model_rows: int,
    assignment_rows: int,
    group_totals: Mapping[str, int],
    outside_panel: int,
    stats: Mapping[str, Mapping[str, int]],
    reconciliation_mismatches: int,
    expected_base_rows: int,
    expected_model_rows: int,
    expected_body_months: int,
    expected_testing: int,
    expected_other: int,
    expected_testing_positive: int,
    expected_other_positive: int,
    expected_all_positive: int,
) -> list[dict[str, Any]]:
    return [
        qc_row(
            "base_panel_rows",
            base_panel_rows == expected_base_rows,
            base_panel_rows,
            expected_base_rows,
            "The completed run-py-7e parse-clean panel scope must be preserved.",
        ),
        qc_row(
            "model_ready_repository_month_rows",
            model_rows == expected_model_rows,
            model_rows,
            expected_model_rows,
            "All outcomes must use the same Python-NCLOC model-ready sample.",
        ),
        qc_row(
            "assignment_body_month_rows",
            assignment_rows == expected_body_months,
            assignment_rows,
            expected_body_months,
            "The frozen run-py-7f07 body-month universe must be preserved.",
        ),
        qc_row(
            "assignments_outside_model_ready_panel",
            outside_panel == 0,
            outside_panel,
            0,
            "Every frozen assignment must map to the locked model-ready panel.",
        ),
        qc_row(
            "testing_total_unique_bodies",
            group_totals.get("testing", 0) == expected_testing,
            group_totals.get("testing", 0),
            expected_testing,
            "Testing must preserve the frozen binary-taxonomy count.",
        ),
        qc_row(
            "other_functions_total_unique_bodies",
            group_totals.get("other_functions", 0) == expected_other,
            group_totals.get("other_functions", 0),
            expected_other,
            "Other functions must preserve the frozen binary-taxonomy count.",
        ),
        qc_row(
            "binary_group_total_unique_bodies",
            sum(group_totals.values()) == expected_body_months,
            sum(group_totals.values()),
            expected_body_months,
            "Testing and other_functions must exhaust all regular functions.",
        ),
        qc_row(
            "testing_positive_repository_months",
            stats["testing"]["positive_rows"] == expected_testing_positive,
            stats["testing"]["positive_rows"],
            expected_testing_positive,
            "Testing outcome must retain zero-count repository-months.",
        ),
        qc_row(
            "other_functions_positive_repository_months",
            stats["other_functions"]["positive_rows"] == expected_other_positive,
            stats["other_functions"]["positive_rows"],
            expected_other_positive,
            "Other-functions outcome must retain zero-count repository-months.",
        ),
        qc_row(
            "all_regular_functions_positive_repository_months",
            stats["all_regular_functions"]["positive_rows"] == expected_all_positive,
            stats["all_regular_functions"]["positive_rows"],
            expected_all_positive,
            "All-functions outcome must reproduce the original positive months.",
        ),
        qc_row(
            "testing_zero_repository_months",
            stats["testing"]["zero_rows"] == expected_model_rows - expected_testing_positive,
            stats["testing"]["zero_rows"],
            expected_model_rows - expected_testing_positive,
            "Missing testing counts after the left join must be zero-filled.",
        ),
        qc_row(
            "other_functions_zero_repository_months",
            stats["other_functions"]["zero_rows"] == expected_model_rows - expected_other_positive,
            stats["other_functions"]["zero_rows"],
            expected_model_rows - expected_other_positive,
            "Missing other-functions counts after the left join must be zero-filled.",
        ),
        qc_row(
            "all_regular_functions_zero_repository_months",
            stats["all_regular_functions"]["zero_rows"] == expected_model_rows - expected_all_positive,
            stats["all_regular_functions"]["zero_rows"],
            expected_model_rows - expected_all_positive,
            "The all-functions zero months must reproduce run-py-7e.",
        ),
        qc_row(
            "row_level_binary_reconciliation_mismatches",
            reconciliation_mismatches == 0,
            reconciliation_mismatches,
            0,
            "Testing plus other_functions must equal the original outcome on every row.",
        ),
        qc_row(
            "identical_panel_rows_across_outcomes",
            all(stats[group]["panel_rows"] == expected_model_rows for group in OUTCOME_GROUPS),
            "|".join(str(stats[group]["panel_rows"]) for group in OUTCOME_GROUPS),
            "|".join([str(expected_model_rows)] * 3),
            "All three DiD inputs must use the identical repository-month sample.",
        ),
        qc_row(
            "all_regular_function_total_reproduced",
            stats["all_regular_functions"]["total_count"] == expected_body_months,
            stats["all_regular_functions"]["total_count"],
            expected_body_months,
            "The all-functions input must reproduce the original total count.",
        ),
    ]


def write_csv(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    fields: Sequence[str],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(
    *,
    output_dir: Path,
    panel_fields: Sequence[str],
    output_panels: Mapping[str, Sequence[Mapping[str, str]]],
    wide_rows: Sequence[Mapping[str, str]],
    summary_rows: Sequence[Mapping[str, Any]],
    qc_rows: Sequence[Mapping[str, Any]],
    metadata_base: Mapping[str, Any],
    overwrite: bool,
) -> dict[str, str]:
    paths = {name: output_dir / filename for name, filename in OUTPUT_FILES.items()}
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise ValidationError(
            "Output files already exist; use --overwrite for an intentional rerun: "
            + ", ".join(str(path) for path in existing)
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=".run-py-7f08-", dir=output_dir))
    try:
        did_fields = [*panel_fields, *PROVENANCE_COLUMNS]
        for group in OUTCOME_GROUPS:
            write_csv(
                staging_dir / OUTPUT_FILES[group],
                output_panels[group],
                did_fields,
            )

        wide_extra_fields: list[str] = []
        for group in OUTCOME_GROUPS:
            prefix = f"npr_agc_{group}_unique_bodies"
            wide_extra_fields.extend(
                [
                    prefix,
                    f"log1p_{prefix}",
                    f"has_{prefix}",
                    f"zero_{group}_month",
                ]
            )
        wide_extra_fields.extend(
            [
                "binary_group_sum",
                "original_total_minus_binary_group_sum",
                "regular_function_taxonomy_status",
                "regular_function_taxonomy_version",
            ]
        )
        write_csv(
            staging_dir / OUTPUT_FILES["wide"],
            wide_rows,
            [*panel_fields, *wide_extra_fields],
        )
        write_csv(
            staging_dir / OUTPUT_FILES["summary"],
            summary_rows,
            [
                "outcome_group",
                "outcome_label",
                "dataset_source",
                "panel_rows",
                "positive_rows",
                "zero_rows",
                "total_unique_bodies",
                "repositories_with_positive_outcome",
            ],
        )
        write_csv(
            staging_dir / OUTPUT_FILES["qc"],
            qc_rows,
            ["check_name", "severity", "passed", "observed", "expected", "note"],
        )

        output_hashes = {
            group: sha256_file(staging_dir / OUTPUT_FILES[group])
            for group in [*OUTCOME_GROUPS, "wide", "summary", "qc"]
        }
        metadata = dict(metadata_base)
        metadata["outputs"] = {
            name: {"file": OUTPUT_FILES[name], "sha256": output_hashes[name]}
            for name in output_hashes
        }
        (staging_dir / OUTPUT_FILES["metadata"]).write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        for name in OUTPUT_FILES.values():
            os.replace(staging_dir / name, output_dir / name)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
    return output_hashes


def run_self_test() -> None:
    panel_fields = [
        "dataset_source",
        "repo_name",
        "time",
        COUNT_COLUMN,
        LOG_COLUMN,
        HAS_COLUMN,
        ZERO_COLUMN,
    ]
    model_rows = [
        {
            "dataset_source": "treatment",
            "repo_name": "example/repo",
            "time": "2025-01",
            COUNT_COLUMN: "2",
            LOG_COLUMN: repr(math.log1p(2)),
            HAS_COLUMN: "1",
            ZERO_COLUMN: "0",
        },
        {
            "dataset_source": "control",
            "repo_name": "control/repo",
            "time": "2025-01",
            COUNT_COLUMN: "0",
            LOG_COLUMN: "0.0",
            HAS_COLUMN: "0",
            ZERO_COLUMN: "1",
        },
    ]
    counts = {
        ("treatment", "example/repo", "2025-01"): Counter(
            {"testing": 1, "other_functions": 1}
        )
    }
    outputs, wide, stats, mismatches = build_outputs(
        panel_fields, model_rows, counts
    )
    if mismatches != 0:
        raise ValidationError("Self-test failed binary reconciliation")
    if [int(row[COUNT_COLUMN]) for row in outputs["testing"]] != [1, 0]:
        raise ValidationError("Self-test failed testing zero fill")
    if [int(row[COUNT_COLUMN]) for row in outputs["other_functions"]] != [1, 0]:
        raise ValidationError("Self-test failed other-functions zero fill")
    if [int(row[COUNT_COLUMN]) for row in outputs["all_regular_functions"]] != [2, 0]:
        raise ValidationError("Self-test failed all-functions outcome")
    if any(int(row["original_total_minus_binary_group_sum"]) != 0 for row in wide):
        raise ValidationError("Self-test failed wide reconciliation")
    if stats["all_regular_functions"]["positive_rows"] != 1:
        raise ValidationError("Self-test failed positive-row count")

    invalid_rows = [dict(model_rows[0], **{COUNT_COLUMN: "3"})]
    _, _, _, invalid_mismatches = build_outputs(
        panel_fields, invalid_rows, counts
    )
    if invalid_mismatches != 1:
        raise ValidationError("Self-test failed to detect an outcome mismatch")
    print("Self-test: PASS")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.self_test_only:
            run_self_test()
            return 0

        required_paths = {
            "base panel": args.base_panel,
            "run-py-7f07 assignments": args.assignments,
            "run-py-7f07 taxonomy metadata": args.taxonomy_metadata,
            "run-py-7f07 taxonomy QC": args.taxonomy_qc,
            "run-py-7f07 binary taxonomy": args.binary_taxonomy,
        }
        for label, path in required_paths.items():
            if path is None or not path.is_file() or path.stat().st_size == 0:
                raise ValidationError(f"Missing or empty {label}: {path}")
        if args.output_dir is None:
            raise ValidationError("--output-dir is required")

        expected_values = {
            "expected base-panel rows": args.expected_base_panel_rows,
            "expected model-ready rows": args.expected_model_ready_rows,
            "expected body-months": args.expected_body_months,
            "expected testing": args.expected_testing,
            "expected other functions": args.expected_other_functions,
            "expected testing positive rows": args.expected_testing_positive_rows,
            "expected other positive rows": args.expected_other_positive_rows,
            "expected all positive rows": args.expected_all_positive_rows,
        }
        for label, value in expected_values.items():
            require_positive(value, label)
        if args.expected_testing + args.expected_other_functions != args.expected_body_months:
            raise ValidationError(
                "Expected testing plus other_functions must equal expected body-months"
            )

        taxonomy_metadata = read_json(args.taxonomy_metadata)
        binary_taxonomy = read_json(args.binary_taxonomy)
        validate_upstream_contract(
            taxonomy_metadata,
            args.taxonomy_qc,
            binary_taxonomy,
        )

        panel_fields, model_rows = load_model_panel(
            args.base_panel,
            args.expected_base_panel_rows,
            args.expected_model_ready_rows,
        )
        panel_keys = {
            tuple(row[column].strip() for column in PANEL_KEY) for row in model_rows
        }
        counts_by_panel, group_totals, outside_panel = aggregate_assignments(
            args.assignments,
            panel_keys,
            args.expected_body_months,
        )
        output_panels, wide_rows, stats, reconciliation_mismatches = build_outputs(
            panel_fields,
            model_rows,
            counts_by_panel,
        )
        summary_rows = make_summary_rows(output_panels)
        qc_rows = build_qc(
            base_panel_rows=args.expected_base_panel_rows,
            model_rows=len(model_rows),
            assignment_rows=sum(group_totals.values()),
            group_totals=group_totals,
            outside_panel=outside_panel,
            stats=stats,
            reconciliation_mismatches=reconciliation_mismatches,
            expected_base_rows=args.expected_base_panel_rows,
            expected_model_rows=args.expected_model_ready_rows,
            expected_body_months=args.expected_body_months,
            expected_testing=args.expected_testing,
            expected_other=args.expected_other_functions,
            expected_testing_positive=args.expected_testing_positive_rows,
            expected_other_positive=args.expected_other_positive_rows,
            expected_all_positive=args.expected_all_positive_rows,
        )
        critical_failures = sum(
            row["severity"] == "critical" and not row["passed"] for row in qc_rows
        )
        if critical_failures:
            failed = [row["check_name"] for row in qc_rows if not row["passed"]]
            raise ValidationError(
                "Critical QC failed before output publication: " + ", ".join(failed)
            )

        metadata = {
            "schema_version": SCRIPT_VERSION,
            "status": "PASS",
            "taxonomy_status": TAXONOMY_STATUS,
            "taxonomy_version": TAXONOMY_VERSION,
            "inputs": {
                "run_py_7e_base_panel": {
                    "path": str(args.base_panel),
                    "sha256": sha256_file(args.base_panel),
                },
                "run_py_7f07_assignments": {
                    "path": str(args.assignments),
                    "sha256": sha256_file(args.assignments),
                },
                "run_py_7f07_taxonomy_metadata": {
                    "path": str(args.taxonomy_metadata),
                    "sha256": sha256_file(args.taxonomy_metadata),
                },
                "run_py_7f07_taxonomy_qc": {
                    "path": str(args.taxonomy_qc),
                    "sha256": sha256_file(args.taxonomy_qc),
                },
                "run_py_7f07_binary_taxonomy": {
                    "path": str(args.binary_taxonomy),
                    "sha256": sha256_file(args.binary_taxonomy),
                },
            },
            "counts": {
                "base_panel_rows": args.expected_base_panel_rows,
                "model_ready_repository_month_rows": len(model_rows),
                "body_month_assignments": sum(group_totals.values()),
                "testing_total_unique_bodies": stats["testing"]["total_count"],
                "other_functions_total_unique_bodies": stats["other_functions"]["total_count"],
                "all_regular_functions_total_unique_bodies": stats["all_regular_functions"]["total_count"],
                "testing_positive_rows": stats["testing"]["positive_rows"],
                "testing_zero_rows": stats["testing"]["zero_rows"],
                "other_functions_positive_rows": stats["other_functions"]["positive_rows"],
                "other_functions_zero_rows": stats["other_functions"]["zero_rows"],
                "all_regular_functions_positive_rows": stats["all_regular_functions"]["positive_rows"],
                "all_regular_functions_zero_rows": stats["all_regular_functions"]["zero_rows"],
                "assignments_outside_model_ready_panel": outside_panel,
                "row_level_reconciliation_mismatches": reconciliation_mismatches,
                "critical_qc_failures": critical_failures,
            },
            "outcome_contract": {
                "canonical_count_column": COUNT_COLUMN,
                "canonical_log1p_column": LOG_COLUMN,
                "canonical_has_column": HAS_COLUMN,
                "canonical_zero_column": ZERO_COLUMN,
                "outcome_groups": OUTCOME_GROUPS,
                "count_unit": "distinct function body SHA per repository-month",
                "scale": "raw_count",
                "zero_inclusive": True,
            },
            "scientific_scope": {
                "model_ready_python_snapshot_ncloc_rows_only": True,
                "same_repository_month_sample_for_all_outcomes": True,
                "binary_group_counts_left_joined_and_zero_filled": True,
                "binary_decomposition_verified_row_by_row": True,
                "att_or_uncertainty_computed": False,
            },
        }

        write_outputs(
            output_dir=args.output_dir,
            panel_fields=panel_fields,
            output_panels=output_panels,
            wide_rows=wide_rows,
            summary_rows=summary_rows,
            qc_rows=qc_rows,
            metadata_base=metadata,
            overwrite=args.overwrite,
        )

        print("run-py-7f08 DiD-input preparation complete")
        print(f"Model-ready repository-month rows: {len(model_rows):,}")
        print(
            "Testing:                         "
            f"total={stats['testing']['total_count']:,}, "
            f"positive={stats['testing']['positive_rows']:,}, "
            f"zero={stats['testing']['zero_rows']:,}"
        )
        print(
            "Other functions:                 "
            f"total={stats['other_functions']['total_count']:,}, "
            f"positive={stats['other_functions']['positive_rows']:,}, "
            f"zero={stats['other_functions']['zero_rows']:,}"
        )
        print(
            "All regular functions:           "
            f"total={stats['all_regular_functions']['total_count']:,}, "
            f"positive={stats['all_regular_functions']['positive_rows']:,}, "
            f"zero={stats['all_regular_functions']['zero_rows']:,}"
        )
        print(f"Row-level reconciliation errors: {reconciliation_mismatches:,}")
        print(f"Critical QC failures:            {critical_failures:,}")
        print(f"Output directory:                {args.output_dir.resolve()}")
        print("ATT/uncertainty computed:         NO")
        print("Status:                           PASS")
        return 0
    except (ValidationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
