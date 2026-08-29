#!/usr/bin/env python3
"""Aggregate finalized FUN and class-method ML file measurements.

I06 is a CPU-only detector-measurement aggregation stage for the Python
longitudinal quality study. It combines the finalized A04 regular-function ML
file measurements and the finalized A07 class-method ML file measurements on
the same frozen historical Python-file universe.

The primary combined ML quantity is recomputed from token numerators and
denominators rather than averaging the two file-level shares:

    combined_agc_share =
        (FUN_AGC_body_tokens + method_AGC_body_tokens)
        / (FUN_body_tokens + method_body_tokens)

The combined primary file flag is 1 only when the recomputed share is strictly
greater than 0.50. Files with neither regular-function nor class-method ML
coverage remain unclassified; they are never imputed as HWC. Cross-category
source hashes are not deduplicated because regular functions and class methods
are distinct semantic procedure occurrences.

I06 does not run ML inference, SonarQube, or DiD estimation and does not inspect
any quality outcome.

Inputs
------
A04:
  python_ml_fun_file_scores.csv
  summary.json

A07:
  python_ml_cfun_file_scores.csv
  summary.json

Outputs
-------
  python_ml_fun_cfun_file_scores.csv
  python_ml_fun_cfun_selected_files_primary.csv
  python_ml_fun_cfun_threshold_support.csv
  python_ml_fun_cfun_aggregation_checks.csv
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCRIPT_VERSION = "run-x-i06-v1"
PRIMARY_THRESHOLD = 0.50
SUPPORT_THRESHOLDS = (0.00, 0.25, 0.50, 0.75)

EXPECTED_FILE_ROWS = 494_592
EXPECTED_PREPARED_FILES = 494_332
EXPECTED_NOT_PREPARED_FILES = 260

EXPECTED_A04_FILES_WITH_FUN = 196_644
EXPECTED_A04_SELECTED_PRIMARY = 41_905
EXPECTED_A04_OCCURRENCES = 921_762
EXPECTED_A04_AGC_OCCURRENCES = 290_926
EXPECTED_A04_HWC_OCCURRENCES = 630_836
EXPECTED_A04_TOTAL_SPACE_TOKENS = 152_001_674
EXPECTED_A04_AGC_SPACE_TOKENS = 13_202_081

EXPECTED_A07_FILES_WITH_CFUN = 196_190
EXPECTED_A07_SELECTED_PRIMARY = 36_556
EXPECTED_A07_OCCURRENCES = 1_677_916
EXPECTED_A07_AGC_OCCURRENCES = 526_910
EXPECTED_A07_HWC_OCCURRENCES = 1_151_006
EXPECTED_A07_TOTAL_SPACE_TOKENS = 327_251_880
EXPECTED_A07_AGC_SPACE_TOKENS = 23_686_235

EXPECTED_COMBINED_OCCURRENCES = EXPECTED_A04_OCCURRENCES + EXPECTED_A07_OCCURRENCES
EXPECTED_COMBINED_AGC_OCCURRENCES = EXPECTED_A04_AGC_OCCURRENCES + EXPECTED_A07_AGC_OCCURRENCES
EXPECTED_COMBINED_HWC_OCCURRENCES = EXPECTED_A04_HWC_OCCURRENCES + EXPECTED_A07_HWC_OCCURRENCES
EXPECTED_COMBINED_TOTAL_SPACE_TOKENS = EXPECTED_A04_TOTAL_SPACE_TOKENS + EXPECTED_A07_TOTAL_SPACE_TOKENS
EXPECTED_COMBINED_AGC_SPACE_TOKENS = EXPECTED_A04_AGC_SPACE_TOKENS + EXPECTED_A07_AGC_SPACE_TOKENS
EXPECTED_COMBINED_HWC_SPACE_TOKENS = EXPECTED_COMBINED_TOTAL_SPACE_TOKENS - EXPECTED_COMBINED_AGC_SPACE_TOKENS

ACCEPTABLE_UPSTREAM_STATUSES = {"PASS", "PASS_WITH_WARNINGS"}

IDENTITY_COLUMNS = [
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

FUN_REQUIRED_COLUMNS = IDENTITY_COLUMNS + [
    "ml_fun_occurrences_total",
    "ml_fun_agc_occurrences",
    "ml_fun_hwc_occurrences",
    "ml_fun_space_by_tokens_total",
    "ml_fun_agc_space_by_tokens",
    "ml_fun_hwc_space_by_tokens",
    "file_ml_agc_share_by_count",
    "file_ml_agc_share_space_by_token_weighted",
    "file_ml_human_decision_score_space_by_token_weighted",
    "file_ml_agc_score_space_by_token_weighted",
    "ml_fun_mapping_warning_occurrences",
    "ml_fun_mapping_warning_present",
    "file_ml_agc_like_primary",
    "file_ml_agc_primary_threshold",
    "file_ml_agc_primary_operator",
    "file_ml_agc_status",
]

CFUN_REQUIRED_COLUMNS = IDENTITY_COLUMNS + [
    "ml_cfun_occurrences_total",
    "ml_cfun_agc_occurrences",
    "ml_cfun_hwc_occurrences",
    "ml_cfun_space_by_tokens_total",
    "ml_cfun_agc_space_by_tokens",
    "ml_cfun_hwc_space_by_tokens",
    "file_ml_cfun_agc_share_by_count",
    "file_ml_cfun_agc_share_space_by_token_weighted",
    "file_ml_cfun_human_decision_score_space_by_token_weighted",
    "file_ml_cfun_agc_score_space_by_token_weighted",
    "ml_cfun_mapping_warning_occurrences",
    "ml_cfun_mapping_warning_present",
    "file_ml_cfun_agc_like_primary",
    "file_ml_cfun_agc_primary_threshold",
    "file_ml_cfun_agc_primary_operator",
    "file_ml_cfun_agc_status",
]

OUTPUT_COLUMNS = IDENTITY_COLUMNS + [
    "fun_present",
    "class_method_present",
    "procedure_presence_pattern",
    "ml_fun_occurrences_total",
    "ml_fun_agc_occurrences",
    "ml_fun_hwc_occurrences",
    "ml_fun_space_by_tokens_total",
    "ml_fun_agc_space_by_tokens",
    "file_ml_agc_share_space_by_token_weighted",
    "file_ml_agc_like_primary",
    "file_ml_agc_status",
    "ml_cfun_occurrences_total",
    "ml_cfun_agc_occurrences",
    "ml_cfun_hwc_occurrences",
    "ml_cfun_space_by_tokens_total",
    "ml_cfun_agc_space_by_tokens",
    "file_ml_cfun_agc_share_space_by_token_weighted",
    "file_ml_cfun_agc_like_primary",
    "file_ml_cfun_agc_status",
    "ml_fun_cfun_occurrences_total",
    "ml_fun_cfun_agc_occurrences",
    "ml_fun_cfun_hwc_occurrences",
    "ml_fun_cfun_space_by_tokens_total",
    "ml_fun_cfun_agc_space_by_tokens",
    "ml_fun_cfun_hwc_space_by_tokens",
    "file_ml_fun_cfun_agc_share_by_count",
    "file_ml_fun_cfun_agc_share_space_by_token_weighted",
    "file_ml_fun_cfun_human_decision_score_space_by_token_weighted",
    "file_ml_fun_cfun_agc_score_space_by_token_weighted",
    "ml_fun_mapping_warning_occurrences",
    "ml_cfun_mapping_warning_occurrences",
    "ml_fun_cfun_mapping_warning_occurrences",
    "ml_fun_mapping_warning_present",
    "ml_cfun_mapping_warning_present",
    "ml_fun_cfun_mapping_warning_present",
    "file_ml_fun_cfun_agc_like_primary",
    "file_ml_fun_cfun_agc_primary_threshold",
    "file_ml_fun_cfun_agc_primary_operator",
    "file_ml_fun_cfun_agc_status",
]

SELECTED_OUTPUT_COLUMNS = [
    "snapshot_id",
    "dataset_source",
    "repo_name",
    "repo_key",
    "snapshot_time",
    "snapshot_commit",
    "relative_path",
    "file_sha256",
    "python_lines",
    "procedure_presence_pattern",
    "ml_fun_cfun_occurrences_total",
    "ml_fun_cfun_agc_occurrences",
    "ml_fun_cfun_space_by_tokens_total",
    "ml_fun_cfun_agc_space_by_tokens",
    "file_ml_fun_cfun_agc_share_by_count",
    "file_ml_fun_cfun_agc_share_space_by_token_weighted",
    "file_ml_fun_cfun_human_decision_score_space_by_token_weighted",
    "file_ml_fun_cfun_agc_score_space_by_token_weighted",
    "ml_fun_cfun_mapping_warning_present",
    "file_ml_fun_cfun_agc_like_primary",
]

SUPPORT_COLUMNS = [
    "dataset_source",
    "threshold",
    "operator",
    "python_file_rows",
    "prepared_file_rows",
    "files_with_fun_or_class_method",
    "selected_files",
    "selected_share_of_eligible_files",
    "selected_share_of_python_files",
    "ties_at_threshold",
]

CHECK_COLUMNS = ["check_name", "severity", "passed", "observed", "expected", "note"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_nonnegative_int(value: Any, field: str, context: str) -> int:
    text = clean(value)
    if text == "":
        raise ValueError(f"Blank integer {field} in {context}")
    parsed = int(text)
    if parsed < 0:
        raise ValueError(f"Negative integer {field}={parsed} in {context}")
    return parsed


def parse_optional_float(value: Any, field: str, context: str) -> float | None:
    text = clean(value)
    if text == "":
        return None
    parsed = float(text)
    if not math.isfinite(parsed):
        raise ValueError(f"Non-finite float {field}={text!r} in {context}")
    return parsed


def parse_binary_or_blank(value: Any, field: str, context: str) -> int | None:
    text = clean(value)
    if text == "":
        return None
    parsed = int(text)
    if parsed not in {0, 1}:
        raise ValueError(f"Expected binary {field}, got {text!r} in {context}")
    return parsed


def finite_or_blank(value: float | None) -> str:
    if value is None:
        return ""
    if not math.isfinite(value):
        raise ValueError(f"Cannot serialize non-finite value: {value}")
    return format(value, ".17g")


def require_columns(fieldnames: list[str] | None, required: list[str], label: str) -> None:
    if fieldnames is None:
        raise ValueError(f"{label} has no CSV header")
    missing = [name for name in required if name not in fieldnames]
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def atomic_write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


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
            "observed": observed,
            "expected": expected,
            "note": note,
        }
    )


def presence_pattern(fun_present: bool, class_method_present: bool) -> str:
    if fun_present and class_method_present:
        return "fun_and_class_method"
    if fun_present:
        return "fun_only"
    if class_method_present:
        return "class_method_only"
    return "neither"


def validate_primary_rule(summary: dict[str, Any], expected_metric: str, label: str) -> None:
    rule = summary.get("primary_file_rule")
    if not isinstance(rule, dict):
        raise ValueError(f"{label} summary missing primary_file_rule")
    if clean(rule.get("metric")) != expected_metric:
        raise ValueError(f"{label} primary metric mismatch: {rule.get('metric')!r}")
    if clean(rule.get("operator")) != ">":
        raise ValueError(f"{label} primary operator is not strict >")
    threshold = float(rule.get("threshold"))
    if not math.isclose(threshold, PRIMARY_THRESHOLD, rel_tol=0.0, abs_tol=1e-15):
        raise ValueError(f"{label} primary threshold mismatch: {threshold}")


def validate_upstream_summaries(a04: dict[str, Any], a07: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    validate_primary_rule(a04, "file_ml_agc_share_space_by_token_weighted", "A04")
    validate_primary_rule(a07, "file_ml_cfun_agc_share_space_by_token_weighted", "A07")

    add_check(
        checks,
        "a04_status",
        clean(a04.get("status")) in ACCEPTABLE_UPSTREAM_STATUSES,
        a04.get("status"),
        "PASS|PASS_WITH_WARNINGS",
        "A04 must be finalized successfully.",
    )
    add_check(
        checks,
        "a07_status",
        clean(a07.get("status")) in ACCEPTABLE_UPSTREAM_STATUSES,
        a07.get("status"),
        "PASS|PASS_WITH_WARNINGS",
        "A07 must be finalized successfully.",
    )
    add_check(checks, "a04_failed_hard_checks", int(a04.get("failed_hard_checks", -1)) == 0, a04.get("failed_hard_checks"), 0, "A04 hard checks must be zero.")
    add_check(checks, "a07_failed_hard_checks", int(a07.get("failed_hard_checks", -1)) == 0, a07.get("failed_hard_checks"), 0, "A07 hard checks must be zero.")

    expected_pairs = [
        ("a04_file_rows", a04.get("files", {}).get("file_rows"), EXPECTED_FILE_ROWS),
        ("a04_files_with_fun", a04.get("files", {}).get("files_with_fun"), EXPECTED_A04_FILES_WITH_FUN),
        ("a04_selected_primary", a04.get("files", {}).get("selected_primary_files"), EXPECTED_A04_SELECTED_PRIMARY),
        ("a04_occurrences", a04.get("files", {}).get("sum_file_occurrences"), EXPECTED_A04_OCCURRENCES),
        ("a04_agc_occurrences", a04.get("files", {}).get("sum_file_agc_occurrences"), EXPECTED_A04_AGC_OCCURRENCES),
        ("a04_total_space_tokens", a04.get("files", {}).get("sum_file_space_by_tokens"), EXPECTED_A04_TOTAL_SPACE_TOKENS),
        ("a04_agc_space_tokens", a04.get("files", {}).get("sum_file_agc_space_by_tokens"), EXPECTED_A04_AGC_SPACE_TOKENS),
        ("a07_file_rows", a07.get("files", {}).get("file_rows"), EXPECTED_FILE_ROWS),
        ("a07_files_with_cfun", a07.get("files", {}).get("files_with_cfun"), EXPECTED_A07_FILES_WITH_CFUN),
        ("a07_selected_primary", a07.get("files", {}).get("selected_primary_files"), EXPECTED_A07_SELECTED_PRIMARY),
        ("a07_occurrences", a07.get("files", {}).get("sum_file_occurrences"), EXPECTED_A07_OCCURRENCES),
        ("a07_agc_occurrences", a07.get("files", {}).get("sum_file_agc_occurrences"), EXPECTED_A07_AGC_OCCURRENCES),
        ("a07_total_space_tokens", a07.get("files", {}).get("sum_file_space_by_tokens"), EXPECTED_A07_TOTAL_SPACE_TOKENS),
        ("a07_agc_space_tokens", a07.get("files", {}).get("sum_file_agc_space_by_tokens"), EXPECTED_A07_AGC_SPACE_TOKENS),
    ]
    for name, observed, expected in expected_pairs:
        add_check(checks, name, int(observed) == expected, observed, expected, "Frozen upstream accounting must match the finalized production artifact.")


def parse_category(row: dict[str, str], prefix: str, context: str) -> dict[str, Any]:
    if prefix == "fun":
        status_field = "file_ml_agc_status"
        status_scored = "scored"
        status_empty = "no_ml_fun"
        occurrence_total_field = "ml_fun_occurrences_total"
        occurrence_agc_field = "ml_fun_agc_occurrences"
        occurrence_hwc_field = "ml_fun_hwc_occurrences"
        token_total_field = "ml_fun_space_by_tokens_total"
        token_agc_field = "ml_fun_agc_space_by_tokens"
        token_hwc_field = "ml_fun_hwc_space_by_tokens"
        count_share_field = "file_ml_agc_share_by_count"
        token_share_field = "file_ml_agc_share_space_by_token_weighted"
        human_score_field = "file_ml_human_decision_score_space_by_token_weighted"
        agc_score_field = "file_ml_agc_score_space_by_token_weighted"
        warning_occ_field = "ml_fun_mapping_warning_occurrences"
        warning_present_field = "ml_fun_mapping_warning_present"
        primary_flag_field = "file_ml_agc_like_primary"
        primary_threshold_field = "file_ml_agc_primary_threshold"
        primary_operator_field = "file_ml_agc_primary_operator"
    else:
        status_field = "file_ml_cfun_agc_status"
        status_scored = "scored"
        status_empty = "no_ml_cfun"
        occurrence_total_field = "ml_cfun_occurrences_total"
        occurrence_agc_field = "ml_cfun_agc_occurrences"
        occurrence_hwc_field = "ml_cfun_hwc_occurrences"
        token_total_field = "ml_cfun_space_by_tokens_total"
        token_agc_field = "ml_cfun_agc_space_by_tokens"
        token_hwc_field = "ml_cfun_hwc_space_by_tokens"
        count_share_field = "file_ml_cfun_agc_share_by_count"
        token_share_field = "file_ml_cfun_agc_share_space_by_token_weighted"
        human_score_field = "file_ml_cfun_human_decision_score_space_by_token_weighted"
        agc_score_field = "file_ml_cfun_agc_score_space_by_token_weighted"
        warning_occ_field = "ml_cfun_mapping_warning_occurrences"
        warning_present_field = "ml_cfun_mapping_warning_present"
        primary_flag_field = "file_ml_cfun_agc_like_primary"
        primary_threshold_field = "file_ml_cfun_agc_primary_threshold"
        primary_operator_field = "file_ml_cfun_agc_primary_operator"

    status = clean(row.get(status_field))
    if status not in {status_scored, status_empty, "file_not_prepared"}:
        raise ValueError(f"Unexpected {prefix} status {status!r} in {context}")

    occurrences_total = parse_nonnegative_int(row.get(occurrence_total_field), occurrence_total_field, context)
    occurrences_agc = parse_nonnegative_int(row.get(occurrence_agc_field), occurrence_agc_field, context)
    occurrences_hwc = parse_nonnegative_int(row.get(occurrence_hwc_field), occurrence_hwc_field, context)
    tokens_total = parse_nonnegative_int(row.get(token_total_field), token_total_field, context)
    tokens_agc = parse_nonnegative_int(row.get(token_agc_field), token_agc_field, context)
    tokens_hwc = parse_nonnegative_int(row.get(token_hwc_field), token_hwc_field, context)
    count_share = parse_optional_float(row.get(count_share_field), count_share_field, context)
    token_share = parse_optional_float(row.get(token_share_field), token_share_field, context)
    human_score = parse_optional_float(row.get(human_score_field), human_score_field, context)
    agc_score = parse_optional_float(row.get(agc_score_field), agc_score_field, context)
    warning_occurrences = parse_nonnegative_int(row.get(warning_occ_field), warning_occ_field, context)
    warning_present = parse_binary_or_blank(row.get(warning_present_field), warning_present_field, context)
    primary_flag = parse_binary_or_blank(row.get(primary_flag_field), primary_flag_field, context)
    threshold = parse_optional_float(row.get(primary_threshold_field), primary_threshold_field, context)
    operator = clean(row.get(primary_operator_field))

    if occurrences_agc + occurrences_hwc != occurrences_total:
        raise ValueError(f"{prefix} occurrence accounting mismatch in {context}")
    if tokens_agc + tokens_hwc != tokens_total:
        raise ValueError(f"{prefix} token accounting mismatch in {context}")
    if warning_present != (1 if warning_occurrences > 0 else 0):
        raise ValueError(f"{prefix} mapping-warning flag mismatch in {context}")

    if status == status_scored:
        if occurrences_total <= 0 or tokens_total <= 0:
            raise ValueError(f"Scored {prefix} row has zero support in {context}")
        if any(value is None for value in (count_share, token_share, human_score, agc_score, primary_flag, threshold)):
            raise ValueError(f"Scored {prefix} row has blank metric/flag in {context}")
        if operator != ">" or not math.isclose(float(threshold), PRIMARY_THRESHOLD, rel_tol=0.0, abs_tol=1e-15):
            raise ValueError(f"Scored {prefix} row primary rule mismatch in {context}")
        expected_count_share = occurrences_agc / occurrences_total
        expected_token_share = tokens_agc / tokens_total
        if not math.isclose(float(count_share), expected_count_share, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"{prefix} count-share mismatch in {context}")
        if not math.isclose(float(token_share), expected_token_share, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"{prefix} token-share mismatch in {context}")
        if not math.isclose(float(agc_score), -float(human_score), rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"{prefix} weighted score sign mismatch in {context}")
        expected_primary = 1 if float(token_share) > PRIMARY_THRESHOLD else 0
        if primary_flag != expected_primary:
            raise ValueError(f"{prefix} strict primary flag mismatch in {context}")
    else:
        if occurrences_total != 0 or tokens_total != 0:
            raise ValueError(f"Unclassified {prefix} row carries procedure support in {context}")
        if any(value is not None for value in (count_share, token_share, human_score, agc_score, primary_flag, threshold)):
            raise ValueError(f"Unclassified {prefix} row carries ML metric/flag in {context}")
        if operator != "":
            raise ValueError(f"Unclassified {prefix} row carries primary operator in {context}")

    return {
        "status": status,
        "present": status == status_scored,
        "occurrences_total": occurrences_total,
        "occurrences_agc": occurrences_agc,
        "occurrences_hwc": occurrences_hwc,
        "tokens_total": tokens_total,
        "tokens_agc": tokens_agc,
        "tokens_hwc": tokens_hwc,
        "count_share": count_share,
        "token_share": token_share,
        "human_score": human_score,
        "agc_score": agc_score,
        "warning_occurrences": warning_occurrences,
        "warning_present": int(warning_present or 0),
        "primary_flag": primary_flag,
    }


def combine_categories(fun: dict[str, Any], cfun: dict[str, Any], parse_status: str, context: str) -> dict[str, Any]:
    fun_not_prepared = fun["status"] == "file_not_prepared"
    cfun_not_prepared = cfun["status"] == "file_not_prepared"
    if fun_not_prepared != cfun_not_prepared:
        raise ValueError(f"A04/A07 preparation status mismatch in {context}")

    prepared = clean(parse_status).casefold() == "prepared"
    if prepared == fun_not_prepared:
        raise ValueError(f"parse_status and ML preparation status disagree in {context}")

    occurrences_total = fun["occurrences_total"] + cfun["occurrences_total"]
    occurrences_agc = fun["occurrences_agc"] + cfun["occurrences_agc"]
    occurrences_hwc = fun["occurrences_hwc"] + cfun["occurrences_hwc"]
    tokens_total = fun["tokens_total"] + cfun["tokens_total"]
    tokens_agc = fun["tokens_agc"] + cfun["tokens_agc"]
    tokens_hwc = fun["tokens_hwc"] + cfun["tokens_hwc"]

    if occurrences_agc + occurrences_hwc != occurrences_total:
        raise ValueError(f"Combined occurrence accounting mismatch in {context}")
    if tokens_agc + tokens_hwc != tokens_total:
        raise ValueError(f"Combined token accounting mismatch in {context}")

    if fun_not_prepared and cfun_not_prepared:
        status = "file_not_prepared"
    elif occurrences_total == 0:
        status = "no_ml_fun_cfun"
    else:
        status = "scored"

    combined_count_share: float | None = None
    combined_token_share: float | None = None
    combined_human_score: float | None = None
    combined_agc_score: float | None = None
    combined_primary: int | None = None

    if status == "scored":
        if occurrences_total <= 0 or tokens_total <= 0:
            raise ValueError(f"Combined scored row has zero support in {context}")
        combined_count_share = occurrences_agc / occurrences_total
        combined_token_share = tokens_agc / tokens_total
        weighted_human_sum = 0.0
        weighted_agc_sum = 0.0
        for category in (fun, cfun):
            if category["present"]:
                weighted_human_sum += category["tokens_total"] * float(category["human_score"])
                weighted_agc_sum += category["tokens_total"] * float(category["agc_score"])
        combined_human_score = weighted_human_sum / tokens_total
        combined_agc_score = weighted_agc_sum / tokens_total
        if not math.isclose(combined_agc_score, -combined_human_score, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"Combined weighted score sign mismatch in {context}")
        combined_primary = 1 if combined_token_share > PRIMARY_THRESHOLD else 0

        if fun["present"] and not cfun["present"]:
            if not math.isclose(combined_token_share, float(fun["token_share"]), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"FUN-only combined share mismatch in {context}")
        if cfun["present"] and not fun["present"]:
            if not math.isclose(combined_token_share, float(cfun["token_share"]), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"Class-method-only combined share mismatch in {context}")
        if fun["present"] and cfun["present"]:
            lower = min(float(fun["token_share"]), float(cfun["token_share"]))
            upper = max(float(fun["token_share"]), float(cfun["token_share"]))
            if not (lower - 1e-12 <= combined_token_share <= upper + 1e-12):
                raise ValueError(f"Combined share is outside component range in {context}")

    warning_occurrences = fun["warning_occurrences"] + cfun["warning_occurrences"]
    warning_present = 1 if warning_occurrences > 0 else 0

    return {
        "status": status,
        "occurrences_total": occurrences_total,
        "occurrences_agc": occurrences_agc,
        "occurrences_hwc": occurrences_hwc,
        "tokens_total": tokens_total,
        "tokens_agc": tokens_agc,
        "tokens_hwc": tokens_hwc,
        "count_share": combined_count_share,
        "token_share": combined_token_share,
        "human_score": combined_human_score,
        "agc_score": combined_agc_score,
        "primary_flag": combined_primary,
        "warning_occurrences": warning_occurrences,
        "warning_present": warning_present,
        "pattern": presence_pattern(fun["present"], cfun["present"]),
    }


def build_output_row(identity: dict[str, str], fun: dict[str, Any], cfun: dict[str, Any], combined: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {name: identity[name] for name in IDENTITY_COLUMNS}
    row.update(
        {
            "fun_present": 1 if fun["present"] else 0,
            "class_method_present": 1 if cfun["present"] else 0,
            "procedure_presence_pattern": combined["pattern"],
            "ml_fun_occurrences_total": fun["occurrences_total"],
            "ml_fun_agc_occurrences": fun["occurrences_agc"],
            "ml_fun_hwc_occurrences": fun["occurrences_hwc"],
            "ml_fun_space_by_tokens_total": fun["tokens_total"],
            "ml_fun_agc_space_by_tokens": fun["tokens_agc"],
            "file_ml_agc_share_space_by_token_weighted": finite_or_blank(fun["token_share"]),
            "file_ml_agc_like_primary": "" if fun["primary_flag"] is None else fun["primary_flag"],
            "file_ml_agc_status": fun["status"],
            "ml_cfun_occurrences_total": cfun["occurrences_total"],
            "ml_cfun_agc_occurrences": cfun["occurrences_agc"],
            "ml_cfun_hwc_occurrences": cfun["occurrences_hwc"],
            "ml_cfun_space_by_tokens_total": cfun["tokens_total"],
            "ml_cfun_agc_space_by_tokens": cfun["tokens_agc"],
            "file_ml_cfun_agc_share_space_by_token_weighted": finite_or_blank(cfun["token_share"]),
            "file_ml_cfun_agc_like_primary": "" if cfun["primary_flag"] is None else cfun["primary_flag"],
            "file_ml_cfun_agc_status": cfun["status"],
            "ml_fun_cfun_occurrences_total": combined["occurrences_total"],
            "ml_fun_cfun_agc_occurrences": combined["occurrences_agc"],
            "ml_fun_cfun_hwc_occurrences": combined["occurrences_hwc"],
            "ml_fun_cfun_space_by_tokens_total": combined["tokens_total"],
            "ml_fun_cfun_agc_space_by_tokens": combined["tokens_agc"],
            "ml_fun_cfun_hwc_space_by_tokens": combined["tokens_hwc"],
            "file_ml_fun_cfun_agc_share_by_count": finite_or_blank(combined["count_share"]),
            "file_ml_fun_cfun_agc_share_space_by_token_weighted": finite_or_blank(combined["token_share"]),
            "file_ml_fun_cfun_human_decision_score_space_by_token_weighted": finite_or_blank(combined["human_score"]),
            "file_ml_fun_cfun_agc_score_space_by_token_weighted": finite_or_blank(combined["agc_score"]),
            "ml_fun_mapping_warning_occurrences": fun["warning_occurrences"],
            "ml_cfun_mapping_warning_occurrences": cfun["warning_occurrences"],
            "ml_fun_cfun_mapping_warning_occurrences": combined["warning_occurrences"],
            "ml_fun_mapping_warning_present": fun["warning_present"],
            "ml_cfun_mapping_warning_present": cfun["warning_present"],
            "ml_fun_cfun_mapping_warning_present": combined["warning_present"],
            "file_ml_fun_cfun_agc_like_primary": "" if combined["primary_flag"] is None else combined["primary_flag"],
            "file_ml_fun_cfun_agc_primary_threshold": PRIMARY_THRESHOLD if combined["status"] == "scored" else "",
            "file_ml_fun_cfun_agc_primary_operator": ">" if combined["status"] == "scored" else "",
            "file_ml_fun_cfun_agc_status": combined["status"],
        }
    )
    return row


def aggregate_files(
    a04_file: Path,
    a07_file: Path,
    output_file: Path,
    selected_file: Path,
    expected_rows: int,
) -> dict[str, Any]:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    out_fd, out_temp_name = tempfile.mkstemp(prefix=output_file.name + ".", suffix=".tmp", dir=output_file.parent)
    selected_fd, selected_temp_name = tempfile.mkstemp(prefix=selected_file.name + ".", suffix=".tmp", dir=selected_file.parent)

    rows = 0
    prepared_rows = 0
    not_prepared_rows = 0
    eligible_rows = 0
    selected_rows = 0
    exact_primary_ties = 0
    mapping_warning_rows = 0
    fun_selected_rows = 0
    cfun_selected_rows = 0
    source_primary_union_rows = 0
    source_primary_intersection_rows = 0
    combined_selected_without_source_primary = 0
    status_counts: Counter[str] = Counter()
    pattern_counts: Counter[str] = Counter()
    dataset_file_counts: Counter[str] = Counter()
    dataset_prepared_counts: Counter[str] = Counter()
    dataset_eligible_counts: Counter[str] = Counter()
    support_selected: dict[tuple[str, float], int] = defaultdict(int)
    support_ties: dict[tuple[str, float], int] = defaultdict(int)

    sums = Counter()

    try:
        with os.fdopen(out_fd, "w", encoding="utf-8", newline="") as out_handle, os.fdopen(
            selected_fd, "w", encoding="utf-8", newline=""
        ) as selected_handle, a04_file.open("r", encoding="utf-8", newline="", buffering=1024 * 1024) as fun_handle, a07_file.open(
            "r", encoding="utf-8", newline="", buffering=1024 * 1024
        ) as cfun_handle:
            fun_reader = csv.DictReader(fun_handle)
            cfun_reader = csv.DictReader(cfun_handle)
            require_columns(fun_reader.fieldnames, FUN_REQUIRED_COLUMNS, "A04 file scores")
            require_columns(cfun_reader.fieldnames, CFUN_REQUIRED_COLUMNS, "A07 file scores")

            out_writer = csv.DictWriter(out_handle, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore", lineterminator="\n")
            selected_writer = csv.DictWriter(selected_handle, fieldnames=SELECTED_OUTPUT_COLUMNS, extrasaction="ignore", lineterminator="\n")
            out_writer.writeheader()
            selected_writer.writeheader()

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
                    raise ValueError(f"A04/A07 row-count mismatch near row {rows + 1}")

                rows += 1
                identity = {name: clean(fun_row.get(name)) for name in IDENTITY_COLUMNS}
                cfun_identity = {name: clean(cfun_row.get(name)) for name in IDENTITY_COLUMNS}
                if identity != cfun_identity:
                    differences = [
                        f"{name}: A04={identity[name]!r} A07={cfun_identity[name]!r}"
                        for name in IDENTITY_COLUMNS
                        if identity[name] != cfun_identity[name]
                    ]
                    raise ValueError(f"A04/A07 identity mismatch at row {rows}: " + "; ".join(differences[:8]))

                context = f"row={rows} snapshot={identity['snapshot_id']} path={identity['relative_path']}"
                fun = parse_category(fun_row, "fun", context)
                cfun = parse_category(cfun_row, "cfun", context)
                combined = combine_categories(fun, cfun, identity["parse_status"], context)
                output_row = build_output_row(identity, fun, cfun, combined)
                out_writer.writerow(output_row)

                dataset = identity["dataset_source"]
                dataset_file_counts[dataset] += 1
                dataset_file_counts["all"] += 1
                if identity["parse_status"].casefold() == "prepared":
                    prepared_rows += 1
                    dataset_prepared_counts[dataset] += 1
                    dataset_prepared_counts["all"] += 1
                else:
                    not_prepared_rows += 1

                status_counts[combined["status"]] += 1
                pattern_counts[combined["pattern"]] += 1
                eligible = combined["status"] == "scored"
                if eligible:
                    eligible_rows += 1
                    dataset_eligible_counts[dataset] += 1
                    dataset_eligible_counts["all"] += 1
                    share = float(combined["token_share"])
                    for threshold in SUPPORT_THRESHOLDS:
                        for group in (dataset, "all"):
                            if share > threshold:
                                support_selected[(group, threshold)] += 1
                            if math.isclose(share, threshold, rel_tol=0.0, abs_tol=1e-15):
                                support_ties[(group, threshold)] += 1
                    if math.isclose(share, PRIMARY_THRESHOLD, rel_tol=0.0, abs_tol=1e-15):
                        exact_primary_ties += 1
                    if combined["primary_flag"] == 1:
                        selected_rows += 1
                        selected_writer.writerow(output_row)

                fun_primary = fun["primary_flag"] == 1
                cfun_primary = cfun["primary_flag"] == 1
                if fun_primary:
                    fun_selected_rows += 1
                if cfun_primary:
                    cfun_selected_rows += 1
                if fun_primary or cfun_primary:
                    source_primary_union_rows += 1
                if fun_primary and cfun_primary:
                    source_primary_intersection_rows += 1
                if combined["primary_flag"] == 1 and not (fun_primary or cfun_primary):
                    combined_selected_without_source_primary += 1
                if combined["warning_present"] == 1:
                    mapping_warning_rows += 1

                sums["fun_occurrences"] += fun["occurrences_total"]
                sums["fun_agc_occurrences"] += fun["occurrences_agc"]
                sums["fun_hwc_occurrences"] += fun["occurrences_hwc"]
                sums["fun_tokens"] += fun["tokens_total"]
                sums["fun_agc_tokens"] += fun["tokens_agc"]
                sums["cfun_occurrences"] += cfun["occurrences_total"]
                sums["cfun_agc_occurrences"] += cfun["occurrences_agc"]
                sums["cfun_hwc_occurrences"] += cfun["occurrences_hwc"]
                sums["cfun_tokens"] += cfun["tokens_total"]
                sums["cfun_agc_tokens"] += cfun["tokens_agc"]
                sums["combined_occurrences"] += combined["occurrences_total"]
                sums["combined_agc_occurrences"] += combined["occurrences_agc"]
                sums["combined_hwc_occurrences"] += combined["occurrences_hwc"]
                sums["combined_tokens"] += combined["tokens_total"]
                sums["combined_agc_tokens"] += combined["tokens_agc"]
                sums["combined_hwc_tokens"] += combined["tokens_hwc"]

        if rows != expected_rows:
            raise ValueError(f"Output row count {rows} != expected {expected_rows}")
        os.replace(out_temp_name, output_file)
        os.replace(selected_temp_name, selected_file)
    except Exception:
        for temp_name in (out_temp_name, selected_temp_name):
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
        raise

    support_rows: list[dict[str, Any]] = []
    groups = sorted(group for group in dataset_file_counts if group != "all") + ["all"]
    for group in groups:
        for threshold in SUPPORT_THRESHOLDS:
            denominator = dataset_eligible_counts[group]
            selected = support_selected[(group, threshold)]
            support_rows.append(
                {
                    "dataset_source": group,
                    "threshold": threshold,
                    "operator": ">",
                    "python_file_rows": dataset_file_counts[group],
                    "prepared_file_rows": dataset_prepared_counts[group],
                    "files_with_fun_or_class_method": denominator,
                    "selected_files": selected,
                    "selected_share_of_eligible_files": selected / denominator if denominator else "",
                    "selected_share_of_python_files": selected / dataset_file_counts[group] if dataset_file_counts[group] else "",
                    "ties_at_threshold": support_ties[(group, threshold)],
                }
            )

    return {
        "rows": rows,
        "prepared_rows": prepared_rows,
        "not_prepared_rows": not_prepared_rows,
        "eligible_rows": eligible_rows,
        "selected_rows": selected_rows,
        "exact_primary_ties": exact_primary_ties,
        "mapping_warning_rows": mapping_warning_rows,
        "fun_selected_rows": fun_selected_rows,
        "cfun_selected_rows": cfun_selected_rows,
        "source_primary_union_rows": source_primary_union_rows,
        "source_primary_intersection_rows": source_primary_intersection_rows,
        "source_primary_union_not_combined_rows": source_primary_union_rows - selected_rows,
        "combined_selected_without_source_primary": combined_selected_without_source_primary,
        "status_counts": dict(sorted(status_counts.items())),
        "presence_pattern_counts": dict(sorted(pattern_counts.items())),
        "dataset_file_counts": dict(sorted(dataset_file_counts.items())),
        "dataset_eligible_counts": dict(sorted(dataset_eligible_counts.items())),
        "support_rows": support_rows,
        "sums": dict(sums),
    }


def build_checks(diag: dict[str, Any], upstream_checks: list[dict[str, Any]], strict_expected_counts: bool) -> list[dict[str, Any]]:
    checks = list(upstream_checks)
    sums = diag["sums"]
    expected_pairs = [
        ("file_rows", diag["rows"], EXPECTED_FILE_ROWS),
        ("prepared_rows", diag["prepared_rows"], EXPECTED_PREPARED_FILES),
        ("not_prepared_rows", diag["not_prepared_rows"], EXPECTED_NOT_PREPARED_FILES),
        ("a04_fun_selected_primary_reproduced", diag["fun_selected_rows"], EXPECTED_A04_SELECTED_PRIMARY),
        ("a07_class_method_selected_primary_reproduced", diag["cfun_selected_rows"], EXPECTED_A07_SELECTED_PRIMARY),
        ("fun_occurrence_conservation", sums["fun_occurrences"], EXPECTED_A04_OCCURRENCES),
        ("fun_agc_occurrence_conservation", sums["fun_agc_occurrences"], EXPECTED_A04_AGC_OCCURRENCES),
        ("fun_hwc_occurrence_conservation", sums["fun_hwc_occurrences"], EXPECTED_A04_HWC_OCCURRENCES),
        ("fun_token_conservation", sums["fun_tokens"], EXPECTED_A04_TOTAL_SPACE_TOKENS),
        ("fun_agc_token_conservation", sums["fun_agc_tokens"], EXPECTED_A04_AGC_SPACE_TOKENS),
        ("class_method_occurrence_conservation", sums["cfun_occurrences"], EXPECTED_A07_OCCURRENCES),
        ("class_method_agc_occurrence_conservation", sums["cfun_agc_occurrences"], EXPECTED_A07_AGC_OCCURRENCES),
        ("class_method_hwc_occurrence_conservation", sums["cfun_hwc_occurrences"], EXPECTED_A07_HWC_OCCURRENCES),
        ("class_method_token_conservation", sums["cfun_tokens"], EXPECTED_A07_TOTAL_SPACE_TOKENS),
        ("class_method_agc_token_conservation", sums["cfun_agc_tokens"], EXPECTED_A07_AGC_SPACE_TOKENS),
        ("combined_occurrence_conservation", sums["combined_occurrences"], EXPECTED_COMBINED_OCCURRENCES),
        ("combined_agc_occurrence_conservation", sums["combined_agc_occurrences"], EXPECTED_COMBINED_AGC_OCCURRENCES),
        ("combined_hwc_occurrence_conservation", sums["combined_hwc_occurrences"], EXPECTED_COMBINED_HWC_OCCURRENCES),
        ("combined_token_conservation", sums["combined_tokens"], EXPECTED_COMBINED_TOTAL_SPACE_TOKENS),
        ("combined_agc_token_conservation", sums["combined_agc_tokens"], EXPECTED_COMBINED_AGC_SPACE_TOKENS),
        ("combined_hwc_token_conservation", sums["combined_hwc_tokens"], EXPECTED_COMBINED_HWC_SPACE_TOKENS),
    ]
    severity = "hard" if strict_expected_counts else "informational"
    for name, observed, expected in expected_pairs:
        add_check(checks, name, observed == expected, observed, expected, "Frozen accounting check.", severity=severity)

    add_check(
        checks,
        "combined_status_partition",
        sum(diag["status_counts"].values()) == diag["rows"],
        sum(diag["status_counts"].values()),
        diag["rows"],
        "Combined status must partition all historical file rows.",
    )
    add_check(
        checks,
        "combined_presence_partition",
        sum(diag["presence_pattern_counts"].values()) == diag["rows"],
        sum(diag["presence_pattern_counts"].values()),
        diag["rows"],
        "Procedure presence pattern must partition all historical file rows.",
    )
    add_check(
        checks,
        "eligible_rows_equal_scored_status",
        diag["eligible_rows"] == int(diag["status_counts"].get("scored", 0)),
        diag["eligible_rows"],
        diag["status_counts"].get("scored", 0),
        "Only scored combined rows are eligible for the primary threshold.",
    )
    add_check(
        checks,
        "selected_not_above_eligible",
        diag["selected_rows"] <= diag["eligible_rows"],
        diag["selected_rows"],
        f"<= {diag['eligible_rows']}",
        "Primary selected files must be a subset of eligible combined files.",
    )
    add_check(
        checks,
        "combined_selected_subset_of_source_primary_union",
        diag["combined_selected_without_source_primary"] == 0,
        diag["combined_selected_without_source_primary"],
        0,
        "A positive weighted average above 0.50 requires at least one component share above 0.50.",
    )
    add_check(
        checks,
        "combined_selected_not_above_source_primary_union",
        diag["selected_rows"] <= diag["source_primary_union_rows"],
        diag["selected_rows"],
        f"<= {diag['source_primary_union_rows']}",
        "Combined primary selection must not exceed the union of category-level primary selections.",
    )
    return checks


def run_self_test() -> None:
    def category(tokens_total: int, tokens_agc: int, occurrences_total: int, occurrences_agc: int, status: str = "scored") -> dict[str, Any]:
        if status != "scored":
            return {
                "status": status,
                "present": False,
                "occurrences_total": 0,
                "occurrences_agc": 0,
                "occurrences_hwc": 0,
                "tokens_total": 0,
                "tokens_agc": 0,
                "tokens_hwc": 0,
                "count_share": None,
                "token_share": None,
                "human_score": None,
                "agc_score": None,
                "warning_occurrences": 0,
                "warning_present": 0,
                "primary_flag": None,
            }
        token_share = tokens_agc / tokens_total
        count_share = occurrences_agc / occurrences_total
        human_score = 0.6 - token_share
        return {
            "status": "scored",
            "present": True,
            "occurrences_total": occurrences_total,
            "occurrences_agc": occurrences_agc,
            "occurrences_hwc": occurrences_total - occurrences_agc,
            "tokens_total": tokens_total,
            "tokens_agc": tokens_agc,
            "tokens_hwc": tokens_total - tokens_agc,
            "count_share": count_share,
            "token_share": token_share,
            "human_score": human_score,
            "agc_score": -human_score,
            "warning_occurrences": 0,
            "warning_present": 0,
            "primary_flag": 1 if token_share > PRIMARY_THRESHOLD else 0,
        }

    fun = category(100, 80, 4, 3)
    cfun = category(300, 30, 6, 2)
    combined = combine_categories(fun, cfun, "prepared", "self-test both")
    assert math.isclose(float(combined["token_share"]), 110 / 400, abs_tol=1e-15)
    assert combined["primary_flag"] == 0
    assert combined["pattern"] == "fun_and_class_method"

    fun_only = combine_categories(fun, category(0, 0, 0, 0, "no_ml_cfun"), "prepared", "self-test fun-only")
    assert math.isclose(float(fun_only["token_share"]), 0.8, abs_tol=1e-15)
    assert fun_only["primary_flag"] == 1

    cfun_only = combine_categories(category(0, 0, 0, 0, "no_ml_fun"), cfun, "prepared", "self-test class-method-only")
    assert math.isclose(float(cfun_only["token_share"]), 0.1, abs_tol=1e-15)
    assert cfun_only["primary_flag"] == 0

    neither = combine_categories(category(0, 0, 0, 0, "no_ml_fun"), category(0, 0, 0, 0, "no_ml_cfun"), "prepared", "self-test neither")
    assert neither["status"] == "no_ml_fun_cfun"
    assert neither["token_share"] is None
    assert neither["primary_flag"] is None

    excluded = combine_categories(category(0, 0, 0, 0, "file_not_prepared"), category(0, 0, 0, 0, "file_not_prepared"), "excluded", "self-test excluded")
    assert excluded["status"] == "file_not_prepared"
    assert excluded["token_share"] is None

    tie_fun = category(100, 50, 2, 1)
    tie = combine_categories(tie_fun, category(0, 0, 0, 0, "no_ml_cfun"), "prepared", "self-test tie")
    assert math.isclose(float(tie["token_share"]), 0.5, abs_tol=1e-15)
    assert tie["primary_flag"] == 0

    print("SELF-TEST PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a04-file", type=Path)
    parser.add_argument("--a04-summary", type=Path)
    parser.add_argument("--a07-file", type=Path)
    parser.add_argument("--a07-summary", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-file-rows", type=int, default=EXPECTED_FILE_ROWS)
    parser.add_argument("--strict-expected-counts", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return 0

    required = [args.a04_file, args.a04_summary, args.a07_file, args.a07_summary, args.output_dir]
    if any(value is None for value in required):
        raise SystemExit("ERROR: --a04-file, --a04-summary, --a07-file, --a07-summary, and --output-dir are required")

    started_at = utc_now()
    a04_summary = load_json(args.a04_summary)
    a07_summary = load_json(args.a07_summary)
    upstream_checks: list[dict[str, Any]] = []
    validate_upstream_summaries(a04_summary, a07_summary, upstream_checks)

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "python_ml_fun_cfun_file_scores.csv"
    selected_file = output_dir / "python_ml_fun_cfun_selected_files_primary.csv"
    support_file = output_dir / "python_ml_fun_cfun_threshold_support.csv"
    checks_file = output_dir / "python_ml_fun_cfun_aggregation_checks.csv"
    summary_file = output_dir / "summary.json"
    metadata_file = output_dir / "metadata.json"

    diag = aggregate_files(args.a04_file, args.a07_file, output_file, selected_file, args.expected_file_rows)
    checks = build_checks(diag, upstream_checks, args.strict_expected_counts)
    atomic_write_csv(support_file, diag["support_rows"], SUPPORT_COLUMNS)
    atomic_write_csv(checks_file, checks, CHECK_COLUMNS)

    hard_failures = [row for row in checks if row["severity"] == "hard" and row["passed"] != 1]
    status = "FAIL" if hard_failures else ("PASS_WITH_WARNINGS" if diag["mapping_warning_rows"] > 0 else "PASS")

    summary = {
        "run": SCRIPT_VERSION,
        "status": status,
        "failed_hard_checks": len(hard_failures),
        "primary_file_rule": {
            "metric": "file_ml_fun_cfun_agc_share_space_by_token_weighted",
            "operator": ">",
            "threshold": PRIMARY_THRESHOLD,
            "weight": "procedure body literal-space token count",
            "no_procedure_policy": "blank/unclassified; never imputed as HWC",
        },
        "methodology": {
            "fun_source": "A04 primary regular-function file ML aggregation",
            "class_method_source": "A07 primary class-method file ML aggregation",
            "combined_numerator": "FUN AGC body tokens + class-method AGC body tokens",
            "combined_denominator": "FUN body tokens + class-method body tokens",
            "cross_category_sha_policy": "semantic occurrences are retained; no cross-category SHA deduplication",
            "quality_outcomes_consumed": False,
            "sonarqube_consumed": False,
            "ml_inference_rerun": False,
        },
        "files": {
            "file_rows": diag["rows"],
            "prepared_files": diag["prepared_rows"],
            "not_prepared_files": diag["not_prepared_rows"],
            "eligible_combined_files": diag["eligible_rows"],
            "selected_primary_files": diag["selected_rows"],
            "exact_primary_ties": diag["exact_primary_ties"],
            "mapping_warning_files": diag["mapping_warning_rows"],
            "source_primary_union_files": diag["source_primary_union_rows"],
            "source_primary_intersection_files": diag["source_primary_intersection_rows"],
            "source_primary_union_not_combined_files": diag["source_primary_union_not_combined_rows"],
            "combined_selected_without_source_primary": diag["combined_selected_without_source_primary"],
            "status_counts": diag["status_counts"],
            "presence_pattern_counts": diag["presence_pattern_counts"],
            "dataset_file_counts": diag["dataset_file_counts"],
            "dataset_eligible_counts": diag["dataset_eligible_counts"],
        },
        "accounting": diag["sums"],
        "outputs": {
            "file_scores": str(output_file),
            "selected_primary_files": str(selected_file),
            "threshold_support": str(support_file),
            "checks": str(checks_file),
        },
        "support_thresholds": list(SUPPORT_THRESHOLDS),
        "created_at_utc": utc_now(),
        "started_at_utc": started_at,
    }

    metadata = {
        "script_version": SCRIPT_VERSION,
        "created_at_utc": utc_now(),
        "inputs": {
            "a04_file": str(args.a04_file),
            "a04_file_sha256": file_sha256(args.a04_file),
            "a04_summary": str(args.a04_summary),
            "a04_summary_sha256": file_sha256(args.a04_summary),
            "a07_file": str(args.a07_file),
            "a07_file_sha256": file_sha256(args.a07_file),
            "a07_summary": str(args.a07_summary),
            "a07_summary_sha256": file_sha256(args.a07_summary),
        },
        "primary_metric": "file_ml_fun_cfun_agc_share_space_by_token_weighted",
        "primary_threshold": PRIMARY_THRESHOLD,
        "primary_operator": ">",
        "file_identity": " + ".join(IDENTITY_COLUMNS),
        "threshold_selection_note": "The frozen ML majority threshold is transferred without reading SonarQube or any quality outcome.",
        "strict_expected_counts": bool(args.strict_expected_counts),
    }

    atomic_write_json(summary_file, summary)
    atomic_write_json(metadata_file, metadata)

    print("=" * 78)
    print(f"{SCRIPT_VERSION} ML FUN + class-method aggregation summary")
    print(f"Status:                              {status}")
    print(f"Historical Python files:             {diag['rows']}")
    print(f"Prepared / not prepared:             {diag['prepared_rows']} / {diag['not_prepared_rows']}")
    print(f"Eligible combined files:             {diag['eligible_rows']}")
    print(f"Primary selected files (> 0.50):     {diag['selected_rows']}")
    print(f"Exact 0.50 ties:                     {diag['exact_primary_ties']}")
    print(f"Source primary union/intersection:   {diag['source_primary_union_rows']} / {diag['source_primary_intersection_rows']}")
    print(f"Source union not combined-selected:  {diag['source_primary_union_not_combined_rows']}")
    print(f"Presence patterns:                   {diag['presence_pattern_counts']}")
    print(f"Combined occurrences:                {diag['sums']['combined_occurrences']}")
    print(f"Combined AGC/HWC occurrences:        {diag['sums']['combined_agc_occurrences']} / {diag['sums']['combined_hwc_occurrences']}")
    print(f"Combined body tokens:                {diag['sums']['combined_tokens']}")
    print(f"Combined AGC body tokens:            {diag['sums']['combined_agc_tokens']}")
    print(f"Mapping-warning file rows:           {diag['mapping_warning_rows']}")
    print(f"Failed hard checks:                  {len(hard_failures)}")
    print(f"File scores:                         {output_file}")
    print(f"Selected primary files:              {selected_file}")
    print(f"Threshold support:                   {support_file}")
    print(f"Checks:                              {checks_file}")
    print("=" * 78)

    return 2 if hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
