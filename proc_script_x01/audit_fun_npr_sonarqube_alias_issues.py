#!/usr/bin/env python3
"""
Audit whether SonarQube issue rows reported through filesystem-alias paths are
already represented on the canonical A12-backed paths resolved by D02-a.

This audit is a read-only gate before D03. It does not run SonarScanner, call a
SonarQube API, inspect Git, apply NPR thresholds, or estimate causal effects.

The downstream quality analysis uses issue stock dimensions such as issue type,
severity, and software-quality impacts. Therefore this program compares alias
and canonical issue multisets using an analysis-equivalence signature that
preserves all fields needed by D03 burden outcomes while intentionally ignoring
path-specific issue IDs and component names.

Inputs
------
1. B05 raw Python SonarQube issue rows.
2. D02-a scope-detail rows mapping every filesystem alias to a canonical A12
   path with confirmed content SHA256 equality.
3. D02-a QC and summary files.

Outputs
-------
- One comparison row per D02-a filesystem-alias mapping.
- Signature-level differences for any non-identical issue multisets.
- Repository-level summaries.
- A frozen alias-handling policy for D03.
- QC checks, summary, and metadata.

The expected safe outcome is that every alias-side issue is already represented
on the canonical path. In that case D02's existing policy of excluding alias
paths while retaining canonical A12 files is confirmed and no D02 rewrite is
needed before D03.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

SCRIPT_VERSION = "run-x-d02-b-v1"

EXPECTED_ALIAS_ROWS_DEFAULT = 124
EXPECTED_ALIAS_ISSUES_DEFAULT = 774
EXPECTED_AFFECTED_SNAPSHOTS_DEFAULT = 21
EXPECTED_AFFECTED_REPOSITORIES_DEFAULT = 2

SCOPE_DETAIL_REQUIRED = {
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "component_path",
    "sonar_issue_total",
    "resolved_git_path",
    "resolved_path_in_a12",
    "content_sha256_matches_a12",
    "scope_cause_class",
    "scope_cause_strength",
}

B05_REQUIRED = {
    "snapshot_key",
    "dataset_source",
    "repo_name",
    "commit_sha",
    "issue_key",
    "rule",
    "type",
    "severity",
    "status",
    "resolution",
    "component_path",
    "message",
    "line",
    "clean_code_attribute",
    "impacts_json",
}

ANALYSIS_SIGNATURE_FIELDS = (
    "rule",
    "type",
    "severity",
    "line",
    "message",
    "impacts_json_normalized",
)

STRICT_SIGNATURE_FIELDS = ANALYSIS_SIGNATURE_FIELDS + (
    "status",
    "resolution",
    "clean_code_attribute",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b05-raw-issues-file", type=Path)
    parser.add_argument("--scope-detail-file", type=Path)
    parser.add_argument("--d02-a-checks-file", type=Path)
    parser.add_argument("--d02-a-summary-file", type=Path)
    parser.add_argument("--comparison-output", type=Path)
    parser.add_argument("--signature-differences-output", type=Path)
    parser.add_argument("--repo-summary-output", type=Path)
    parser.add_argument("--handling-spec-output", type=Path)
    parser.add_argument("--checks-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--metadata-output", type=Path)
    parser.add_argument("--csv-chunksize", type=int, default=100_000)
    parser.add_argument(
        "--expected-alias-rows", type=int, default=EXPECTED_ALIAS_ROWS_DEFAULT
    )
    parser.add_argument(
        "--expected-alias-issues", type=int, default=EXPECTED_ALIAS_ISSUES_DEFAULT
    )
    parser.add_argument(
        "--expected-affected-snapshots",
        type=int,
        default=EXPECTED_AFFECTED_SNAPSHOTS_DEFAULT,
    )
    parser.add_argument(
        "--expected-affected-repositories",
        type=int,
        default=EXPECTED_AFFECTED_REPOSITORIES_DEFAULT,
    )
    parser.add_argument("--strict-expected-counts", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def require_file(path: Path | None, label: str) -> Path:
    if path is None or not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return path


def require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(tmp, index=False, quoting=csv.QUOTE_MINIMAL)
    os.replace(tmp, path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "no", "n", "", "nan", "none"}:
        return False
    raise ValueError(f"Cannot parse boolean value: {value!r}")


def normalize_impacts_json(value: str) -> str:
    """Canonicalize SonarQube impacts JSON while preserving semantic content."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return text

    if isinstance(obj, list):
        normalized_items = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in obj]
        normalized_items.sort()
        return "[" + ",".join(normalized_items) + "]"
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def normalize_line(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return text


def make_analysis_signature(row: dict[str, str]) -> tuple[str, ...]:
    return (
        row.get("rule", ""),
        row.get("type", ""),
        row.get("severity", ""),
        normalize_line(row.get("line", "")),
        row.get("message", ""),
        normalize_impacts_json(row.get("impacts_json", "")),
    )


def make_strict_signature(row: dict[str, str]) -> tuple[str, ...]:
    return make_analysis_signature(row) + (
        row.get("status", ""),
        row.get("resolution", ""),
        row.get("clean_code_attribute", ""),
    )


def multiset_overlap(left: Counter[tuple[str, ...]], right: Counter[tuple[str, ...]]) -> int:
    return sum(min(count, right.get(signature, 0)) for signature, count in left.items())


def classify_pair(
    alias_analysis: Counter[tuple[str, ...]],
    canonical_analysis: Counter[tuple[str, ...]],
    alias_strict: Counter[tuple[str, ...]],
    canonical_strict: Counter[tuple[str, ...]],
) -> dict[str, Any]:
    alias_total = sum(alias_analysis.values())
    canonical_total = sum(canonical_analysis.values())
    analysis_overlap = multiset_overlap(alias_analysis, canonical_analysis)
    strict_overlap = multiset_overlap(alias_strict, canonical_strict)
    unmatched_alias_analysis = alias_total - analysis_overlap
    unmatched_canonical_analysis = canonical_total - analysis_overlap
    unmatched_alias_strict = alias_total - strict_overlap

    if alias_total == 0:
        classification = "alias_issue_rows_missing_from_b05"
        safe_to_exclude_alias = False
        recommended_action = "stop_and_review_missing_alias_rows"
    elif unmatched_alias_analysis == 0:
        safe_to_exclude_alias = True
        recommended_action = "exclude_alias_keep_canonical"
        if alias_analysis == canonical_analysis and alias_strict == canonical_strict:
            classification = "exact_multiset_duplicate"
        elif alias_analysis == canonical_analysis:
            classification = "analysis_equivalent_metadata_difference"
        elif unmatched_alias_strict == 0:
            classification = "alias_fully_duplicated_by_canonical"
        else:
            classification = "alias_analysis_fully_duplicated_metadata_differs"
    elif canonical_total == 0:
        classification = "alias_only_remap_required"
        safe_to_exclude_alias = False
        recommended_action = "remap_alias_issues_to_canonical_before_d03"
    elif analysis_overlap == 0:
        classification = "disjoint_alias_canonical_issue_sets"
        safe_to_exclude_alias = False
        recommended_action = "review_then_union_or_remap_before_d03"
    else:
        classification = "partial_overlap_requires_dedup_and_remap"
        safe_to_exclude_alias = False
        recommended_action = "deduplicate_overlap_and_remap_alias_only_issues_before_d03"

    return {
        "alias_issue_count_b05": alias_total,
        "canonical_issue_count_b05": canonical_total,
        "analysis_signature_overlap_count": analysis_overlap,
        "strict_signature_overlap_count": strict_overlap,
        "unmatched_alias_analysis_issue_count": unmatched_alias_analysis,
        "unmatched_canonical_analysis_issue_count": unmatched_canonical_analysis,
        "unmatched_alias_strict_issue_count": unmatched_alias_strict,
        "alias_analysis_coverage_ratio": (analysis_overlap / alias_total) if alias_total else 0.0,
        "alias_strict_coverage_ratio": (strict_overlap / alias_total) if alias_total else 0.0,
        "alias_issue_relation_class": classification,
        "safe_to_exclude_alias_for_d03": int(safe_to_exclude_alias),
        "recommended_action": recommended_action,
    }


def check_row(name: str, observed: Any, expected: Any, passed: bool, detail: str = "") -> dict[str, Any]:
    return {
        "check": name,
        "observed": observed,
        "expected": expected,
        "status": "pass" if passed else "fail",
        "detail": detail,
    }


def validate_d02_a_inputs(checks_path: Path, summary_path: Path) -> dict[str, Any]:
    checks = pd.read_csv(checks_path, dtype=str, keep_default_na=False)
    summary = pd.read_csv(summary_path, dtype=str, keep_default_na=False)
    require_columns(checks, {"check", "status"}, "D02-a checks")
    require_columns(summary, {"metric", "value"}, "D02-a summary")

    failed_checks = int((checks["status"].str.lower() != "pass").sum())
    summary_map = dict(zip(summary["metric"], summary["value"]))
    status = summary_map.get("status", "")
    hard_failures = int(summary_map.get("hard_qc_failures", "-1"))
    if failed_checks != 0:
        raise RuntimeError(f"D02-a checks contain {failed_checks} non-pass rows")
    if status != "PASS_CONFIRMED_FILESYSTEM_ALIAS_SCOPE":
        raise RuntimeError(f"Unexpected D02-a status: {status}")
    if hard_failures != 0:
        raise RuntimeError(f"D02-a hard_qc_failures is {hard_failures}, expected 0")
    return {
        "d02_a_status": status,
        "d02_a_failed_checks": failed_checks,
        "d02_a_hard_qc_failures": hard_failures,
    }


def read_relevant_b05_issue_counters(
    b05_path: Path,
    wanted_pairs: set[tuple[str, str]],
    chunksize: int,
) -> tuple[
    dict[tuple[str, str], Counter[tuple[str, ...]]],
    dict[tuple[str, str], Counter[tuple[str, ...]]],
    dict[tuple[str, str], int],
]:
    analysis_counters: dict[tuple[str, str], Counter[tuple[str, ...]]] = defaultdict(Counter)
    strict_counters: dict[tuple[str, str], Counter[tuple[str, ...]]] = defaultdict(Counter)
    raw_counts: dict[tuple[str, str], int] = defaultdict(int)

    usecols = sorted(B05_REQUIRED)
    for chunk in pd.read_csv(
        b05_path,
        compression="infer",
        dtype=str,
        keep_default_na=False,
        usecols=usecols,
        chunksize=chunksize,
    ):
        require_columns(chunk, B05_REQUIRED, "B05 raw issues")
        pair_mask = [
            pair in wanted_pairs
            for pair in zip(chunk["snapshot_key"].astype(str), chunk["component_path"].astype(str))
        ]
        relevant = chunk.loc[pair_mask]
        if relevant.empty:
            continue
        for record in relevant.to_dict(orient="records"):
            pair = (record["snapshot_key"], record["component_path"])
            analysis_counters[pair][make_analysis_signature(record)] += 1
            strict_counters[pair][make_strict_signature(record)] += 1
            raw_counts[pair] += 1

    return analysis_counters, strict_counters, raw_counts


def signature_to_columns(signature: tuple[str, ...], strict: bool = False) -> dict[str, str]:
    names = STRICT_SIGNATURE_FIELDS if strict else ANALYSIS_SIGNATURE_FIELDS
    return dict(zip(names, signature))


def build_signature_difference_rows(
    scope_row: pd.Series,
    alias_analysis: Counter[tuple[str, ...]],
    canonical_analysis: Counter[tuple[str, ...]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    all_signatures = sorted(set(alias_analysis) | set(canonical_analysis))
    for signature in all_signatures:
        alias_count = alias_analysis.get(signature, 0)
        canonical_count = canonical_analysis.get(signature, 0)
        if alias_count == canonical_count:
            continue
        rows.append(
            {
                "snapshot_key": scope_row["snapshot_key"],
                "dataset_source": scope_row["dataset_source"],
                "repo_name": scope_row["repo_name"],
                "commit_sha": scope_row["commit_sha"],
                "alias_component_path": scope_row["component_path"],
                "canonical_component_path": scope_row["resolved_git_path"],
                "alias_signature_count": alias_count,
                "canonical_signature_count": canonical_count,
                "count_difference_alias_minus_canonical": alias_count - canonical_count,
                **signature_to_columns(signature),
            }
        )
    return rows


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    b05_path = require_file(args.b05_raw_issues_file, "B05 raw issues")
    scope_detail_path = require_file(args.scope_detail_file, "D02-a scope detail")
    checks_path = require_file(args.d02_a_checks_file, "D02-a checks")
    summary_path = require_file(args.d02_a_summary_file, "D02-a summary")

    if args.csv_chunksize <= 0:
        raise ValueError("--csv-chunksize must be positive")

    provenance = validate_d02_a_inputs(checks_path, summary_path)

    scope = pd.read_csv(scope_detail_path, dtype=str, keep_default_na=False)
    require_columns(scope, SCOPE_DETAIL_REQUIRED, "D02-a scope detail")
    scope["sonar_issue_total_int"] = pd.to_numeric(scope["sonar_issue_total"], errors="raise").astype(int)

    alias_rows = len(scope)
    alias_issue_stock = int(scope["sonar_issue_total_int"].sum())
    affected_snapshots = int(scope["snapshot_key"].nunique())
    affected_repositories = int(scope[["dataset_source", "repo_name"]].drop_duplicates().shape[0])
    duplicate_alias_keys = int(scope.duplicated(["snapshot_key", "component_path"]).sum())

    confirmed_scope_rows = int(
        (
            (scope["scope_cause_strength"] == "confirmed_scope_alias")
            & scope["resolved_path_in_a12"].map(as_bool)
            & scope["content_sha256_matches_a12"].map(as_bool)
        ).sum()
    )

    if args.strict_expected_counts:
        expected_pairs = [
            ("alias rows", alias_rows, args.expected_alias_rows),
            ("alias issue stock", alias_issue_stock, args.expected_alias_issues),
            ("affected snapshots", affected_snapshots, args.expected_affected_snapshots),
            ("affected repositories", affected_repositories, args.expected_affected_repositories),
        ]
        mismatches = [(label, observed, expected) for label, observed, expected in expected_pairs if observed != expected]
        if mismatches:
            raise RuntimeError(f"Strict expected-count mismatch: {mismatches}")

    wanted_pairs: set[tuple[str, str]] = set()
    for row in scope.itertuples(index=False):
        wanted_pairs.add((row.snapshot_key, row.component_path))
        wanted_pairs.add((row.snapshot_key, row.resolved_git_path))

    analysis_counters, strict_counters, raw_counts = read_relevant_b05_issue_counters(
        b05_path=b05_path,
        wanted_pairs=wanted_pairs,
        chunksize=args.csv_chunksize,
    )

    comparison_rows: list[dict[str, Any]] = []
    difference_rows: list[dict[str, Any]] = []

    for _, row in scope.iterrows():
        alias_pair = (row["snapshot_key"], row["component_path"])
        canonical_pair = (row["snapshot_key"], row["resolved_git_path"])
        relation = classify_pair(
            analysis_counters.get(alias_pair, Counter()),
            analysis_counters.get(canonical_pair, Counter()),
            strict_counters.get(alias_pair, Counter()),
            strict_counters.get(canonical_pair, Counter()),
        )
        comparison_rows.append(
            {
                "snapshot_key": row["snapshot_key"],
                "dataset_source": row["dataset_source"],
                "repo_name": row["repo_name"],
                "commit_sha": row["commit_sha"],
                "alias_component_path": row["component_path"],
                "canonical_component_path": row["resolved_git_path"],
                "d02_alias_issue_total": int(row["sonar_issue_total_int"]),
                "scope_cause_class": row["scope_cause_class"],
                "scope_cause_strength": row["scope_cause_strength"],
                "content_sha256_matches_a12": int(as_bool(row["content_sha256_matches_a12"])),
                **relation,
            }
        )
        difference_rows.extend(
            build_signature_difference_rows(
                scope_row=row,
                alias_analysis=analysis_counters.get(alias_pair, Counter()),
                canonical_analysis=analysis_counters.get(canonical_pair, Counter()),
            )
        )

    comparison = pd.DataFrame(comparison_rows)
    signature_differences = pd.DataFrame(
        difference_rows,
        columns=[
            "snapshot_key",
            "dataset_source",
            "repo_name",
            "commit_sha",
            "alias_component_path",
            "canonical_component_path",
            "alias_signature_count",
            "canonical_signature_count",
            "count_difference_alias_minus_canonical",
            *ANALYSIS_SIGNATURE_FIELDS,
        ],
    )

    alias_b05_count_mismatches = int(
        (comparison["alias_issue_count_b05"] != comparison["d02_alias_issue_total"]).sum()
    )
    safe_rows = int((comparison["safe_to_exclude_alias_for_d03"] == 1).sum())
    unsafe_rows = alias_rows - safe_rows
    unmatched_alias_analysis_issues = int(comparison["unmatched_alias_analysis_issue_count"].sum())
    total_analysis_overlap = int(comparison["analysis_signature_overlap_count"].sum())

    repo_summary = (
        comparison.groupby(["dataset_source", "repo_name"], dropna=False)
        .agg(
            alias_files=("alias_component_path", "size"),
            affected_snapshots=("snapshot_key", "nunique"),
            alias_issue_stock=("alias_issue_count_b05", "sum"),
            canonical_issue_stock_across_pairs=("canonical_issue_count_b05", "sum"),
            analysis_signature_overlap=("analysis_signature_overlap_count", "sum"),
            unmatched_alias_analysis_issues=("unmatched_alias_analysis_issue_count", "sum"),
            safe_alias_rows=("safe_to_exclude_alias_for_d03", "sum"),
        )
        .reset_index()
    )
    class_counts_by_repo = (
        comparison.groupby(["dataset_source", "repo_name"])["alias_issue_relation_class"]
        .apply(lambda series: "|".join(f"{key}:{value}" for key, value in sorted(Counter(series).items())))
        .reset_index(name="relation_class_counts")
    )
    repo_summary = repo_summary.merge(class_counts_by_repo, on=["dataset_source", "repo_name"], how="left")
    repo_summary["all_alias_rows_safe_to_exclude"] = (
        repo_summary["safe_alias_rows"] == repo_summary["alias_files"]
    ).astype(int)

    handling_spec = pd.DataFrame(
        [
            {
                "policy_id": "exclude_filesystem_alias_issues_keep_canonical_a12_path",
                "apply_in_d03": int(unsafe_rows == 0),
                "prespecified_before_d03": 1,
                "alias_rows": alias_rows,
                "alias_issue_stock": alias_issue_stock,
                "analysis_signature_overlap_issue_stock": total_analysis_overlap,
                "unmatched_alias_analysis_issue_stock": unmatched_alias_analysis_issues,
                "policy_condition": "Every alias-side D03-relevant issue signature is present on the canonical A12-backed path with equal or greater multiplicity.",
                "action": "Keep D02 v2 canonical-path burden and exclude filesystem-alias issue rows; do not remap or double-count alias rows." if unsafe_rows == 0 else "Do not start D03; repair D02 by remapping/deduplicating alias issue rows according to D02-b detail outputs.",
            }
        ]
    )

    checks: list[dict[str, Any]] = []
    checks.append(check_row("d02_a_status_confirmed_alias_scope", provenance["d02_a_status"], "PASS_CONFIRMED_FILESYSTEM_ALIAS_SCOPE", provenance["d02_a_status"] == "PASS_CONFIRMED_FILESYSTEM_ALIAS_SCOPE"))
    checks.append(check_row("alias_rows", alias_rows, args.expected_alias_rows if args.strict_expected_counts else ">0", alias_rows == args.expected_alias_rows if args.strict_expected_counts else alias_rows > 0))
    checks.append(check_row("alias_issue_stock", alias_issue_stock, args.expected_alias_issues if args.strict_expected_counts else ">0", alias_issue_stock == args.expected_alias_issues if args.strict_expected_counts else alias_issue_stock > 0))
    checks.append(check_row("affected_snapshots", affected_snapshots, args.expected_affected_snapshots if args.strict_expected_counts else ">0", affected_snapshots == args.expected_affected_snapshots if args.strict_expected_counts else affected_snapshots > 0))
    checks.append(check_row("affected_repositories", affected_repositories, args.expected_affected_repositories if args.strict_expected_counts else ">0", affected_repositories == args.expected_affected_repositories if args.strict_expected_counts else affected_repositories > 0))
    checks.append(check_row("duplicate_alias_snapshot_paths", duplicate_alias_keys, 0, duplicate_alias_keys == 0))
    checks.append(check_row("scope_rows_confirmed_alias_and_content_match", confirmed_scope_rows, alias_rows, confirmed_scope_rows == alias_rows))
    checks.append(check_row("alias_b05_issue_counts_reconcile_d02_a", alias_b05_count_mismatches, 0, alias_b05_count_mismatches == 0))
    checks.append(check_row("all_alias_rows_safe_to_exclude_for_d03", safe_rows, alias_rows, safe_rows == alias_rows, "Safe means every D03-relevant alias issue signature is already represented on the canonical path."))
    checks.append(check_row("unmatched_alias_analysis_issue_stock", unmatched_alias_analysis_issues, 0, unmatched_alias_analysis_issues == 0))
    checks.append(check_row("handling_policy_frozen_before_d03", int(handling_spec.loc[0, "prespecified_before_d03"]), 1, int(handling_spec.loc[0, "prespecified_before_d03"]) == 1))

    hard_failures = sum(row["status"] != "pass" for row in checks)
    status = "PASS_CONFIRMED_ALIAS_ISSUE_DUPLICATION" if hard_failures == 0 else "FAIL_ALIAS_ISSUE_SCOPE_REQUIRES_REPAIR"

    summary_metrics = [
        ("script_version", SCRIPT_VERSION),
        ("status", status),
        ("alias_rows", alias_rows),
        ("alias_issue_stock", alias_issue_stock),
        ("affected_snapshots", affected_snapshots),
        ("affected_repositories", affected_repositories),
        ("safe_alias_rows", safe_rows),
        ("unsafe_alias_rows", unsafe_rows),
        ("analysis_signature_overlap_issue_stock", total_analysis_overlap),
        ("unmatched_alias_analysis_issue_stock", unmatched_alias_analysis_issues),
        ("signature_difference_rows", len(signature_differences)),
        ("hard_qc_failures", hard_failures),
        ("npr_thresholds_applied", 0),
        ("sonarqube_api_called", 0),
        ("sonarscanner_rerun", 0),
        ("git_inspection_performed", 0),
        ("d03_ready", int(hard_failures == 0)),
    ]
    summary = pd.DataFrame(summary_metrics, columns=["metric", "value"])

    atomic_csv(comparison, args.comparison_output)
    atomic_csv(signature_differences, args.signature_differences_output)
    atomic_csv(repo_summary, args.repo_summary_output)
    atomic_csv(handling_spec, args.handling_spec_output)
    atomic_csv(pd.DataFrame(checks), args.checks_output)
    atomic_csv(summary, args.summary_output)

    metadata = {
        "script_version": SCRIPT_VERSION,
        "status": status,
        "inputs": {
            "b05_raw_issues_file": str(b05_path),
            "b05_raw_issues_sha256": sha256_file(b05_path),
            "scope_detail_file": str(scope_detail_path),
            "scope_detail_sha256": sha256_file(scope_detail_path),
            "d02_a_checks_file": str(checks_path),
            "d02_a_checks_sha256": sha256_file(checks_path),
            "d02_a_summary_file": str(summary_path),
            "d02_a_summary_sha256": sha256_file(summary_path),
        },
        "comparison_semantics": {
            "analysis_signature_fields": list(ANALYSIS_SIGNATURE_FIELDS),
            "strict_signature_fields": list(STRICT_SIGNATURE_FIELDS),
            "issue_key_in_signature": False,
            "component_path_in_signature": False,
            "creation_update_dates_in_signature": False,
            "reason": "D03 burden equivalence depends on rule/type/severity/location/message and software-quality impacts, not path-specific Sonar issue IDs.",
        },
        "policy": handling_spec.iloc[0].to_dict(),
        "counts": {str(k): v for k, v in summary_metrics},
        "relation_class_counts": dict(Counter(comparison["alias_issue_relation_class"])),
        "safety": {
            "sonarqube_api_called": False,
            "sonarscanner_rerun": False,
            "git_inspection_performed": False,
            "npr_thresholds_applied": False,
            "causal_results_read": False,
        },
    }
    atomic_json(metadata, args.metadata_output)

    print("=" * 80)
    print("run-x-d02-b FUN-NPR x SonarQube alias-issue duplication audit")
    print(f"Status:                              {status}")
    print(f"Alias mapping rows:                  {alias_rows}")
    print(f"Alias issue stock:                   {alias_issue_stock}")
    print(f"Affected snapshots / repositories:   {affected_snapshots} / {affected_repositories}")
    print(f"Safe alias rows:                     {safe_rows}")
    print(f"Unsafe alias rows:                   {unsafe_rows}")
    print(f"Analysis-signature overlap issues:   {total_analysis_overlap}")
    print(f"Unmatched alias analysis issues:     {unmatched_alias_analysis_issues}")
    print(f"Signature-difference rows:           {len(signature_differences)}")
    print(f"Hard QC failures:                    {hard_failures}")
    print(f"Comparison detail:                   {args.comparison_output}")
    print(f"Repository summary:                  {args.repo_summary_output}")
    print(f"Handling policy:                     {args.handling_spec_output}")
    print("=" * 80)

    if hard_failures:
        raise RuntimeError(
            f"D02-b hard QC failures: {hard_failures}; D03 must not start until alias issue handling is repaired or reviewed."
        )
    return metadata


def run_self_test() -> None:
    # Exact duplicate: same analysis and strict signatures on both paths.
    base = {
        "rule": "python:S1",
        "type": "CODE_SMELL",
        "severity": "MAJOR",
        "line": "10",
        "message": "Example issue",
        "impacts_json": '[{"softwareQuality":"MAINTAINABILITY","severity":"MEDIUM"}]',
        "status": "OPEN",
        "resolution": "",
        "clean_code_attribute": "CLEAR",
    }
    analysis = Counter({make_analysis_signature(base): 2})
    strict = Counter({make_strict_signature(base): 2})
    relation = classify_pair(analysis, analysis.copy(), strict, strict.copy())
    assert relation["alias_issue_relation_class"] == "exact_multiset_duplicate"
    assert relation["safe_to_exclude_alias_for_d03"] == 1
    assert relation["unmatched_alias_analysis_issue_count"] == 0

    # Alias is a strict subset of canonical: all alias issues are duplicated.
    extra = dict(base)
    extra["line"] = "20"
    canonical_analysis = analysis.copy()
    canonical_analysis[make_analysis_signature(extra)] += 1
    canonical_strict = strict.copy()
    canonical_strict[make_strict_signature(extra)] += 1
    relation = classify_pair(analysis, canonical_analysis, strict, canonical_strict)
    assert relation["safe_to_exclude_alias_for_d03"] == 1
    assert relation["alias_issue_relation_class"] == "alias_fully_duplicated_by_canonical"

    # Alias-only issue requires remapping instead of exclusion.
    relation = classify_pair(analysis, Counter(), strict, Counter())
    assert relation["alias_issue_relation_class"] == "alias_only_remap_required"
    assert relation["safe_to_exclude_alias_for_d03"] == 0
    assert relation["unmatched_alias_analysis_issue_count"] == 2

    # Partial overlap requires deduplication plus remapping.
    second = dict(base)
    second["line"] = "11"
    alias_analysis = Counter({make_analysis_signature(base): 1, make_analysis_signature(second): 1})
    alias_strict = Counter({make_strict_signature(base): 1, make_strict_signature(second): 1})
    canonical_analysis = Counter({make_analysis_signature(base): 1})
    canonical_strict = Counter({make_strict_signature(base): 1})
    relation = classify_pair(alias_analysis, canonical_analysis, alias_strict, canonical_strict)
    assert relation["alias_issue_relation_class"] == "partial_overlap_requires_dedup_and_remap"
    assert relation["unmatched_alias_analysis_issue_count"] == 1

    print("audit_fun_npr_sonarqube_alias_issues self-test: PASS")


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return 0

    required_outputs = [
        args.comparison_output,
        args.signature_differences_output,
        args.repo_summary_output,
        args.handling_spec_output,
        args.checks_output,
        args.summary_output,
        args.metadata_output,
    ]
    if any(path is None for path in required_outputs):
        raise ValueError("All output paths are required outside --self-test mode")

    run_pipeline(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
