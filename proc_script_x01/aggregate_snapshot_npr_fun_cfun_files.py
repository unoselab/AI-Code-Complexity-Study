#!/usr/bin/env python3
"""Combine finalized A12 FUN and A15 C_FUN file-NPR measurements.

I01 is a CPU-only measurement-combination stage for the Python longitudinal
quality study. It does not rescore code, run SonarQube, apply an NPR threshold,
or classify files as AI-generated.

The combined procedure-body NPR is recomputed from the finalized category-level
sufficient statistics. For every historical file occurrence:

    NPR_FUN_CFUN =
        (tokens_FUN * NPR_FUN + tokens_CFUN * NPR_CFUN)
        / (tokens_FUN + tokens_CFUN)

where the weights are the scored space-by-token counts from A12 and A15. The
weighted original and perturbed log-rank components are recomputed with the same
weights, and their ratio is retained separately as pooled-component NPR.

If only one category has a finite NPR, the combined NPR equals that category's
NPR. If neither category has finite NPR coverage, the combined NPR is blank,
never zero. Cross-category SHA values are not deduplicated because the combined
measurement preserves semantic procedure-body occurrences.

Inputs
------
A12:
  python_fun_file_npr_scores.csv
  python_fun_repo_month_file_npr_scores.csv
  summary.json

A15:
  python_cfun_file_npr_scores.csv
  python_cfun_repo_month_file_npr_scores.csv
  summary.json

Outputs
-------
  python_fun_cfun_file_npr_scores.csv
  python_fun_cfun_repo_month_file_npr_scores.csv
  python_fun_cfun_aggregation_checks.csv
  summary.json
  metadata.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_VERSION = "run-x-i01-v1"

EXPECTED_FILE_ROWS = 494_592
EXPECTED_REPO_MONTH_FILE_ROWS = 510_297
EXPECTED_REPOSITORIES = 167
EXPECTED_REPO_MONTHS = 1_954
EXPECTED_SNAPSHOTS = 1_496
EXPECTED_A12_FILE_FINITE = 196_643
EXPECTED_A12_REPO_MONTH_FINITE = 204_508
EXPECTED_A15_FILE_FINITE = 195_701
EXPECTED_A15_REPO_MONTH_FINITE = 202_027
EXPECTED_COMBINED_FILE_FINITE = 347_173
EXPECTED_COMBINED_REPO_MONTH_FINITE = 359_057

SUCCESS_STATUSES = {"scored", "scored_with_expected_exclusions"}

FILE_IDENTITY_COLUMNS = [
    "snapshot_order",
    "snapshot_id",
    "dataset_source",
    "repo_name",
    "repo_key",
    "snapshot_time",
    "snapshot_commit",
    "relative_path",
    "file_sha256",
    "python_lines",
    "parse_status",
]

REPO_MONTH_IDENTITY_COLUMNS = [
    "repo_id",
    "dataset_source",
    "repo_name",
    "repo_month",
    "time_index",
    "event",
    "event_index",
    "snapshot_id",
    "snapshot_commit",
    "relative_path",
    "file_sha256",
    "python_lines",
    "parse_status",
]

# Keep only the category fields needed to audit the combined measurement. The
# full A12/A15 sufficient statistics remain immutable upstream artifacts.
FUN_SOURCE_OUTPUT_COLUMNS = [
    "fun_space_by_tokens_total",
    "fun_space_by_tokens_scored",
    "fun_space_by_tokens_excluded",
    "file_npr_fun_space_by_token_weighted",
    "file_npr_fun_status",
]

CFUN_SOURCE_OUTPUT_COLUMNS = [
    "cfun_space_by_tokens_total",
    "cfun_space_by_tokens_scored",
    "cfun_space_by_tokens_excluded",
    "file_npr_cfun_space_by_token_weighted",
    "file_npr_cfun_status",
]

COMBINED_COLUMNS = [
    "fun_present",
    "cfun_present",
    "fun_finite_npr",
    "cfun_finite_npr",
    "procedure_body_presence_pattern",
    "procedure_body_finite_npr_pattern",
    "fun_cfun_occurrences_total",
    "fun_cfun_occurrences_scored",
    "fun_cfun_occurrences_excluded",
    "fun_cfun_occurrences_missing",
    "fun_cfun_space_by_tokens_total",
    "fun_cfun_space_by_tokens_scored",
    "fun_cfun_space_by_tokens_excluded",
    "fun_cfun_npr_coverage_ratio",
    "file_npr_fun_cfun_space_by_token_weighted",
    "file_fun_cfun_original_log_rank_space_by_token_weighted",
    "file_fun_cfun_mean_perturbed_log_rank_space_by_token_weighted",
    "file_npr_fun_cfun_pooled_components",
    "fun_cfun_expected_exclusion_classes",
    "file_npr_fun_cfun_status",
]

CHECK_COLUMNS = ["check_name", "severity", "passed", "observed", "expected", "note"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def finite_text(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return ""
    return format(value, ".17g")


def parse_nonnegative_int(text: str, field: str, context: str) -> int:
    if text == "":
        raise ValueError(f"Blank integer {field} in {context}")
    value = int(text)
    if value < 0:
        raise ValueError(f"Negative integer {field} in {context}: {value}")
    return value


def parse_optional_finite(text: str, field: str, context: str) -> float | None:
    if text == "":
        return None
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"Non-finite {field} in {context}: {text}")
    return value


def split_classes(text: str) -> set[str]:
    if not text:
        return set()
    normalized = text.replace(";", "|").replace(",", "|")
    return {piece.strip() for piece in normalized.split("|") if piece.strip()}


def union_classes(fun_text: str, cfun_text: str) -> str:
    return "|".join(sorted(split_classes(fun_text) | split_classes(cfun_text)))


def pattern(left: bool, right: bool) -> str:
    if left and right:
        return "fun_and_cfun"
    if left:
        return "fun_only"
    if right:
        return "cfun_only"
    return "neither"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_columns(header: list[str], required: list[str], label: str) -> dict[str, int]:
    index = {name: position for position, name in enumerate(header)}
    missing = [name for name in required if name not in index]
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")
    return index


def category_required(prefix: str) -> list[str]:
    if prefix == "fun":
        return [
            "fun_occurrences_total",
            "fun_occurrences_scored",
            "fun_occurrences_excluded",
            "fun_occurrences_missing",
            "fun_space_by_tokens_total",
            "fun_space_by_tokens_scored",
            "fun_space_by_tokens_excluded",
            "file_npr_fun_space_by_token_weighted",
            "file_fun_original_log_rank_space_by_token_weighted",
            "file_fun_mean_perturbed_log_rank_space_by_token_weighted",
            "fun_expected_exclusion_classes",
            "file_npr_fun_status",
        ]
    return [
        "cfun_occurrences_total",
        "cfun_occurrences_scored",
        "cfun_occurrences_excluded",
        "cfun_occurrences_missing",
        "cfun_space_by_tokens_total",
        "cfun_space_by_tokens_scored",
        "cfun_space_by_tokens_excluded",
        "file_npr_cfun_space_by_token_weighted",
        "file_cfun_original_log_rank_space_by_token_weighted",
        "file_cfun_mean_perturbed_log_rank_space_by_token_weighted",
        "cfun_expected_exclusion_classes",
        "file_npr_cfun_status",
    ]


def read_category(row: list[str], index: dict[str, int], prefix: str, context: str) -> dict[str, Any]:
    if prefix == "fun":
        occurrence_prefix = "fun"
        token_prefix = "fun"
        npr_field = "file_npr_fun_space_by_token_weighted"
        original_field = "file_fun_original_log_rank_space_by_token_weighted"
        perturbed_field = "file_fun_mean_perturbed_log_rank_space_by_token_weighted"
        classes_field = "fun_expected_exclusion_classes"
        status_field = "file_npr_fun_status"
    else:
        occurrence_prefix = "cfun"
        token_prefix = "cfun"
        npr_field = "file_npr_cfun_space_by_token_weighted"
        original_field = "file_cfun_original_log_rank_space_by_token_weighted"
        perturbed_field = "file_cfun_mean_perturbed_log_rank_space_by_token_weighted"
        classes_field = "cfun_expected_exclusion_classes"
        status_field = "file_npr_cfun_status"

    occurrences_total = parse_nonnegative_int(row[index[f"{occurrence_prefix}_occurrences_total"]], f"{prefix}.occurrences_total", context)
    occurrences_scored = parse_nonnegative_int(row[index[f"{occurrence_prefix}_occurrences_scored"]], f"{prefix}.occurrences_scored", context)
    occurrences_excluded = parse_nonnegative_int(row[index[f"{occurrence_prefix}_occurrences_excluded"]], f"{prefix}.occurrences_excluded", context)
    occurrences_missing = parse_nonnegative_int(row[index[f"{occurrence_prefix}_occurrences_missing"]], f"{prefix}.occurrences_missing", context)
    tokens_total = parse_nonnegative_int(row[index[f"{token_prefix}_space_by_tokens_total"]], f"{prefix}.tokens_total", context)
    tokens_scored = parse_nonnegative_int(row[index[f"{token_prefix}_space_by_tokens_scored"]], f"{prefix}.tokens_scored", context)
    tokens_excluded = parse_nonnegative_int(row[index[f"{token_prefix}_space_by_tokens_excluded"]], f"{prefix}.tokens_excluded", context)
    status = row[index[status_field]].strip()
    npr = parse_optional_finite(row[index[npr_field]].strip(), npr_field, context)
    original = parse_optional_finite(row[index[original_field]].strip(), original_field, context)
    perturbed = parse_optional_finite(row[index[perturbed_field]].strip(), perturbed_field, context)
    classes = row[index[classes_field]].strip()

    finite = status in SUCCESS_STATUSES
    if finite:
        if tokens_scored <= 0 or npr is None or original is None or perturbed is None:
            raise ValueError(f"Finite {prefix} status lacks finite sufficient statistics in {context}")
        if original == 0:
            raise ValueError(f"Finite {prefix} status has zero original log-rank in {context}")
    else:
        if tokens_scored != 0:
            raise ValueError(f"Non-finite {prefix} status has scored tokens in {context}")
        if npr is not None or original is not None or perturbed is not None:
            raise ValueError(f"Non-finite {prefix} status has nonblank sufficient statistics in {context}")

    if occurrences_scored + occurrences_excluded + occurrences_missing > occurrences_total:
        raise ValueError(f"{prefix} occurrence accounting exceeds total in {context}")
    if tokens_scored + tokens_excluded > tokens_total:
        raise ValueError(f"{prefix} token accounting exceeds total in {context}")

    return {
        "occurrences_total": occurrences_total,
        "occurrences_scored": occurrences_scored,
        "occurrences_excluded": occurrences_excluded,
        "occurrences_missing": occurrences_missing,
        "tokens_total": tokens_total,
        "tokens_scored": tokens_scored,
        "tokens_excluded": tokens_excluded,
        "status": status,
        "finite": finite,
        "npr": npr,
        "original": original,
        "perturbed": perturbed,
        "classes": classes,
    }


def combine_categories(fun: dict[str, Any], cfun: dict[str, Any], context: str) -> tuple[list[str], dict[str, Any]]:
    if (fun["status"] == "file_not_prepared") != (cfun["status"] == "file_not_prepared"):
        raise ValueError(f"FUN/C_FUN preparation status mismatch in {context}")

    fun_present = fun["occurrences_total"] > 0
    cfun_present = cfun["occurrences_total"] > 0
    fun_finite = bool(fun["finite"])
    cfun_finite = bool(cfun["finite"])

    occurrences_total = fun["occurrences_total"] + cfun["occurrences_total"]
    occurrences_scored = fun["occurrences_scored"] + cfun["occurrences_scored"]
    occurrences_excluded = fun["occurrences_excluded"] + cfun["occurrences_excluded"]
    occurrences_missing = fun["occurrences_missing"] + cfun["occurrences_missing"]
    tokens_total = fun["tokens_total"] + cfun["tokens_total"]
    tokens_scored = fun["tokens_scored"] + cfun["tokens_scored"]
    tokens_excluded = fun["tokens_excluded"] + cfun["tokens_excluded"]

    weighted_npr_sum = 0.0
    weighted_original_sum = 0.0
    weighted_perturbed_sum = 0.0
    for category in (fun, cfun):
        if category["finite"]:
            weight = category["tokens_scored"]
            weighted_npr_sum += weight * float(category["npr"])
            weighted_original_sum += weight * float(category["original"])
            weighted_perturbed_sum += weight * float(category["perturbed"])

    if tokens_scored > 0:
        combined_npr: float | None = weighted_npr_sum / tokens_scored
        combined_original: float | None = weighted_original_sum / tokens_scored
        combined_perturbed: float | None = weighted_perturbed_sum / tokens_scored
        if combined_original == 0:
            raise ValueError(f"Combined weighted original log-rank is zero in {context}")
        combined_pooled: float | None = combined_perturbed / combined_original
    else:
        combined_npr = None
        combined_original = None
        combined_perturbed = None
        combined_pooled = None

    if fun["status"] == "unexpected_missing_score" or cfun["status"] == "unexpected_missing_score" or occurrences_missing > 0:
        status = "unexpected_missing_score"
    elif fun["status"] == "file_not_prepared" and cfun["status"] == "file_not_prepared":
        status = "file_not_prepared"
    elif occurrences_total == 0:
        status = "no_fun_cfun"
    elif tokens_scored == 0 and occurrences_excluded > 0:
        status = "fun_cfun_all_excluded"
    elif tokens_scored == 0:
        status = "unexpected_missing_score"
    elif occurrences_excluded > 0:
        status = "scored_with_expected_exclusions"
    else:
        status = "scored"

    combined_finite = status in SUCCESS_STATUSES
    if combined_finite != (tokens_scored > 0):
        raise ValueError(f"Combined finite/status inconsistency in {context}: {status}")

    if fun_finite and not cfun_finite and not math.isclose(float(combined_npr), float(fun["npr"]), rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError(f"FUN-only combined NPR does not equal FUN NPR in {context}")
    if cfun_finite and not fun_finite and not math.isclose(float(combined_npr), float(cfun["npr"]), rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError(f"C_FUN-only combined NPR does not equal C_FUN NPR in {context}")
    if fun_finite and cfun_finite:
        lower = min(float(fun["npr"]), float(cfun["npr"]))
        upper = max(float(fun["npr"]), float(cfun["npr"]))
        if not (lower - 1e-12 <= float(combined_npr) <= upper + 1e-12):
            raise ValueError(f"Combined weighted NPR is outside component range in {context}")

    coverage = tokens_scored / tokens_total if tokens_total > 0 else None
    values = [
        "1" if fun_present else "0",
        "1" if cfun_present else "0",
        "1" if fun_finite else "0",
        "1" if cfun_finite else "0",
        pattern(fun_present, cfun_present),
        pattern(fun_finite, cfun_finite),
        str(occurrences_total),
        str(occurrences_scored),
        str(occurrences_excluded),
        str(occurrences_missing),
        str(tokens_total),
        str(tokens_scored),
        str(tokens_excluded),
        finite_text(coverage),
        finite_text(combined_npr),
        finite_text(combined_original),
        finite_text(combined_perturbed),
        finite_text(combined_pooled),
        union_classes(fun["classes"], cfun["classes"]),
        status,
    ]
    diagnostics = {
        "combined_finite": combined_finite,
        "status": status,
        "presence_pattern": pattern(fun_present, cfun_present),
        "finite_pattern": pattern(fun_finite, cfun_finite),
        "expected_exclusion": occurrences_excluded > 0,
        "unexpected_missing": status == "unexpected_missing_score",
    }
    return values, diagnostics


def merge_csv_pair(
    fun_path: Path,
    cfun_path: Path,
    output_path: Path,
    identity_columns: list[str],
    expected_rows: int,
    label: str,
) -> dict[str, Any]:
    output_columns = identity_columns + FUN_SOURCE_OUTPUT_COLUMNS + CFUN_SOURCE_OUTPUT_COLUMNS + COMBINED_COLUMNS
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = tempfile.NamedTemporaryFile(
        mode="w",
        newline="",
        encoding="utf-8",
        buffering=1024 * 1024,
        dir=output_path.parent,
        prefix=output_path.name + ".",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(temp.name)

    rows = 0
    finite_combined = 0
    finite_fun = 0
    finite_cfun = 0
    unexpected_missing = 0
    expected_exclusion_rows = 0
    status_counts: Counter[str] = Counter()
    presence_counts: Counter[str] = Counter()
    finite_pattern_counts: Counter[str] = Counter()
    snapshots: set[str] = set()
    repositories: set[str] = set()
    repo_months: set[tuple[str, str]] = set()

    try:
        writer = csv.writer(temp, lineterminator="\n")
        writer.writerow(output_columns)
        with fun_path.open("r", newline="", encoding="utf-8", buffering=1024 * 1024) as fun_handle, cfun_path.open(
            "r", newline="", encoding="utf-8", buffering=1024 * 1024
        ) as cfun_handle:
            fun_reader = csv.reader(fun_handle)
            cfun_reader = csv.reader(cfun_handle)
            fun_header = next(fun_reader)
            cfun_header = next(cfun_reader)
            fun_index = require_columns(fun_header, identity_columns + category_required("fun"), f"A12 {label}")
            cfun_index = require_columns(cfun_header, identity_columns + category_required("cfun"), f"A15 {label}")

            fun_source_indexes = [fun_index[name] for name in FUN_SOURCE_OUTPUT_COLUMNS]
            cfun_source_indexes = [cfun_index[name] for name in CFUN_SOURCE_OUTPUT_COLUMNS]
            fun_identity_indexes = [fun_index[name] for name in identity_columns]
            cfun_identity_indexes = [cfun_index[name] for name in identity_columns]
            snapshot_index = fun_index["snapshot_id"]
            repo_index = fun_index.get("repo_id")
            repo_month_index = fun_index.get("repo_month")
            path_index = fun_index["relative_path"]

            while True:
                try:
                    fun_row = next(fun_reader)
                except StopIteration:
                    fun_row = None
                try:
                    cfun_row = next(cfun_reader)
                except StopIteration:
                    cfun_row = None
                if fun_row is None and cfun_row is None:
                    break
                if fun_row is None or cfun_row is None:
                    raise ValueError(f"A12/A15 {label} row-count mismatch near row {rows + 1}")

                rows += 1
                identity_values = [fun_row[index] for index in fun_identity_indexes]
                cfun_identity_values = [cfun_row[index] for index in cfun_identity_indexes]
                if identity_values != cfun_identity_values:
                    differences = [
                        f"{name}: FUN={identity_values[pos]!r} C_FUN={cfun_identity_values[pos]!r}"
                        for pos, name in enumerate(identity_columns)
                        if identity_values[pos] != cfun_identity_values[pos]
                    ]
                    raise ValueError(f"{label} identity mismatch at row {rows}: " + "; ".join(differences[:8]))

                context = f"{label} row={rows} snapshot={fun_row[snapshot_index]} path={fun_row[path_index]}"
                fun = read_category(fun_row, fun_index, "fun", context)
                cfun = read_category(cfun_row, cfun_index, "cfun", context)
                combined_values, diag = combine_categories(fun, cfun, context)

                writer.writerow(
                    identity_values
                    + [fun_row[index] for index in fun_source_indexes]
                    + [cfun_row[index] for index in cfun_source_indexes]
                    + combined_values
                )

                finite_fun += int(fun["finite"])
                finite_cfun += int(cfun["finite"])
                finite_combined += int(diag["combined_finite"])
                unexpected_missing += int(diag["unexpected_missing"])
                expected_exclusion_rows += int(diag["expected_exclusion"])
                status_counts[diag["status"]] += 1
                presence_counts[diag["presence_pattern"]] += 1
                finite_pattern_counts[diag["finite_pattern"]] += 1
                snapshots.add(fun_row[snapshot_index])
                if repo_index is not None and repo_month_index is not None:
                    repositories.add(fun_row[repo_index])
                    repo_months.add((fun_row[repo_index], fun_row[repo_month_index]))

        temp.flush()
        os.fsync(temp.fileno())
        temp.close()
        if rows != expected_rows:
            raise ValueError(f"{label} rows {rows} != expected {expected_rows}")
        os.replace(temp_path, output_path)
        os.chmod(output_path, 0o664)
    except Exception:
        try:
            temp.close()
        except Exception:
            pass
        if temp_path.exists():
            temp_path.unlink()
        raise

    return {
        "rows": rows,
        "finite_combined_npr_rows": finite_combined,
        "finite_fun_npr_rows": finite_fun,
        "finite_cfun_npr_rows": finite_cfun,
        "unexpected_missing_rows": unexpected_missing,
        "rows_with_expected_exclusions": expected_exclusion_rows,
        "status_counts": dict(sorted(status_counts.items())),
        "presence_pattern_counts": dict(sorted(presence_counts.items())),
        "finite_npr_pattern_counts": dict(sorted(finite_pattern_counts.items())),
        "snapshots": len(snapshots),
        "repositories": len(repositories),
        "repo_months": len(repo_months),
    }


def add_check(checks: list[dict[str, str]], name: str, passed: bool, observed: Any, expected: Any, note: str) -> None:
    checks.append(
        {
            "check_name": name,
            "severity": "hard",
            "passed": "1" if passed else "0",
            "observed": clean(observed),
            "expected": clean(expected),
            "note": note,
        }
    )


def write_checks(path: Path, checks: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CHECK_COLUMNS)
        writer.writeheader()
        writer.writerows(checks)


def atomic_json(data: dict[str, Any], path: Path) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temp, path)


def run_self_test() -> None:
    fun = {
        "occurrences_total": 1,
        "occurrences_scored": 1,
        "occurrences_excluded": 0,
        "occurrences_missing": 0,
        "tokens_total": 10,
        "tokens_scored": 10,
        "tokens_excluded": 0,
        "status": "scored",
        "finite": True,
        "npr": 1.2,
        "original": 2.0,
        "perturbed": 2.4,
        "classes": "",
    }
    cfun = {
        "occurrences_total": 1,
        "occurrences_scored": 1,
        "occurrences_excluded": 0,
        "occurrences_missing": 0,
        "tokens_total": 30,
        "tokens_scored": 30,
        "tokens_excluded": 0,
        "status": "scored",
        "finite": True,
        "npr": 1.8,
        "original": 4.0,
        "perturbed": 7.2,
        "classes": "",
    }
    values, diag = combine_categories(fun, cfun, "self-test both")
    result = dict(zip(COMBINED_COLUMNS, values))
    assert diag["combined_finite"]
    assert math.isclose(float(result["file_npr_fun_cfun_space_by_token_weighted"]), 1.65, abs_tol=1e-12)
    expected_original = (10 * 2.0 + 30 * 4.0) / 40
    expected_perturbed = (10 * 2.4 + 30 * 7.2) / 40
    assert math.isclose(float(result["file_fun_cfun_original_log_rank_space_by_token_weighted"]), expected_original, abs_tol=1e-12)
    assert math.isclose(float(result["file_fun_cfun_mean_perturbed_log_rank_space_by_token_weighted"]), expected_perturbed, abs_tol=1e-12)
    assert math.isclose(float(result["file_npr_fun_cfun_pooled_components"]), expected_perturbed / expected_original, abs_tol=1e-12)

    absent = {
        "occurrences_total": 0,
        "occurrences_scored": 0,
        "occurrences_excluded": 0,
        "occurrences_missing": 0,
        "tokens_total": 0,
        "tokens_scored": 0,
        "tokens_excluded": 0,
        "status": "no_cfun",
        "finite": False,
        "npr": None,
        "original": None,
        "perturbed": None,
        "classes": "",
    }
    values, _ = combine_categories(fun, absent, "self-test fun-only")
    result = dict(zip(COMBINED_COLUMNS, values))
    assert math.isclose(float(result["file_npr_fun_cfun_space_by_token_weighted"]), 1.2, abs_tol=1e-12)
    assert result["procedure_body_finite_npr_pattern"] == "fun_only"

    absent_fun = dict(absent)
    absent_fun["status"] = "no_fun"
    values, _ = combine_categories(absent_fun, absent, "self-test neither")
    result = dict(zip(COMBINED_COLUMNS, values))
    assert result["file_npr_fun_cfun_space_by_token_weighted"] == ""
    assert result["file_npr_fun_cfun_status"] == "no_fun_cfun"
    print("aggregate_snapshot_npr_fun_cfun_files self-test: PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Combine finalized A12 FUN and A15 C_FUN file NPR measurements.")
    parser.add_argument("--a12-file", type=Path)
    parser.add_argument("--a12-repo-month-file", type=Path)
    parser.add_argument("--a12-summary", type=Path)
    parser.add_argument("--a15-file", type=Path)
    parser.add_argument("--a15-repo-month-file", type=Path)
    parser.add_argument("--a15-summary", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("repo_x01/run-x-i01"))
    parser.add_argument("--expected-file-rows", type=int, default=EXPECTED_FILE_ROWS)
    parser.add_argument("--expected-repo-month-file-rows", type=int, default=EXPECTED_REPO_MONTH_FILE_ROWS)
    parser.add_argument("--expected-repositories", type=int, default=EXPECTED_REPOSITORIES)
    parser.add_argument("--expected-repo-months", type=int, default=EXPECTED_REPO_MONTHS)
    parser.add_argument("--expected-snapshots", type=int, default=EXPECTED_SNAPSHOTS)
    parser.add_argument("--strict-expected-counts", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def require_path(path: Path | None, label: str) -> Path:
    if path is None:
        raise ValueError(f"Missing required argument: {label}")
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return 0

    started = utc_now()
    a12_file = require_path(args.a12_file, "A12 snapshot/file CSV")
    a12_repo_month = require_path(args.a12_repo_month_file, "A12 repo-month/file CSV")
    a12_summary_path = require_path(args.a12_summary, "A12 summary")
    a15_file = require_path(args.a15_file, "A15 snapshot/file CSV")
    a15_repo_month = require_path(args.a15_repo_month_file, "A15 repo-month/file CSV")
    a15_summary_path = require_path(args.a15_summary, "A15 summary")

    a12_summary = load_json(a12_summary_path)
    a15_summary = load_json(a15_summary_path)
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    file_output = output_dir / "python_fun_cfun_file_npr_scores.csv"
    repo_month_output = output_dir / "python_fun_cfun_repo_month_file_npr_scores.csv"
    checks_output = output_dir / "python_fun_cfun_aggregation_checks.csv"

    file_diag = merge_csv_pair(a12_file, a15_file, file_output, FILE_IDENTITY_COLUMNS, args.expected_file_rows, "snapshot/file")
    repo_diag = merge_csv_pair(a12_repo_month, a15_repo_month, repo_month_output, REPO_MONTH_IDENTITY_COLUMNS, args.expected_repo_month_file_rows, "repo-month/file")

    checks: list[dict[str, str]] = []
    add_check(checks, "a12_status", str(a12_summary.get("status", "")).startswith("PASS"), a12_summary.get("status"), "PASS*", "A12 must be finalized successfully.")
    add_check(checks, "a15_status", str(a15_summary.get("status", "")).startswith("PASS"), a15_summary.get("status"), "PASS*", "A15 must be finalized successfully.")
    add_check(checks, "a05_manifest_sha_matches_between_a12_a15", clean(a12_summary.get("a05_code_manifest_sha256")) == clean(a15_summary.get("a05_code_manifest_sha256")), a12_summary.get("a05_code_manifest_sha256"), a15_summary.get("a05_code_manifest_sha256"), "FUN and C_FUN must originate from the same frozen A05 code manifest.")
    add_check(checks, "snapshot_file_rows", file_diag["rows"] == args.expected_file_rows, file_diag["rows"], args.expected_file_rows, "A12/A15 snapshot/file rows must reconcile one-to-one in frozen order.")
    add_check(checks, "repo_month_file_rows", repo_diag["rows"] == args.expected_repo_month_file_rows, repo_diag["rows"], args.expected_repo_month_file_rows, "A12/A15 repo-month/file rows must reconcile one-to-one in frozen order.")
    add_check(checks, "a12_file_finite_fun_npr", file_diag["finite_fun_npr_rows"] == EXPECTED_A12_FILE_FINITE, file_diag["finite_fun_npr_rows"], EXPECTED_A12_FILE_FINITE, "Frozen A12 snapshot/file finite FUN NPR count.")
    add_check(checks, "a12_repo_month_finite_fun_npr", repo_diag["finite_fun_npr_rows"] == EXPECTED_A12_REPO_MONTH_FINITE, repo_diag["finite_fun_npr_rows"], EXPECTED_A12_REPO_MONTH_FINITE, "Frozen A12 repo-month/file finite FUN NPR count.")
    add_check(checks, "a15_file_finite_cfun_npr", file_diag["finite_cfun_npr_rows"] == EXPECTED_A15_FILE_FINITE, file_diag["finite_cfun_npr_rows"], EXPECTED_A15_FILE_FINITE, "Frozen A15 snapshot/file finite C_FUN NPR count.")
    add_check(checks, "a15_repo_month_finite_cfun_npr", repo_diag["finite_cfun_npr_rows"] == EXPECTED_A15_REPO_MONTH_FINITE, repo_diag["finite_cfun_npr_rows"], EXPECTED_A15_REPO_MONTH_FINITE, "Frozen A15 repo-month/file finite C_FUN NPR count.")
    add_check(checks, "combined_file_finite_npr", file_diag["finite_combined_npr_rows"] == EXPECTED_COMBINED_FILE_FINITE, file_diag["finite_combined_npr_rows"], EXPECTED_COMBINED_FILE_FINITE, "Frozen union of finite FUN and C_FUN snapshot/file coverage.")
    add_check(checks, "combined_repo_month_finite_npr", repo_diag["finite_combined_npr_rows"] == EXPECTED_COMBINED_REPO_MONTH_FINITE, repo_diag["finite_combined_npr_rows"], EXPECTED_COMBINED_REPO_MONTH_FINITE, "Frozen union of finite FUN and C_FUN repo-month/file coverage.")
    add_check(checks, "snapshot_file_unexpected_missing", file_diag["unexpected_missing_rows"] == 0, file_diag["unexpected_missing_rows"], 0, "No combined snapshot/file may have unexpected missing NPR.")
    add_check(checks, "repo_month_unexpected_missing", repo_diag["unexpected_missing_rows"] == 0, repo_diag["unexpected_missing_rows"], 0, "No combined repo-month/file may have unexpected missing NPR.")
    add_check(checks, "repositories", repo_diag["repositories"] == args.expected_repositories, repo_diag["repositories"], args.expected_repositories, "Preserve frozen Model A repository universe.")
    add_check(checks, "repo_months", repo_diag["repo_months"] == args.expected_repo_months, repo_diag["repo_months"], args.expected_repo_months, "Preserve frozen Model A repo-month universe.")
    add_check(checks, "snapshot_count_file", file_diag["snapshots"] == args.expected_snapshots, file_diag["snapshots"], args.expected_snapshots, "Preserve all historical snapshots in snapshot/file output.")
    add_check(checks, "snapshot_count_repo_month", repo_diag["snapshots"] == args.expected_snapshots, repo_diag["snapshots"], args.expected_snapshots, "Preserve all historical snapshots in repo-month/file output.")

    hard_failures = [row for row in checks if row["passed"] != "1"]
    if args.strict_expected_counts and hard_failures:
        status = "FAIL"
    elif hard_failures:
        status = "PASS_WITH_QC_WARNINGS"
    elif file_diag["rows_with_expected_exclusions"] or repo_diag["rows_with_expected_exclusions"]:
        status = "PASS_WITH_EXPECTED_EXCLUSIONS"
    else:
        status = "PASS"

    write_checks(checks_output, checks)
    summary = {
        "script_version": SCRIPT_VERSION,
        "status": status,
        "started_utc": started,
        "completed_utc": utc_now(),
        "scope": "combined FUN + C_FUN procedure-body file NPR",
        "a05_code_manifest_sha256": a12_summary.get("a05_code_manifest_sha256"),
        "a12": {"script_version": a12_summary.get("script_version"), "status": a12_summary.get("status")},
        "a15": {"script_version": a15_summary.get("script_version"), "status": a15_summary.get("status")},
        "snapshot_files": file_diag,
        "repo_month_files": repo_diag,
        "hard_check_failures": len(hard_failures),
        "hard_check_failure_names": [row["check_name"] for row in hard_failures],
        "methodology": {
            "fun_category": "A12 primary regular-function body occurrences",
            "cfun_category": "A15 primary class-method body occurrences",
            "combined_weighting": "space-by-token weighted recomputation across finite FUN and C_FUN category sufficient statistics",
            "pooled_component_npr": "combined weighted mean perturbed log-rank divided by combined weighted mean original log-rank",
            "single_category_policy": "if exactly one category has finite NPR, combined NPR equals that category NPR",
            "no_coverage_policy": "if neither category has finite NPR, combined NPR is blank, never zero",
            "cross_category_sha_policy": "semantic occurrences are retained; no cross-category SHA deduplication is performed",
            "classification": "disabled; no threshold or AI-likely label is produced",
            "quality_outcomes": "not consumed",
        },
        "outputs": {
            "snapshot_file_scores": str(file_output),
            "repo_month_file_scores": str(repo_month_output),
            "checks": str(checks_output),
        },
    }
    atomic_json(summary, output_dir / "summary.json")
    metadata = {
        "script_version": SCRIPT_VERSION,
        "created_utc": utc_now(),
        "inputs": {
            "a12_file": str(a12_file),
            "a12_repo_month_file": str(a12_repo_month),
            "a12_summary": str(a12_summary_path),
            "a15_file": str(a15_file),
            "a15_repo_month_file": str(a15_repo_month),
            "a15_summary": str(a15_summary_path),
        },
        "summary_sha256": {"a12": file_sha256(a12_summary_path), "a15": file_sha256(a15_summary_path)},
        "quality_outcome_inputs_consumed": False,
        "threshold_applied": False,
        "expected_counts": {
            "file_rows": args.expected_file_rows,
            "repo_month_file_rows": args.expected_repo_month_file_rows,
            "repositories": args.expected_repositories,
            "repo_months": args.expected_repo_months,
            "snapshots": args.expected_snapshots,
            "combined_file_finite_npr": EXPECTED_COMBINED_FILE_FINITE,
            "combined_repo_month_finite_npr": EXPECTED_COMBINED_REPO_MONTH_FINITE,
        },
    }
    atomic_json(metadata, output_dir / "metadata.json")

    print("=" * 80)
    print("run-x-i01 combined FUN + C_FUN file-NPR aggregation")
    print(f"Status:                                      {status}")
    print(f"Snapshot/file rows:                          {file_diag['rows']}")
    print(f"Snapshot/file finite FUN / C_FUN / combined: {file_diag['finite_fun_npr_rows']} / {file_diag['finite_cfun_npr_rows']} / {file_diag['finite_combined_npr_rows']}")
    print(f"Repo-month/file rows:                        {repo_diag['rows']}")
    print(f"Repo-month finite FUN / C_FUN / combined:    {repo_diag['finite_fun_npr_rows']} / {repo_diag['finite_cfun_npr_rows']} / {repo_diag['finite_combined_npr_rows']}")
    print(f"Combined finite patterns (repo-month/file):  {repo_diag['finite_npr_pattern_counts']}")
    print(f"Combined status counts (repo-month/file):    {repo_diag['status_counts']}")
    print(f"Repositories / repo-months / snapshots:      {repo_diag['repositories']} / {repo_diag['repo_months']} / {repo_diag['snapshots']}")
    print(f"Hard QC failures:                            {len(hard_failures)}")
    print(f"Snapshot/file output:                        {file_output}")
    print(f"Repo-month/file output:                      {repo_month_output}")
    print(f"Checks:                                      {checks_output}")
    print("Threshold/classification:                    none")
    print("Quality/SonarQube inputs:                    none")
    print("=" * 80)
    return 2 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
