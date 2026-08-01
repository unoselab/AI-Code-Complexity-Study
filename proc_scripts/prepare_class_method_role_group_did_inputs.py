#!/usr/bin/env python3
"""Prepare zero-inclusive DiD inputs for four class-method outcomes.

The outcomes use one identical locked repository-month model sample:

1. Category 4: all retained synchronous class methods;
2. Category 5: testing-related synchronous class methods;
3. Category 6: boilerplate synchronous class methods;
4. Category 7: other methods excluding Categories 5 and 6.

Frozen run-py-7f13 body-month assignments are aggregated by repository-month,
left-joined to the run-py-7e model-ready panel, and zero-filled. Testing plus
boilerplate plus other must equal all class methods on every row. This prepares
inputs only; it computes no ATT or uncertainty statistic.
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


SCRIPT_VERSION = "run-py-7f14-v2"
UPSTREAM_SCHEMA_VERSION = "run-py-7f13-v2"
TAXONOMY_STATUS = "FROZEN_PARTITION"
TAXONOMY_VERSION = "class-method-testing-boilerplate-other-v1"

READY_COLUMN = (
    "analysis_ready_regular_module_function_agc_unique_body_"
    "python_snapshot_ncloc"
)
PANEL_KEY = ["dataset_source", "repo_name", "time"]
ASSIGNMENT_KEY = [*PANEL_KEY, "function_body_sha256"]
GROUPS = ["testing", "boilerplate", "other"]
OUTCOMES = [
    "all_class_methods",
    "testing_class_methods",
    "boilerplate_class_methods",
    "other_class_methods",
]

COUNT_COLUMN = "npr_agc_class_method_unique_bodies"
LOG_COLUMN = "log1p_npr_agc_class_method_unique_bodies"
HAS_COLUMN = "has_npr_agc_class_method_unique_body"
ZERO_COLUMN = "zero_npr_agc_class_method_unique_body_month"

OUTCOME_CATEGORIES = {
    "all_class_methods": 4,
    "testing_class_methods": 5,
    "boilerplate_class_methods": 6,
    "other_class_methods": 7,
}
OUTCOME_LABELS = {
    "all_class_methods": "All AGC-like synchronous class-method unique bodies",
    "testing_class_methods": "AGC-like testing-related synchronous class-method unique bodies",
    "boilerplate_class_methods": "AGC-like boilerplate synchronous class-method unique bodies",
    "other_class_methods": "AGC-like other synchronous class-method unique bodies",
}
OUTCOME_DEFINITIONS = {
    "all_class_methods": (
        "Distinct AGC-like synchronous direct-class-scope method bodies per "
        "repository-month after excluding lexically nested/local-class methods."
    ),
    "testing_class_methods": (
        "Category 5 distinct class-method bodies assigned to testing by the "
        "frozen run-py-7f13 taxonomy."
    ),
    "boilerplate_class_methods": (
        "Category 6 distinct class-method bodies assigned to boilerplate by "
        "the frozen run-py-7f13 taxonomy."
    ),
    "other_class_methods": (
        "Category 7 distinct class-method bodies assigned to other after "
        "excluding Categories 5 and 6 by the frozen run-py-7f13 taxonomy."
    ),
}

OUTPUT_FILES = {
    "all_class_methods": "run-py-7f14-did-input-all-class-methods.csv",
    "testing_class_methods": "run-py-7f14-did-input-testing-class-methods.csv",
    "boilerplate_class_methods": "run-py-7f14-did-input-boilerplate-class-methods.csv",
    "other_class_methods": "run-py-7f14-did-input-other-class-methods.csv",
    "wide": "run-py-7f14-zero-inclusive-class-method-outcomes-wide.csv",
    "summary": "run-py-7f14-outcome-summary.csv",
    "qc": "run-py-7f14-did-input-qc.csv",
    "metadata": "run-py-7f14-did-input-metadata.json",
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
    "regular_function_scope",
    "agc_count_unit",
    "agc_outcome_scale",
    READY_COLUMN,
}

REQUIRED_ASSIGNMENT_COLUMNS = {
    *ASSIGNMENT_KEY,
    "testing_signal",
    "boilerplate_signal",
    "class_method_group",
    "taxonomy_status",
    "taxonomy_version",
}

PROVENANCE_COLUMNS = [
    "class_method_outcome_category",
    "class_method_outcome_group",
    "class_method_outcome_label",
    "class_method_outcome_definition",
    "class_method_outcome_schema_version",
    "class_method_taxonomy_status",
    "class_method_taxonomy_version",
    "class_method_scope",
    "class_method_count_unit",
    "class_method_outcome_scale",
]


class ValidationError(RuntimeError):
    """Raised when an input or cross-artifact invariant is violated."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-panel", type=Path)
    parser.add_argument("--assignments", type=Path)
    parser.add_argument("--taxonomy-metadata", type=Path)
    parser.add_argument("--taxonomy-qc", type=Path)
    parser.add_argument("--role-taxonomy", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-base-panel-rows", type=int, default=1536)
    parser.add_argument("--expected-model-ready-rows", type=int, default=1521)
    parser.add_argument("--expected-body-months", type=int, default=3925)
    parser.add_argument("--expected-testing", type=int, default=1201)
    parser.add_argument("--expected-all-positive-rows", type=int, default=497)
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


def parse_bool(value: str, label: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "1.0", "true", "t", "yes"}:
        return True
    if normalized in {"0", "0.0", "false", "f", "no"}:
        return False
    raise ValidationError(f"{label} must be binary; found {value!r}")


def require_positive(value: int, label: str) -> None:
    if value <= 0:
        raise ValidationError(f"{label} must be positive; found {value}")


def validate_upstream(
    metadata: Mapping[str, Any],
    qc_path: Path,
    taxonomy: Mapping[str, Any],
) -> None:
    if metadata.get("schema_version") != UPSTREAM_SCHEMA_VERSION:
        raise ValidationError(
            "Unexpected run-py-7f13 schema_version: "
            f"{metadata.get('schema_version')!r}"
        )
    if metadata.get("status") != "PASS":
        raise ValidationError("run-py-7f13 metadata status must be PASS")
    if metadata.get("taxonomy_status") != TAXONOMY_STATUS:
        raise ValidationError("run-py-7f13 taxonomy must be FROZEN_BINARY")
    if metadata.get("taxonomy_version") != TAXONOMY_VERSION:
        raise ValidationError("Unexpected run-py-7f13 taxonomy_version")

    scope = metadata.get("scientific_scope")
    if not isinstance(scope, dict):
        raise ValidationError("run-py-7f13 scientific_scope is missing")
    if scope.get("role_groups_mutually_exclusive_and_exhaustive") is not True:
        raise ValidationError("run-py-7f13 role taxonomy is not exhaustive")
    if scope.get("category_4_equals_categories_5_plus_6_plus_7") is not True:
        raise ValidationError("run-py-7f13 category partition identity is missing")
    if scope.get("lexically_nested_or_local_class_methods_excluded") is not True:
        raise ValidationError("run-py-7f13 must exclude lexically nested methods")
    if scope.get("att_or_uncertainty_computed") is not False:
        raise ValidationError("run-py-7f13 must not compute ATT or uncertainty")

    qc_fields, qc_rows = read_csv(qc_path)
    if not {"check_name", "passed"}.issubset(qc_fields) or not qc_rows:
        raise ValidationError("Unexpected or empty run-py-7f13 QC")
    failed = [
        row["check_name"]
        for row in qc_rows
        if not parse_bool(row["passed"], row["check_name"])
    ]
    if failed:
        raise ValidationError("run-py-7f13 has failed QC checks: " + ", ".join(failed))

    if taxonomy.get("schema_version") != UPSTREAM_SCHEMA_VERSION:
        raise ValidationError("Unexpected role-taxonomy schema_version")
    if taxonomy.get("taxonomy_status") != TAXONOMY_STATUS:
        raise ValidationError("Role taxonomy is not frozen")
    groups = {
        item.get("id")
        for item in taxonomy.get("groups", [])
        if isinstance(item, dict)
    }
    if groups != set(GROUPS):
        raise ValidationError(f"Role taxonomy must contain exactly {GROUPS}")
    if taxonomy.get("all_class_methods_category") != 4:
        raise ValidationError("Role taxonomy must preserve Category 4 as the union")


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

    seen: set[tuple[str, str, str]] = set()
    model_rows: list[dict[str, str]] = []
    for row_number, row in enumerate(rows, start=2):
        key = tuple(row[column].strip() for column in PANEL_KEY)
        if any(not value for value in key) or key in seen:
            raise ValidationError(f"Invalid or duplicate base-panel key at row {row_number}")
        seen.add(key)  # type: ignore[arg-type]
        if not parse_bool(row[READY_COLUMN], f"base row {row_number} ready"):
            continue
        if parse_bool(row["has_parse_exclusion"], f"base row {row_number} parse exclusion"):
            raise ValidationError(f"Model-ready row {row_number} has a parse exclusion")
        if not parse_bool(row["npr_detection_complete"], f"base row {row_number} detection"):
            raise ValidationError(f"Model-ready row {row_number} is NPR-incomplete")
        if row["agc_outcome_scale"].strip() != "raw_count":
            raise ValidationError(f"Model-ready row {row_number} has a non-raw outcome")
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
) -> tuple[dict[tuple[str, str, str], Counter[str]], Counter[str], int]:
    fields, rows = read_csv(path)
    missing = sorted(REQUIRED_ASSIGNMENT_COLUMNS - set(fields))
    if missing:
        raise ValidationError("Assignments are missing columns: " + ", ".join(missing))
    if len(rows) != expected_body_months:
        raise ValidationError(
            f"Assignment rows={len(rows)}; expected {expected_body_months}"
        )

    seen: set[tuple[str, str, str, str]] = set()
    by_panel: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    totals: Counter[str] = Counter()
    outside_panel = 0
    for row_number, row in enumerate(rows, start=2):
        key = tuple(row[column].strip() for column in ASSIGNMENT_KEY)
        if any(not value for value in key) or key in seen:
            raise ValidationError(f"Invalid or duplicate assignment key at row {row_number}")
        seen.add(key)  # type: ignore[arg-type]
        panel_key = key[:3]
        outside_panel += int(panel_key not in valid_panel_keys)
        group = row["class_method_group"].strip()
        if group not in GROUPS:
            raise ValidationError(f"Invalid class-method group at row {row_number}: {group}")
        testing = parse_bool(row["testing_signal"], f"assignment row {row_number}")
        boilerplate = parse_bool(
            row["boilerplate_signal"], f"assignment row {row_number} boilerplate"
        )
        expected_group = "testing" if testing else "boilerplate" if boilerplate else "other"
        if group != expected_group:
            raise ValidationError(f"Priority/group mismatch at assignment row {row_number}")
        if row["taxonomy_status"].strip() != TAXONOMY_STATUS:
            raise ValidationError(f"Unfrozen assignment at row {row_number}")
        if row["taxonomy_version"].strip() != TAXONOMY_VERSION:
            raise ValidationError(f"Unexpected taxonomy version at row {row_number}")
        by_panel[panel_key][group] += 1  # type: ignore[index]
        totals[group] += 1
    return dict(by_panel), totals, outside_panel


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
    panels = {outcome: [] for outcome in OUTCOMES}
    wide_rows: list[dict[str, str]] = []
    stats = {
        outcome: {"panel_rows": 0, "positive_rows": 0, "zero_rows": 0, "total_count": 0}
        for outcome in OUTCOMES
    }
    reconciliation_errors = 0

    for base_row in model_rows:
        key = tuple(base_row[column].strip() for column in PANEL_KEY)
        group_counts = counts_by_panel.get(key, {})  # type: ignore[arg-type]
        testing = int(group_counts.get("testing", 0))
        boilerplate = int(group_counts.get("boilerplate", 0))
        other = int(group_counts.get("other", 0))
        all_methods = testing + boilerplate + other
        counts = {
            "all_class_methods": all_methods,
            "testing_class_methods": testing,
            "boilerplate_class_methods": boilerplate,
            "other_class_methods": other,
        }
        reconciliation_errors += int(
            counts["all_class_methods"]
            != counts["testing_class_methods"]
            + counts["boilerplate_class_methods"]
            + counts["other_class_methods"]
        )

        for outcome, count in counts.items():
            output = dict(base_row)
            output.update(outcome_values(count))
            output.update(
                {
                    "class_method_outcome_category": str(OUTCOME_CATEGORIES[outcome]),
                    "class_method_outcome_group": outcome,
                    "class_method_outcome_label": OUTCOME_LABELS[outcome],
                    "class_method_outcome_definition": OUTCOME_DEFINITIONS[outcome],
                    "class_method_outcome_schema_version": SCRIPT_VERSION,
                    "class_method_taxonomy_status": TAXONOMY_STATUS,
                    "class_method_taxonomy_version": TAXONOMY_VERSION,
                    "class_method_scope": "synchronous_direct_class_scope_method_excluding_lexically_nested",
                    "class_method_count_unit": "distinct_function_body_sha256_per_repository_month",
                    "class_method_outcome_scale": "raw_count",
                }
            )
            panels[outcome].append(output)
            stats[outcome]["panel_rows"] += 1
            stats[outcome]["positive_rows"] += int(count > 0)
            stats[outcome]["zero_rows"] += int(count == 0)
            stats[outcome]["total_count"] += count

        wide = dict(base_row)
        for outcome, count in counts.items():
            prefix = f"npr_agc_{outcome}_unique_bodies"
            wide[prefix] = str(count)
            wide[f"log1p_{prefix}"] = repr(math.log1p(count))
            wide[f"has_{prefix}"] = "1" if count > 0 else "0"
            wide[f"zero_{outcome}_month"] = "1" if count == 0 else "0"
        wide["role_group_sum"] = str(testing + boilerplate + other)
        wide["all_minus_role_group_sum"] = str(
            all_methods - testing - boilerplate - other
        )
        wide["class_method_taxonomy_status"] = TAXONOMY_STATUS
        wide["class_method_taxonomy_version"] = TAXONOMY_VERSION
        wide_rows.append(wide)
    return panels, wide_rows, stats, reconciliation_errors


def summary_rows(panels: Mapping[str, Sequence[Mapping[str, str]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for outcome in OUTCOMES:
        for source in ["treatment", "control", "all"]:
            selected = [
                row for row in panels[outcome]
                if source == "all" or row["dataset_source"] == source
            ]
            counts = [int(row[COUNT_COLUMN]) for row in selected]
            positive_repos = {
                row["repo_name"] for row in selected if int(row[COUNT_COLUMN]) > 0
            }
            rows.append(
                {
                    "outcome_category": OUTCOME_CATEGORIES[outcome],
                    "outcome_group": outcome,
                    "outcome_label": OUTCOME_LABELS[outcome],
                    "dataset_source": source,
                    "panel_rows": len(selected),
                    "positive_rows": sum(value > 0 for value in counts),
                    "zero_rows": sum(value == 0 for value in counts),
                    "total_unique_bodies": sum(counts),
                    "repositories_with_positive_outcome": len(positive_repos),
                }
            )
    return rows


def qc_row(name: str, passed: bool, observed: Any, expected: Any, note: str) -> dict[str, Any]:
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
    base_rows: int,
    model_rows: int,
    assignment_rows: int,
    totals: Mapping[str, int],
    outside_panel: int,
    stats: Mapping[str, Mapping[str, int]],
    reconciliation_errors: int,
    expected_base_rows: int,
    expected_model_rows: int,
    expected_body_months: int,
    expected_testing: int,
    frozen_group_totals: Mapping[str, int],
    expected_all_positive: int,
) -> list[dict[str, Any]]:
    rows = [
        qc_row("base_panel_rows", base_rows == expected_base_rows, base_rows, expected_base_rows, "Preserve the completed run-py-7e parse-clean panel."),
        qc_row("model_ready_repository_month_rows", model_rows == expected_model_rows, model_rows, expected_model_rows, "All outcomes use the same Python-NCLOC model-ready sample."),
        qc_row("assignment_body_month_rows", assignment_rows == expected_body_months, assignment_rows, expected_body_months, "Preserve the frozen run-py-7f13 body-month universe."),
        qc_row("assignments_outside_model_ready_panel", outside_panel == 0, outside_panel, 0, "Every frozen assignment maps to the locked model-ready panel."),
        qc_row("testing_total_unique_bodies", totals.get("testing", 0) == expected_testing, totals.get("testing", 0), expected_testing, "Preserve frozen Category 5 units."),
        qc_row("boilerplate_total_unique_bodies", totals.get("boilerplate", 0) == frozen_group_totals.get("boilerplate", -1), totals.get("boilerplate", 0), frozen_group_totals.get("boilerplate", -1), "Preserve frozen Category 6 units from run-py-7f13 metadata."),
        qc_row("other_total_unique_bodies", totals.get("other", 0) == frozen_group_totals.get("other", -1), totals.get("other", 0), frozen_group_totals.get("other", -1), "Preserve frozen Category 7 units from run-py-7f13 metadata."),
        qc_row("role_group_total_unique_bodies", sum(totals.values()) == expected_body_months, sum(totals.values()), expected_body_months, "Categories 5, 6, and 7 equal Category 4."),
        qc_row("row_level_role_reconciliation_errors", reconciliation_errors == 0, reconciliation_errors, 0, "Testing plus boilerplate plus other equals all class methods on every row."),
        qc_row("identical_panel_rows_across_outcomes", all(stats[outcome]["panel_rows"] == expected_model_rows for outcome in OUTCOMES), "|".join(str(stats[outcome]["panel_rows"]) for outcome in OUTCOMES), "|".join([str(expected_model_rows)] * len(OUTCOMES)), "All four outcomes use an identical sample."),
        qc_row("all_class_method_total_reproduced", stats["all_class_methods"]["total_count"] == expected_body_months, stats["all_class_methods"]["total_count"], expected_body_months, "Category 4 preserves all retained assignments."),
    ]
    rows.append(qc_row("all_class_methods_positive_rows", stats["all_class_methods"]["positive_rows"] == expected_all_positive, stats["all_class_methods"]["positive_rows"], expected_all_positive, "Category 4 positive repository-month count remains locked."))
    for outcome in OUTCOMES:
        rows.append(qc_row(f"{outcome}_zero_fill_identity", stats[outcome]["positive_rows"] + stats[outcome]["zero_rows"] == expected_model_rows, stats[outcome]["positive_rows"] + stats[outcome]["zero_rows"], expected_model_rows, "Every outcome row is positive or zero after the left join."))
    return rows


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fields: Sequence[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(
    *,
    output_dir: Path,
    panel_fields: Sequence[str],
    panels: Mapping[str, Sequence[Mapping[str, str]]],
    wide_rows: Sequence[Mapping[str, str]],
    summaries: Sequence[Mapping[str, Any]],
    qc_rows: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
    overwrite: bool,
) -> None:
    paths = {key: output_dir / filename for key, filename in OUTPUT_FILES.items()}
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise ValidationError(
            "Output files already exist; use --overwrite for an intentional rerun: "
            + ", ".join(str(path) for path in existing)
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".run-py-7f14-", dir=output_dir))
    try:
        did_fields = [*panel_fields, COUNT_COLUMN, LOG_COLUMN, HAS_COLUMN, ZERO_COLUMN, *PROVENANCE_COLUMNS]
        for outcome in OUTCOMES:
            write_csv(staging / OUTPUT_FILES[outcome], panels[outcome], did_fields)

        wide_extra: list[str] = []
        for outcome in OUTCOMES:
            prefix = f"npr_agc_{outcome}_unique_bodies"
            wide_extra.extend([prefix, f"log1p_{prefix}", f"has_{prefix}", f"zero_{outcome}_month"])
        wide_extra.extend(["role_group_sum", "all_minus_role_group_sum", "class_method_taxonomy_status", "class_method_taxonomy_version"])
        write_csv(staging / OUTPUT_FILES["wide"], wide_rows, [*panel_fields, *wide_extra])
        write_csv(
            staging / OUTPUT_FILES["summary"],
            summaries,
            ["outcome_category", "outcome_group", "outcome_label", "dataset_source", "panel_rows", "positive_rows", "zero_rows", "total_unique_bodies", "repositories_with_positive_outcome"],
        )
        write_csv(staging / OUTPUT_FILES["qc"], qc_rows, ["check_name", "severity", "passed", "observed", "expected", "note"])

        materialized = [*OUTCOMES, "wide", "summary", "qc"]
        hashes = {key: sha256_file(staging / OUTPUT_FILES[key]) for key in materialized}
        full_metadata = dict(metadata)
        full_metadata["outputs"] = {
            key: {"file": OUTPUT_FILES[key], "sha256": hashes[key]}
            for key in materialized
        }
        (staging / OUTPUT_FILES["metadata"]).write_text(
            json.dumps(full_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        for filename in OUTPUT_FILES.values():
            os.replace(staging / filename, output_dir / filename)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def run_self_test() -> None:
    panel_fields = [*PANEL_KEY]
    model_rows = [
        {"dataset_source": "treatment", "repo_name": "example/repo", "time": "2025-01"},
        {"dataset_source": "control", "repo_name": "control/repo", "time": "2025-01"},
    ]
    counts = {
        ("treatment", "example/repo", "2025-01"): Counter(
            {"testing": 1, "boilerplate": 2, "other": 3}
        )
    }
    panels, wide, stats, errors = build_outputs(panel_fields, model_rows, counts)
    if errors != 0:
        raise ValidationError("Self-test failed role reconciliation")
    if [int(row[COUNT_COLUMN]) for row in panels["all_class_methods"]] != [6, 0]:
        raise ValidationError("Self-test failed all-class zero fill")
    if [int(row[COUNT_COLUMN]) for row in panels["testing_class_methods"]] != [1, 0]:
        raise ValidationError("Self-test failed testing zero fill")
    if [int(row[COUNT_COLUMN]) for row in panels["boilerplate_class_methods"]] != [2, 0]:
        raise ValidationError("Self-test failed boilerplate zero fill")
    if [int(row[COUNT_COLUMN]) for row in panels["other_class_methods"]] != [3, 0]:
        raise ValidationError("Self-test failed other zero fill")
    if any(int(row["all_minus_role_group_sum"]) != 0 for row in wide):
        raise ValidationError("Self-test failed wide reconciliation")
    if stats["all_class_methods"]["zero_rows"] != 1:
        raise ValidationError("Self-test failed zero-row accounting")
    print("run-py-7f14 self-test PASS")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.self_test_only:
            run_self_test()
            return 0
        required = {
            "base panel": args.base_panel,
            "assignments": args.assignments,
            "taxonomy metadata": args.taxonomy_metadata,
            "taxonomy QC": args.taxonomy_qc,
            "role taxonomy": args.role_taxonomy,
        }
        for label, path in required.items():
            if path is None or not path.is_file() or path.stat().st_size == 0:
                raise ValidationError(f"Missing or empty {label}: {path}")
        if args.output_dir is None:
            raise ValidationError("--output-dir is required")
        for label, value in {
            "expected base rows": args.expected_base_panel_rows,
            "expected model rows": args.expected_model_ready_rows,
            "expected body-months": args.expected_body_months,
            "expected testing": args.expected_testing,
            "expected all positive rows": args.expected_all_positive_rows,
        }.items():
            require_positive(value, label)
        taxonomy_metadata = read_json(args.taxonomy_metadata)
        taxonomy = read_json(args.role_taxonomy)
        validate_upstream(taxonomy_metadata, args.taxonomy_qc, taxonomy)
        upstream_counts = taxonomy_metadata.get("counts")
        if not isinstance(upstream_counts, dict):
            raise ValidationError("run-py-7f13 counts metadata is missing")
        frozen_group_totals = {
            "testing": int(upstream_counts.get("testing_body_month_units", -1)),
            "boilerplate": int(upstream_counts.get("boilerplate_body_month_units", -1)),
            "other": int(upstream_counts.get("other_body_month_units", -1)),
        }
        if sum(frozen_group_totals.values()) != args.expected_body_months:
            raise ValidationError(
                "Frozen run-py-7f13 groups do not sum to expected body-months: "
                f"{frozen_group_totals}"
            )
        panel_fields, model_rows = load_model_panel(
            args.base_panel, args.expected_base_panel_rows, args.expected_model_ready_rows
        )
        panel_keys = {
            tuple(row[column].strip() for column in PANEL_KEY) for row in model_rows
        }
        counts_by_panel, totals, outside_panel = aggregate_assignments(
            args.assignments, panel_keys, args.expected_body_months
        )
        panels, wide_rows, stats, reconciliation_errors = build_outputs(
            panel_fields, model_rows, counts_by_panel
        )
        summaries = summary_rows(panels)
        qc_rows = build_qc(
            base_rows=args.expected_base_panel_rows,
            model_rows=len(model_rows),
            assignment_rows=sum(totals.values()),
            totals=totals,
            outside_panel=outside_panel,
            stats=stats,
            reconciliation_errors=reconciliation_errors,
            expected_base_rows=args.expected_base_panel_rows,
            expected_model_rows=args.expected_model_ready_rows,
            expected_body_months=args.expected_body_months,
            expected_testing=args.expected_testing,
            frozen_group_totals=frozen_group_totals,
            expected_all_positive=args.expected_all_positive_rows,
        )
        failed = [row["check_name"] for row in qc_rows if not row["passed"]]
        if failed:
            raise ValidationError("Critical QC failed before publication: " + ", ".join(failed))

        metadata = {
            "schema_version": SCRIPT_VERSION,
            "status": "PASS",
            "taxonomy_status": TAXONOMY_STATUS,
            "taxonomy_version": TAXONOMY_VERSION,
            "inputs": {
                "run_py_7e_base_panel": {"path": str(args.base_panel), "sha256": sha256_file(args.base_panel)},
                "run_py_7f13_assignments": {"path": str(args.assignments), "sha256": sha256_file(args.assignments)},
                "run_py_7f13_metadata": {"path": str(args.taxonomy_metadata), "sha256": sha256_file(args.taxonomy_metadata)},
                "run_py_7f13_qc": {"path": str(args.taxonomy_qc), "sha256": sha256_file(args.taxonomy_qc)},
                "run_py_7f13_taxonomy": {"path": str(args.role_taxonomy), "sha256": sha256_file(args.role_taxonomy)},
            },
            "counts": {
                "base_panel_rows": args.expected_base_panel_rows,
                "model_ready_repository_month_rows": len(model_rows),
                "body_month_assignments": sum(totals.values()),
                "testing_total_unique_bodies": stats["testing_class_methods"]["total_count"],
                "boilerplate_total_unique_bodies": stats["boilerplate_class_methods"]["total_count"],
                "other_total_unique_bodies": stats["other_class_methods"]["total_count"],
                "all_total_unique_bodies": stats["all_class_methods"]["total_count"],
                "testing_positive_rows": stats["testing_class_methods"]["positive_rows"],
                "testing_zero_rows": stats["testing_class_methods"]["zero_rows"],
                "boilerplate_positive_rows": stats["boilerplate_class_methods"]["positive_rows"],
                "boilerplate_zero_rows": stats["boilerplate_class_methods"]["zero_rows"],
                "other_positive_rows": stats["other_class_methods"]["positive_rows"],
                "other_zero_rows": stats["other_class_methods"]["zero_rows"],
                "all_positive_rows": stats["all_class_methods"]["positive_rows"],
                "all_zero_rows": stats["all_class_methods"]["zero_rows"],
                "assignments_outside_model_ready_panel": outside_panel,
                "row_level_reconciliation_errors": reconciliation_errors,
                "critical_qc_failures": 0,
            },
            "outcome_contract": {
                "canonical_count_column": COUNT_COLUMN,
                "canonical_log1p_column": LOG_COLUMN,
                "canonical_has_column": HAS_COLUMN,
                "canonical_zero_column": ZERO_COLUMN,
                "outcome_groups": OUTCOMES,
                "category_mapping": OUTCOME_CATEGORIES,
                "count_unit": "distinct function_body_sha256 per repository-month",
                "scale": "raw_count",
                "zero_inclusive": True,
            },
            "scientific_scope": {
                "model_ready_python_snapshot_ncloc_rows_only": True,
                "same_repository_month_sample_for_all_outcomes": True,
                "role_group_counts_left_joined_and_zero_filled": True,
                "category_4_equals_categories_5_plus_6_plus_7_row_by_row": True,
                "lexically_nested_or_local_class_methods_excluded": True,
                "att_or_uncertainty_computed": False,
            },
        }
        write_outputs(
            output_dir=args.output_dir,
            panel_fields=panel_fields,
            panels=panels,
            wide_rows=wide_rows,
            summaries=summaries,
            qc_rows=qc_rows,
            metadata=metadata,
            overwrite=args.overwrite,
        )
        print("run-py-7f14 class-method DiD-input preparation complete")
        print(f"Model-ready repository-month rows: {len(model_rows):,}")
        for outcome in OUTCOMES:
            label = outcome.replace("_", " ").title()
            print(
                f"{label + ':':36s}"
                f"total={stats[outcome]['total_count']:,}, "
                f"positive={stats[outcome]['positive_rows']:,}, "
                f"zero={stats[outcome]['zero_rows']:,}"
            )
        print(f"Row-level reconciliation errors:  {reconciliation_errors:,}")
        print(f"Output directory:                 {args.output_dir.resolve()}")
        print("ATT/uncertainty computed:          NO")
        print("Status:                            PASS")
        return 0
    except (ValidationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
