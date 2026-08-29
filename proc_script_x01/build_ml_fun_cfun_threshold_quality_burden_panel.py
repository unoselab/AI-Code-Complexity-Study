#!/usr/bin/env python3
"""Build run-x-i08-v1 combined-ML threshold x SonarQube quality-burden panel.

I08 consumes the finalized I06 combined regular-function + class-method ML
historical-file measurement, the corrected/finalized I07 threshold grid, the
canonical D02 historical file-level SonarQube issue burden, and the B06
repo-month DiD panel. It materializes a zero-inclusive threshold x sample x
repo-month panel for the downstream combined-ML Borusyak DiD stage.

Scientific contract
-------------------
- Combined metric: file_ml_fun_cfun_agc_share_space_by_token_weighted
- Threshold grid is read from finalized I07; it is not regenerated from outcomes.
- Selection is strict: combined AGC body-token share > threshold.
- Boundary comparisons use exact integer AGC-token and total-token counts, not
  serialized floating-point score text.
- Missing/non-scored combined ML rows remain unclassified and are never selected.
- Samples: full_sample and exclude_scope_mismatch_repos.
- Scope-sensitivity repositories are frozen from D02's detector-universe
  exclusion artifact before any treatment-effect model is fit.
- Repo-month outcomes are raw selected-file issue stocks summed first, then log1p.
- Density is not computed because selected-file SonarQube NCLOC is unavailable.
- This script does not estimate a treatment effect.

Primary output
--------------
quality_ml_fun_cfun_threshold_input_panel.csv.gz

Downstream key
--------------
sample_spec + threshold_spec_id + repo_id + time_index
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

IMPLEMENTATION_VERSION = "v1"
EXPERIMENT_NAME = "run-x-i08-build-ml-fun-cfun-threshold-quality-burden-panel"
EXPECTED_I06_RUN = "run-x-i06-v1"
EXPECTED_I07_RUN = "run-x-i07-v2"
ML_METRIC = "file_ml_fun_cfun_agc_share_space_by_token_weighted"
ML_STATUS = "file_ml_fun_cfun_agc_status"
ML_NUMERATOR = "ml_fun_cfun_agc_space_by_tokens"
ML_DENOMINATOR = "ml_fun_cfun_space_by_tokens_total"
ML_WARNING = "ml_fun_cfun_mapping_warning_present"
PRESENCE_COLUMN = "procedure_presence_pattern"
PRIMARY_THRESHOLD = 0.50
STRICT_OPERATOR = ">"
MAPPING_SPEC = "all_ml_files"
EXPECTED_THRESHOLDS = tuple(round(0.10 + 0.04 * i, 2) for i in range(21))
FILE_KEYS = ("snapshot_id", "relative_path", "file_sha256")
JOIN_SHA_COLUMN = "_file_sha256_join"
JOIN_FILE_KEYS = ("snapshot_id", "relative_path", JOIN_SHA_COLUMN)
REPO_TIME_KEYS = ("repo_id", "time_index")
MISSING_SHA_SENTINEL = "__MISSING_FILE_SHA256__"

B06_KEEP_COLUMNS = [
    "repo_id", "repo_name", "dataset_source", "scope_role", "treatment_group",
    "time", "time_index", "time_yyyymm", "event", "event_index", "event_yyyymm",
    "post_event", "time_to_event", "log_age", "ncloc_py_sonarqube",
    "log_contributors", "log_stars", "log_issues", "latest_commit_effective",
    "snapshot_key", "quality_scope", "quality_count_semantics",
]

BURDEN_SOURCES = {
    "selected_issue_total": ("sonar_issue_total", "issue_total"),
    "selected_issue_code_smell": (
        "sonar_issue_type_code_smell", "sonar_issue_code_smell", "issue_code_smell", "code_smell"
    ),
    "selected_issue_bug": ("sonar_issue_type_bug", "sonar_issue_bug", "issue_bug", "bug"),
    "selected_issue_vulnerability": (
        "sonar_issue_type_vulnerability", "sonar_issue_vulnerability", "issue_vulnerability", "vulnerability"
    ),
    "selected_issue_high_severity": ("sonar_issue_high_severity", "issue_high_severity", "high_severity"),
    "selected_issue_maintainability_impact": (
        "sonar_issue_with_maintainability_impact", "sonar_issue_maintainability_impact",
        "issue_maintainability_impact", "maintainability_impact"
    ),
    "selected_issue_reliability_impact": (
        "sonar_issue_with_reliability_impact", "sonar_issue_reliability_impact",
        "issue_reliability_impact", "reliability_impact"
    ),
    "selected_issue_security_impact": (
        "sonar_issue_with_security_impact", "sonar_issue_security_impact",
        "issue_security_impact", "security_impact"
    ),
}


def abort(message: str) -> None:
    raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_table(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def require_columns(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        abort(f"{label} is missing required columns: {missing}")


def normalize_repo_time_keys(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    out = frame.copy()
    require_columns(out, REPO_TIME_KEYS, label)
    out["repo_id"] = pd.to_numeric(out["repo_id"], errors="raise").astype(int)
    out["time_index"] = pd.to_numeric(out["time_index"], errors="raise").astype(int)
    if out[list(REPO_TIME_KEYS)].isna().any().any():
        abort(f"{label} contains missing repo_id/time_index")
    return out


def normalize_file_keys(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    out = frame.copy()
    require_columns(out, FILE_KEYS, label)
    for column in ("snapshot_id", "relative_path"):
        if out[column].isna().any():
            abort(f"{label} contains missing {column}")
        out[column] = out[column].astype(str)
    sha = out["file_sha256"].astype("string").str.strip()
    sha = sha.mask(sha.isna() | sha.eq(""), pd.NA)
    out["file_sha256"] = sha
    out[JOIN_SHA_COLUMN] = sha.fillna(MISSING_SHA_SENTINEL).astype(str)
    return out


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_i06_summary(path: Path) -> dict:
    summary = read_json(path)
    if str(summary.get("run", "")).strip() != EXPECTED_I06_RUN:
        abort(f"Unexpected I06 run: {summary.get('run')!r}; expected {EXPECTED_I06_RUN}")
    if str(summary.get("status", "")).strip() not in {"PASS", "PASS_WITH_WARNINGS"}:
        abort(f"I06 is not finalized successfully: {summary.get('status')!r}")
    if int(summary.get("failed_hard_checks", -1)) != 0:
        abort("I06 has hard QC failures")
    rule = summary.get("primary_file_rule", {})
    if str(rule.get("metric", "")).strip() != ML_METRIC:
        abort("I06 primary metric mismatch")
    if str(rule.get("operator", "")).strip() != STRICT_OPERATOR:
        abort("I06 primary operator mismatch")
    if not math.isclose(float(rule.get("threshold")), PRIMARY_THRESHOLD, abs_tol=1e-12):
        abort("I06 primary threshold mismatch")
    return summary


def validate_i07_summary(path: Path) -> dict:
    summary = read_json(path)
    if str(summary.get("run", "")).strip() != EXPECTED_I07_RUN:
        abort(f"I08 requires corrected {EXPECTED_I07_RUN}; observed {summary.get('run')!r}")
    if str(summary.get("status", "")).strip() not in {"PASS", "PASS_WITH_WARNINGS"}:
        abort(f"I07 is not finalized successfully: {summary.get('status')!r}")
    if int(summary.get("failed_hard_checks", -1)) != 0:
        abort("I07 has hard QC failures")
    grid = summary.get("threshold_grid", {})
    if int(grid.get("count", -1)) != 21:
        abort("I07 threshold count mismatch")
    return summary


def validate_i07_checks(path: Path) -> None:
    checks = read_table(path)
    require_columns(checks, ["passed"], "I07 checks")
    passed = pd.to_numeric(checks["passed"], errors="coerce")
    if passed.isna().any() or not passed.eq(1).all():
        abort("I07 checks contain a failed/non-numeric row")


def load_i07_thresholds(spec_path: Path, audit_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    spec = read_table(spec_path)
    audit = read_table(audit_path)
    require_columns(
        spec,
        ["threshold_id", "threshold_role", "grid_order", "delta_from_primary", "threshold", "comparison_operator", "metric"],
        "I07 threshold spec",
    )
    require_columns(audit, ["threshold_id", "threshold", "selected_file_rows", "ties_at_threshold"], "I07 threshold audit")
    if len(spec) != 21 or len(audit) != 21:
        abort(f"I07 must contain 21 thresholds; spec={len(spec)}, audit={len(audit)}")
    spec = spec.sort_values("grid_order").reset_index(drop=True)
    observed = [round(float(value), 2) for value in spec["threshold"]]
    if observed != list(EXPECTED_THRESHOLDS):
        abort(f"Unexpected I07 threshold grid: {observed}")
    if not spec["comparison_operator"].astype(str).eq(STRICT_OPERATOR).all():
        abort("I07 threshold spec must use strict >")
    if not spec["metric"].astype(str).eq(ML_METRIC).all():
        abort("I07 threshold metric mismatch")
    primary = spec.loc[np.isclose(pd.to_numeric(spec["threshold"], errors="raise"), PRIMARY_THRESHOLD)]
    if len(primary) != 1 or str(primary.iloc[0]["threshold_role"]) != "primary":
        abort("I07 primary threshold row is malformed")
    merged = spec[["threshold_id", "threshold"]].merge(
        audit[["threshold_id", "threshold", "selected_file_rows", "ties_at_threshold"]],
        on="threshold_id",
        suffixes=("_spec", "_audit"),
        validate="one_to_one",
    )
    if not np.allclose(merged["threshold_spec"], merged["threshold_audit"], atol=1e-12, rtol=0):
        abort("I07 spec/audit threshold mismatch")
    return spec, audit


def audit_missing_sha_identity(i06: pd.DataFrame, unique_d02: pd.DataFrame) -> dict[str, int]:
    i06_missing = i06.loc[i06["file_sha256"].isna(), ["snapshot_id", "relative_path"]].copy()
    d02_missing = unique_d02.loc[unique_d02["file_sha256"].isna(), ["snapshot_id", "relative_path"]].copy()
    if i06_missing.duplicated(["snapshot_id", "relative_path"]).any():
        abort("I06 missing-SHA rows are not unique by snapshot_id + relative_path")
    if d02_missing.duplicated(["snapshot_id", "relative_path"]).any():
        abort("D02 missing-SHA rows are not unique by snapshot_id + relative_path")
    comparison = d02_missing.merge(
        i06_missing, on=["snapshot_id", "relative_path"], how="outer", indicator=True, validate="one_to_one"
    )
    return {
        "i06_missing_sha_files": int(len(i06_missing)),
        "d02_missing_sha_files": int(len(d02_missing)),
        "d02_only_missing_sha_keys": int((comparison["_merge"] == "left_only").sum()),
        "i06_only_missing_sha_keys": int((comparison["_merge"] == "right_only").sum()),
    }


def resolve_burden_columns(d02: pd.DataFrame) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for output_column, candidates in BURDEN_SOURCES.items():
        source = next((candidate for candidate in candidates if candidate in d02.columns), None)
        if source is None:
            abort(f"D02 cannot provide {output_column}; tried {list(candidates)}")
        resolved[output_column] = source
    return resolved


def derive_sample_specs(outside_scope: pd.DataFrame, b06: pd.DataFrame) -> tuple[dict[str, set[int]], pd.DataFrame]:
    require_columns(outside_scope, ["dataset_source", "repo_name", "exclusion_class", "sonar_issue_total"], "D02 outside-scope")
    if outside_scope.empty:
        abort("D02 outside-scope artifact is unexpectedly empty")
    if not outside_scope["exclusion_class"].astype(str).eq("outside_a12_npr_file_universe").all():
        abort("Unexpected D02 outside-scope exclusion class")
    outside_repo_names = sorted(set(outside_scope["repo_name"].astype(str)))
    b06_names = b06[["repo_id", "repo_name", "dataset_source"]].drop_duplicates()
    mapped = b06_names.loc[b06_names["repo_name"].astype(str).isin(outside_repo_names)].copy()
    if set(mapped["repo_name"].astype(str)) != set(outside_repo_names):
        missing = sorted(set(outside_repo_names) - set(mapped["repo_name"].astype(str)))
        abort(f"Outside-scope repositories are absent from B06: {missing}")
    excluded_ids = set(mapped["repo_id"].astype(int))
    full_ids = set(b06["repo_id"].astype(int))
    return {
        "full_sample": full_ids,
        "exclude_scope_mismatch_repos": full_ids - excluded_ids,
    }, mapped.sort_values("repo_id").reset_index(drop=True)


def treatment_counts(panel: pd.DataFrame) -> dict[str, int]:
    treatment = pd.to_numeric(panel["treatment_group"], errors="raise").astype(int)
    event_index = pd.to_numeric(panel["event_index"], errors="raise").astype(int)
    time_index = pd.to_numeric(panel["time_index"], errors="raise").astype(int)
    control = treatment.eq(0)
    treated = treatment.eq(1)
    return {
        "repo_month_rows": int(len(panel)),
        "repositories": int(panel["repo_id"].nunique()),
        "control_repositories": int(panel.loc[control, "repo_id"].nunique()),
        "treatment_repositories": int(panel.loc[treated, "repo_id"].nunique()),
        "control_rows": int(control.sum()),
        "treatment_pre_rows": int((treated & time_index.lt(event_index)).sum()),
        "treatment_post_rows": int((treated & time_index.ge(event_index)).sum()),
        "dynamic_event_0_to_6_rows": int((treated & (time_index - event_index).between(0, 6)).sum()),
    }


def add_log_outcomes(panel: pd.DataFrame) -> None:
    for output_column in BURDEN_SOURCES:
        panel[f"log1p_{output_column}"] = np.log1p(panel[output_column].astype(float))


def ratio_selected(frame: pd.DataFrame, threshold: float) -> pd.Series:
    threshold_percent = int(round(threshold * 100))
    numerator = pd.to_numeric(frame[ML_NUMERATOR], errors="raise").astype("int64")
    denominator = pd.to_numeric(frame[ML_DENOMINATOR], errors="raise").astype("int64")
    return numerator.mul(100).gt(denominator.mul(threshold_percent))


def ratio_ties(frame: pd.DataFrame, threshold: float) -> pd.Series:
    threshold_percent = int(round(threshold * 100))
    numerator = pd.to_numeric(frame[ML_NUMERATOR], errors="raise").astype("int64")
    denominator = pd.to_numeric(frame[ML_DENOMINATOR], errors="raise").astype("int64")
    return numerator.mul(100).eq(denominator.mul(threshold_percent))


def run_self_test() -> None:
    fixture = pd.DataFrame(
        {
            ML_NUMERATOR: [10, 11, 50, 51, 90, 91],
            ML_DENOMINATOR: [100, 100, 100, 100, 100, 100],
        }
    )
    assert ratio_selected(fixture, 0.10).tolist() == [False, True, True, True, True, True]
    assert ratio_ties(fixture, 0.10).tolist() == [True, False, False, False, False, False]
    assert ratio_selected(fixture, 0.50).tolist() == [False, False, False, True, True, True]
    assert ratio_ties(fixture, 0.50).tolist() == [False, False, True, False, False, False]
    assert len(EXPECTED_THRESHOLDS) == 21 and EXPECTED_THRESHOLDS[10] == PRIMARY_THRESHOLD
    print("build_ml_fun_cfun_threshold_quality_burden_panel self-test: PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--i06-file", type=Path)
    parser.add_argument("--i06-summary-file", type=Path)
    parser.add_argument("--i07-threshold-spec-file", type=Path)
    parser.add_argument("--i07-threshold-audit-file", type=Path)
    parser.add_argument("--i07-summary-file", type=Path)
    parser.add_argument("--i07-checks-file", type=Path)
    parser.add_argument("--d02-file", type=Path)
    parser.add_argument("--d02-outside-scope-file", type=Path)
    parser.add_argument("--b06-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-i06-rows", type=int, default=494592)
    parser.add_argument("--expected-d02-rows", type=int, default=510297)
    parser.add_argument("--expected-d02-unique-files", type=int, default=494592)
    parser.add_argument("--expected-b06-rows", type=int, default=1954)
    parser.add_argument("--expected-b06-repositories", type=int, default=167)
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument("--expected-sensitivity-rows", type=int, default=1915)
    parser.add_argument("--expected-sensitivity-repositories", type=int, default=165)
    parser.add_argument("--expected-sensitivity-treatment-repositories", type=int, default=62)
    parser.add_argument("--expected-sensitivity-control-repositories", type=int, default=103)
    parser.add_argument("--expected-scope-excluded-repositories", type=int, default=2)
    parser.add_argument("--expected-eligible-expanded-rows", type=int, default=359466)
    parser.add_argument("--expected-eligible-unique-files", type=int, default=347562)
    parser.add_argument("--expected-primary-selected-expanded-rows", type=int, default=64153)
    parser.add_argument("--expected-primary-selected-unique-files", type=int, default=62319)
    parser.add_argument("--expected-primary-issue-stock", type=float, default=35765.0)
    parser.add_argument("--expected-sensitivity-primary-selected-expanded-rows", type=int, default=63409)
    parser.add_argument("--expected-sensitivity-primary-selected-unique-files", type=int, default=61575)
    parser.add_argument("--expected-sensitivity-primary-issue-stock", type=float, default=34598.0)
    parser.add_argument("--strict-expected-counts", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return

    required = [
        args.i06_file, args.i06_summary_file, args.i07_threshold_spec_file, args.i07_threshold_audit_file,
        args.i07_summary_file, args.i07_checks_file, args.d02_file, args.d02_outside_scope_file,
        args.b06_file, args.output_dir,
    ]
    if any(value is None for value in required):
        parser.error("all production paths are required unless --self-test is used")
    for path in required[:-1]:
        if not path.exists():
            abort(f"Missing required input: {path}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    i06_summary = validate_i06_summary(args.i06_summary_file)
    i07_summary = validate_i07_summary(args.i07_summary_file)
    validate_i07_checks(args.i07_checks_file)
    threshold_spec, i07_audit = load_i07_thresholds(args.i07_threshold_spec_file, args.i07_threshold_audit_file)

    print(f"Reading I06 combined ML file scores: {args.i06_file}")
    i06 = normalize_file_keys(read_table(args.i06_file), "I06")
    print(f"Reading D02 canonical file burden: {args.d02_file}")
    d02 = normalize_file_keys(normalize_repo_time_keys(read_table(args.d02_file), "D02"), "D02")
    print(f"Reading D02 outside-scope artifact: {args.d02_outside_scope_file}")
    outside_scope = read_table(args.d02_outside_scope_file)
    print(f"Reading B06 authoritative panel: {args.b06_file}")
    b06_full = normalize_repo_time_keys(read_table(args.b06_file), "B06")
    require_columns(b06_full, B06_KEEP_COLUMNS, "B06")
    b06 = b06_full[B06_KEEP_COLUMNS].copy()
    del b06_full

    if len(i06) != args.expected_i06_rows:
        abort(f"I06 row mismatch: expected {args.expected_i06_rows}, observed {len(i06)}")
    if len(d02) != args.expected_d02_rows:
        abort(f"D02 row mismatch: expected {args.expected_d02_rows}, observed {len(d02)}")
    if len(b06) != args.expected_b06_rows:
        abort(f"B06 row mismatch: expected {args.expected_b06_rows}, observed {len(b06)}")
    if b06["repo_id"].nunique() != args.expected_b06_repositories:
        abort("B06 repository-count mismatch")
    if b06.duplicated(["repo_id", "time_index"]).any():
        abort("B06 contains duplicate repo-month keys")

    require_columns(
        i06,
        [ML_METRIC, ML_STATUS, ML_NUMERATOR, ML_DENOMINATOR, ML_WARNING, PRESENCE_COLUMN, "dataset_source", "repo_name"],
        "I06",
    )
    i06[ML_METRIC] = pd.to_numeric(i06[ML_METRIC], errors="coerce")
    i06[ML_NUMERATOR] = pd.to_numeric(i06[ML_NUMERATOR], errors="raise").astype("int64")
    i06[ML_DENOMINATOR] = pd.to_numeric(i06[ML_DENOMINATOR], errors="raise").astype("int64")
    if i06.duplicated(list(JOIN_FILE_KEYS)).any():
        abort("I06 contains duplicate historical file keys")
    eligible_i06 = i06[ML_STATUS].astype(str).eq("scored")
    if eligible_i06.ne(i06[ML_METRIC].notna()).any():
        abort("I06 scored status does not match finite combined metric")
    if ((i06.loc[eligible_i06, ML_DENOMINATOR] <= 0) | (i06.loc[eligible_i06, ML_NUMERATOR] < 0) |
        (i06.loc[eligible_i06, ML_NUMERATOR] > i06.loc[eligible_i06, ML_DENOMINATOR])).any():
        abort("I06 combined token numerator/denominator is invalid")
    recomputed_score = i06.loc[eligible_i06, ML_NUMERATOR] / i06.loc[eligible_i06, ML_DENOMINATOR]
    score_mismatches = int((~np.isclose(recomputed_score, i06.loc[eligible_i06, ML_METRIC], atol=1e-15, rtol=1e-12)).sum())
    if score_mismatches:
        abort(f"I06 continuous-score reconstruction mismatches: {score_mismatches}")

    burden_columns = resolve_burden_columns(d02)
    for source in burden_columns.values():
        d02[source] = pd.to_numeric(d02[source], errors="raise")
        if (d02[source] < 0).any():
            abort(f"D02 contains negative burden values in {source}")

    unique_d02 = d02[list(JOIN_FILE_KEYS) + ["file_sha256"]].drop_duplicates(list(JOIN_FILE_KEYS))
    if len(unique_d02) != args.expected_d02_unique_files:
        abort(f"D02 unique historical file mismatch: expected {args.expected_d02_unique_files}, observed {len(unique_d02)}")
    missing_sha = audit_missing_sha_identity(i06, unique_d02)
    if missing_sha["d02_only_missing_sha_keys"] or missing_sha["i06_only_missing_sha_keys"]:
        abort(f"I06/D02 missing-SHA identity mismatch: {missing_sha}")

    universe = unique_d02[list(JOIN_FILE_KEYS)].merge(
        i06[list(JOIN_FILE_KEYS)], on=list(JOIN_FILE_KEYS), how="outer", indicator=True, validate="one_to_one"
    )
    d02_only = int((universe["_merge"] == "left_only").sum())
    i06_only = int((universe["_merge"] == "right_only").sum())
    if d02_only or i06_only:
        abort(f"I06/D02 historical-file universe mismatch: d02_only={d02_only}, i06_only={i06_only}")

    i06_join_columns = [
        *JOIN_FILE_KEYS, ML_METRIC, ML_STATUS, ML_NUMERATOR, ML_DENOMINATOR, ML_WARNING, PRESENCE_COLUMN,
    ]
    base = d02.merge(i06[i06_join_columns], on=list(JOIN_FILE_KEYS), how="left", validate="many_to_one")
    if len(base) != len(d02):
        abort("I06/D02 expanded join changed D02 row count")
    eligible = base[ML_STATUS].astype(str).eq("scored")
    eligible_rows = int(eligible.sum())
    eligible_unique = int(base.loc[eligible, list(JOIN_FILE_KEYS)].drop_duplicates().shape[0])

    sample_repo_ids, scope_repos = derive_sample_specs(outside_scope, b06)
    sample_b06: dict[str, pd.DataFrame] = {}
    for sample_name, repo_ids in sample_repo_ids.items():
        sample_b06[sample_name] = b06.loc[b06["repo_id"].isin(repo_ids)].copy()
    full_counts = treatment_counts(sample_b06["full_sample"])
    sensitivity_counts = treatment_counts(sample_b06["exclude_scope_mismatch_repos"])

    expected_sample = {
        "full_sample": (args.expected_b06_rows, args.expected_b06_repositories, args.expected_treatment_repositories, args.expected_control_repositories),
        "exclude_scope_mismatch_repos": (
            args.expected_sensitivity_rows, args.expected_sensitivity_repositories,
            args.expected_sensitivity_treatment_repositories, args.expected_sensitivity_control_repositories,
        ),
    }
    for sample_name, counts in [("full_sample", full_counts), ("exclude_scope_mismatch_repos", sensitivity_counts)]:
        expected_rows, expected_repos, expected_treat, expected_control = expected_sample[sample_name]
        observed = (counts["repo_month_rows"], counts["repositories"], counts["treatment_repositories"], counts["control_repositories"])
        expected_tuple = (expected_rows, expected_repos, expected_treat, expected_control)
        if args.strict_expected_counts and observed != expected_tuple:
            abort(f"{sample_name} B06 accounting mismatch: observed={observed}, expected={expected_tuple}")

    # Threshold-independent eligible support by repo-month.
    eligible_agg = (
        base.loc[eligible]
        .groupby(["repo_id", "time_index"], as_index=False)
        .agg(
            eligible_ml_file_count=("relative_path", "size"),
            eligible_mapping_warning_file_count=(ML_WARNING, "sum"),
        )
    )

    panel_parts: list[pd.DataFrame] = []
    global_rows: list[dict] = []
    timing_rows: list[dict] = []
    reproduction_rows: list[dict] = []

    i07_audit_by_id = i07_audit.set_index("threshold_id")
    primary_audits: dict[str, dict] = {}

    for spec in threshold_spec.itertuples(index=False):
        threshold = float(spec.threshold)
        selected_mask = eligible & ratio_selected(base, threshold)
        selected = base.loc[selected_mask].copy()

        # Reproduce corrected I07 historical-file support exactly at every threshold.
        selected_unique = int(selected[list(JOIN_FILE_KEYS)].drop_duplicates().shape[0])
        expected_unique = int(i07_audit_by_id.loc[spec.threshold_id, "selected_file_rows"])
        reproduction_rows.append({
            "threshold_spec_id": spec.threshold_id,
            "threshold": threshold,
            "i07_selected_unique_files": expected_unique,
            "i08_selected_unique_files": selected_unique,
            "difference": selected_unique - expected_unique,
            "match": int(selected_unique == expected_unique),
        })

        selected["_selected_file"] = 1
        selected["_selected_issue_file"] = pd.to_numeric(selected[burden_columns["selected_issue_total"]], errors="raise").gt(0).astype(int)
        agg_dict: dict[str, tuple[str, str]] = {
            "selected_file_count": ("_selected_file", "sum"),
            "selected_file_with_any_issue_count": ("_selected_issue_file", "sum"),
            "selected_mapping_warning_file_count": (ML_WARNING, "sum"),
        }
        for output_column, source_column in burden_columns.items():
            agg_dict[output_column] = (source_column, "sum")
        selected_agg = selected.groupby(["repo_id", "time_index"], as_index=False).agg(**agg_dict)

        for sample_name, base_panel in sample_b06.items():
            panel = base_panel.merge(eligible_agg, on=["repo_id", "time_index"], how="left", validate="one_to_one")
            panel = panel.merge(selected_agg, on=["repo_id", "time_index"], how="left", validate="one_to_one")
            for column in [
                "eligible_ml_file_count", "eligible_mapping_warning_file_count", "selected_file_count",
                "selected_file_with_any_issue_count", "selected_mapping_warning_file_count",
            ]:
                panel[column] = panel[column].fillna(0).astype(int)
            for output_column in burden_columns:
                panel[output_column] = panel[output_column].fillna(0.0).astype(float)
            panel["selected_issue_free_file_count"] = panel["selected_file_count"] - panel["selected_file_with_any_issue_count"]
            if (panel["selected_issue_free_file_count"] < 0).any():
                abort("Selected issue-free file count became negative")
            panel["selected_file_share_of_eligible"] = np.where(
                panel["eligible_ml_file_count"].gt(0), panel["selected_file_count"] / panel["eligible_ml_file_count"], 0.0
            )
            panel["has_selected_files"] = panel["selected_file_count"].gt(0).astype(int)
            panel["has_selected_issue_burden"] = panel["selected_issue_total"].gt(0).astype(int)
            add_log_outcomes(panel)
            panel["sample_spec"] = sample_name
            panel["mapping_spec"] = MAPPING_SPEC
            panel["threshold_spec_id"] = spec.threshold_id
            panel["threshold_role"] = spec.threshold_role
            panel["grid_order"] = int(spec.grid_order)
            panel["delta_from_primary"] = float(spec.delta_from_primary)
            panel["threshold"] = threshold
            panel["ml_metric"] = ML_METRIC
            panel["ml_operator"] = STRICT_OPERATOR
            panel["primary_threshold"] = PRIMARY_THRESHOLD
            panel["primary_analysis"] = int(sample_name == "full_sample" and math.isclose(threshold, PRIMARY_THRESHOLD, abs_tol=1e-12))
            panel["quality_scope"] = "canonical_i06_python_files_with_finite_combined_ml"
            panel["quality_count_semantics"] = "unresolved_sonarqube_issue_stock_at_historical_snapshot"
            panel["density_computed"] = 0
            panel_parts.append(panel)

            sample_selected = selected.loc[selected["repo_id"].isin(sample_repo_ids[sample_name])]
            audit = {
                "sample_spec": sample_name,
                "mapping_spec": MAPPING_SPEC,
                "threshold_spec_id": spec.threshold_id,
                "threshold": threshold,
                "threshold_role": spec.threshold_role,
                "repo_month_rows": int(len(panel)),
                "repositories": int(panel["repo_id"].nunique()),
                "eligible_file_rows": int(base.loc[eligible & base["repo_id"].isin(sample_repo_ids[sample_name])].shape[0]),
                "selected_file_rows": int(len(sample_selected)),
                "selected_unique_historical_files": int(sample_selected[list(JOIN_FILE_KEYS)].drop_duplicates().shape[0]),
                "repo_months_with_selected_files": int(panel["has_selected_files"].sum()),
                "repo_months_with_positive_issue_burden": int(panel["has_selected_issue_burden"].sum()),
                "zero_issue_repo_month_share": float(panel["selected_issue_total"].eq(0).mean()),
                "repositories_with_within_quality_variation": int(panel.groupby("repo_id")["log1p_selected_issue_total"].nunique().gt(1).sum()),
            }
            for output_column in burden_columns:
                audit[output_column] = float(panel[output_column].sum())
            global_rows.append(audit)
            if math.isclose(threshold, PRIMARY_THRESHOLD, abs_tol=1e-12):
                primary_audits[sample_name] = audit

            treatment_group = pd.to_numeric(panel["treatment_group"], errors="raise").astype(int)
            event_index = pd.to_numeric(panel["event_index"], errors="raise").astype(int)
            time_index = pd.to_numeric(panel["time_index"], errors="raise").astype(int)
            masks = {
                "control": treatment_group.eq(0),
                "treatment_pre": treatment_group.eq(1) & time_index.lt(event_index),
                "treatment_post": treatment_group.eq(1) & time_index.ge(event_index),
            }
            for timing_group, timing_mask in masks.items():
                part = panel.loc[timing_mask]
                timing_rows.append({
                    "sample_spec": sample_name,
                    "threshold_spec_id": spec.threshold_id,
                    "threshold": threshold,
                    "timing_group": timing_group,
                    "repo_month_rows": int(len(part)),
                    "repositories": int(part["repo_id"].nunique()),
                    "selected_file_rows": int(part["selected_file_count"].sum()),
                    "selected_issue_total": float(part["selected_issue_total"].sum()),
                })

    long_panel = pd.concat(panel_parts, ignore_index=True)
    expected_long_rows = 21 * (args.expected_b06_rows + args.expected_sensitivity_rows)
    duplicate_keys = int(long_panel.duplicated(["sample_spec", "threshold_spec_id", "repo_id", "time_index"]).sum())
    if len(long_panel) != expected_long_rows or duplicate_keys:
        abort(f"I08 long-panel contract failed: rows={len(long_panel)}/{expected_long_rows}, duplicates={duplicate_keys}")

    global_audit = pd.DataFrame(global_rows).sort_values(["sample_spec", "threshold"]).reset_index(drop=True)
    for sample_name in sample_repo_ids:
        sample = global_audit.loc[global_audit["sample_spec"].eq(sample_name)].sort_values("threshold")
        for metric in ["selected_file_rows", *BURDEN_SOURCES.keys()]:
            values = pd.to_numeric(sample[metric], errors="raise").to_numpy(dtype=float)
            if np.any(np.diff(values) > 1e-9):
                abort(f"Threshold monotonicity failed for {sample_name}::{metric}")

    reproduction = pd.DataFrame(reproduction_rows)
    reproduction_failures = int(reproduction["match"].ne(1).sum())
    if reproduction_failures:
        abort(f"I07 unique-file threshold reproduction failed at {reproduction_failures} thresholds")

    full_primary = primary_audits["full_sample"]
    sens_primary = primary_audits["exclude_scope_mismatch_repos"]
    if args.strict_expected_counts:
        expected_primary = (
            args.expected_primary_selected_expanded_rows,
            args.expected_primary_selected_unique_files,
            args.expected_primary_issue_stock,
        )
        observed_primary = (
            int(full_primary["selected_file_rows"]),
            int(full_primary["selected_unique_historical_files"]),
            float(full_primary["selected_issue_total"]),
        )
        if observed_primary != expected_primary:
            abort(f"Full primary accounting mismatch: observed={observed_primary}, expected={expected_primary}")
        expected_sens = (
            args.expected_sensitivity_primary_selected_expanded_rows,
            args.expected_sensitivity_primary_selected_unique_files,
            args.expected_sensitivity_primary_issue_stock,
        )
        observed_sens = (
            int(sens_primary["selected_file_rows"]),
            int(sens_primary["selected_unique_historical_files"]),
            float(sens_primary["selected_issue_total"]),
        )
        if observed_sens != expected_sens:
            abort(f"Sensitivity primary accounting mismatch: observed={observed_sens}, expected={expected_sens}")

    sample_summary_rows = []
    excluded_ids = set(scope_repos["repo_id"].astype(int))
    for sample_name, panel in sample_b06.items():
        counts = treatment_counts(panel)
        counts.update({
            "sample_spec": sample_name,
            "excluded_repository_count": 0 if sample_name == "full_sample" else len(excluded_ids),
            "excluded_repo_ids": "" if sample_name == "full_sample" else "|".join(map(str, sorted(excluded_ids))),
            "excluded_repositories": "" if sample_name == "full_sample" else " | ".join(sorted(scope_repos["repo_name"].astype(str))),
        })
        sample_summary_rows.append(counts)
    sample_summary = pd.DataFrame(sample_summary_rows)

    scope_spec = scope_repos.copy()
    scope_spec.insert(0, "sample_spec", "exclude_scope_mismatch_repos")
    scope_spec["exclude_repository"] = 1
    scope_spec["frozen_before_did"] = 1
    scope_spec["reason"] = "D02 contains issue-bearing Python files outside the frozen historical detector file universe."

    outcome_spec = pd.DataFrame([
        {
            "outcome": f"log1p_{column}",
            "raw_outcome": column,
            "role": "primary_burden" if column == "selected_issue_total" else "burden_robustness",
            "transform": "log1p(repo-month selected-file issue stock)",
            "density_computed": 0,
        }
        for column in BURDEN_SOURCES
    ])

    log_mismatches = 0
    for column in BURDEN_SOURCES:
        observed = pd.to_numeric(long_panel[f"log1p_{column}"], errors="raise").to_numpy(dtype=float)
        expected = np.log1p(pd.to_numeric(long_panel[column], errors="raise").to_numpy(dtype=float))
        log_mismatches += int((~np.isclose(observed, expected, atol=1e-12, rtol=0)).sum())

    qc_rows: list[dict] = []
    def add_qc(name: str, observed, expected, passed: bool, detail: str = "") -> None:
        qc_rows.append({"check_name": name, "severity": "hard", "passed": int(passed), "observed": observed, "expected": expected, "note": detail})

    add_qc("i06_status", i06_summary.get("status"), "PASS|PASS_WITH_WARNINGS", True, "I06 must be finalized successfully.")
    add_qc("i07_status", i07_summary.get("status"), "PASS|PASS_WITH_WARNINGS", True, "Corrected I07-v2 must be finalized successfully.")
    add_qc("threshold_count", len(threshold_spec), 21, len(threshold_spec) == 21)
    add_qc("i06_rows", len(i06), args.expected_i06_rows, len(i06) == args.expected_i06_rows or not args.strict_expected_counts)
    add_qc("d02_rows", len(d02), args.expected_d02_rows, len(d02) == args.expected_d02_rows or not args.strict_expected_counts)
    add_qc("d02_unique_files", len(unique_d02), args.expected_d02_unique_files, len(unique_d02) == args.expected_d02_unique_files or not args.strict_expected_counts)
    add_qc("b06_rows", len(b06), args.expected_b06_rows, len(b06) == args.expected_b06_rows or not args.strict_expected_counts)
    add_qc("eligible_expanded_file_rows", eligible_rows, args.expected_eligible_expanded_rows, eligible_rows == args.expected_eligible_expanded_rows or not args.strict_expected_counts)
    add_qc("eligible_unique_files", eligible_unique, args.expected_eligible_unique_files, eligible_unique == args.expected_eligible_unique_files or not args.strict_expected_counts)
    add_qc("i06_missing_sha_files", missing_sha["i06_missing_sha_files"], missing_sha["d02_missing_sha_files"], missing_sha["i06_missing_sha_files"] == missing_sha["d02_missing_sha_files"])
    add_qc("missing_sha_identity_mismatches", missing_sha["d02_only_missing_sha_keys"] + missing_sha["i06_only_missing_sha_keys"], 0, missing_sha["d02_only_missing_sha_keys"] + missing_sha["i06_only_missing_sha_keys"] == 0)
    add_qc("d02_only_file_keys", d02_only, 0, d02_only == 0)
    add_qc("i06_only_file_keys", i06_only, 0, i06_only == 0)
    add_qc("score_reconstruction_mismatches", score_mismatches, 0, score_mismatches == 0)
    add_qc("scope_sensitivity_repositories_excluded", len(scope_repos), args.expected_scope_excluded_repositories, len(scope_repos) == args.expected_scope_excluded_repositories or not args.strict_expected_counts)
    add_qc("scope_sensitivity_repo_month_rows", sensitivity_counts["repo_month_rows"], args.expected_sensitivity_rows, sensitivity_counts["repo_month_rows"] == args.expected_sensitivity_rows or not args.strict_expected_counts)
    add_qc("long_panel_rows", len(long_panel), expected_long_rows, len(long_panel) == expected_long_rows)
    add_qc("long_panel_duplicate_keys", duplicate_keys, 0, duplicate_keys == 0)
    add_qc("i07_threshold_reproduction_mismatches", reproduction_failures, 0, reproduction_failures == 0)
    add_qc("primary_full_selected_file_rows", int(full_primary["selected_file_rows"]), args.expected_primary_selected_expanded_rows, int(full_primary["selected_file_rows"]) == args.expected_primary_selected_expanded_rows or not args.strict_expected_counts)
    add_qc("primary_full_selected_unique_files", int(full_primary["selected_unique_historical_files"]), args.expected_primary_selected_unique_files, int(full_primary["selected_unique_historical_files"]) == args.expected_primary_selected_unique_files or not args.strict_expected_counts)
    add_qc("primary_full_selected_issue_total", float(full_primary["selected_issue_total"]), args.expected_primary_issue_stock, math.isclose(float(full_primary["selected_issue_total"]), args.expected_primary_issue_stock, abs_tol=1e-9) or not args.strict_expected_counts)
    add_qc("primary_sensitivity_selected_file_rows", int(sens_primary["selected_file_rows"]), args.expected_sensitivity_primary_selected_expanded_rows, int(sens_primary["selected_file_rows"]) == args.expected_sensitivity_primary_selected_expanded_rows or not args.strict_expected_counts)
    add_qc("primary_sensitivity_selected_unique_files", int(sens_primary["selected_unique_historical_files"]), args.expected_sensitivity_primary_selected_unique_files, int(sens_primary["selected_unique_historical_files"]) == args.expected_sensitivity_primary_selected_unique_files or not args.strict_expected_counts)
    add_qc("primary_sensitivity_selected_issue_total", float(sens_primary["selected_issue_total"]), args.expected_sensitivity_primary_issue_stock, math.isclose(float(sens_primary["selected_issue_total"]), args.expected_sensitivity_primary_issue_stock, abs_tol=1e-9) or not args.strict_expected_counts)
    add_qc("negative_selected_issue_values", int((long_panel[list(BURDEN_SOURCES)].to_numpy(dtype=float) < 0).sum()), 0, not (long_panel[list(BURDEN_SOURCES)].to_numpy(dtype=float) < 0).any())
    add_qc("log1p_outcome_recomputation_mismatches", log_mismatches, 0, log_mismatches == 0)
    qc = pd.DataFrame(qc_rows)
    hard_failures = int(qc["passed"].ne(1).sum())
    if hard_failures:
        abort(f"I08 hard QC failed with {hard_failures} checks")

    output_panel = args.output_dir / "quality_ml_fun_cfun_threshold_input_panel.csv.gz"
    output_global = args.output_dir / "quality_ml_fun_cfun_threshold_input_global_audit.csv"
    output_timing = args.output_dir / "quality_ml_fun_cfun_threshold_input_by_treatment_timing.csv"
    output_sample = args.output_dir / "quality_ml_fun_cfun_threshold_input_sample_summary.csv"
    output_scope = args.output_dir / "quality_ml_fun_cfun_threshold_input_scope_sensitivity.csv"
    output_outcomes = args.output_dir / "quality_ml_fun_cfun_threshold_input_outcome_spec.csv"
    output_reproduction = args.output_dir / "quality_ml_fun_cfun_threshold_input_i07_reproduction.csv"
    output_checks = args.output_dir / "quality_ml_fun_cfun_threshold_input_checks.csv"
    output_summary = args.output_dir / "quality_ml_fun_cfun_threshold_input_summary.csv"
    output_metadata = args.output_dir / "quality_ml_fun_cfun_threshold_input_metadata.json"

    long_panel.to_csv(output_panel, index=False, compression="gzip")
    global_audit.to_csv(output_global, index=False)
    pd.DataFrame(timing_rows).to_csv(output_timing, index=False)
    sample_summary.to_csv(output_sample, index=False)
    scope_spec.to_csv(output_scope, index=False)
    outcome_spec.to_csv(output_outcomes, index=False)
    reproduction.to_csv(output_reproduction, index=False)
    qc.to_csv(output_checks, index=False)

    summary = pd.DataFrame([
        ("script_version", f"run-x-i08-{IMPLEMENTATION_VERSION}"),
        ("status", "PASS"),
        ("ml_metric", ML_METRIC),
        ("quality_semantics", "unresolved_sonarqube_issue_stock_at_historical_snapshot"),
        ("mapping_spec", MAPPING_SPEC),
        ("thresholds", len(threshold_spec)),
        ("sample_specs", len(sample_repo_ids)),
        ("full_sample_repo_month_rows", full_counts["repo_month_rows"]),
        ("scope_sensitivity_repo_month_rows", sensitivity_counts["repo_month_rows"]),
        ("long_panel_rows", len(long_panel)),
        ("primary_threshold", PRIMARY_THRESHOLD),
        ("primary_full_selected_file_rows", int(full_primary["selected_file_rows"])),
        ("primary_full_selected_unique_files", int(full_primary["selected_unique_historical_files"])),
        ("primary_full_selected_issue_total", float(full_primary["selected_issue_total"])),
        ("eligible_expanded_file_rows", eligible_rows),
        ("eligible_unique_historical_files", eligible_unique),
        ("scope_sensitivity_repositories", len(scope_repos)),
        ("i07_threshold_reproduction_mismatches", reproduction_failures),
        ("density_computed", 0),
        ("hard_qc_failures", hard_failures),
    ], columns=["metric", "value"])
    summary.to_csv(output_summary, index=False)

    metadata = {
        "experiment_name": EXPERIMENT_NAME,
        "implementation_version": IMPLEMENTATION_VERSION,
        "inputs": {
            "i06_file": str(args.i06_file), "i06_sha256": sha256_file(args.i06_file),
            "i06_summary_file": str(args.i06_summary_file), "i06_summary_sha256": sha256_file(args.i06_summary_file),
            "i07_threshold_spec_file": str(args.i07_threshold_spec_file), "i07_threshold_spec_sha256": sha256_file(args.i07_threshold_spec_file),
            "i07_threshold_audit_file": str(args.i07_threshold_audit_file), "i07_threshold_audit_sha256": sha256_file(args.i07_threshold_audit_file),
            "i07_summary_file": str(args.i07_summary_file), "i07_summary_sha256": sha256_file(args.i07_summary_file),
            "d02_file": str(args.d02_file), "d02_sha256": sha256_file(args.d02_file),
            "d02_outside_scope_file": str(args.d02_outside_scope_file), "d02_outside_scope_sha256": sha256_file(args.d02_outside_scope_file),
            "b06_file": str(args.b06_file), "b06_sha256": sha256_file(args.b06_file),
        },
        "ml_metric": ML_METRIC,
        "operator": STRICT_OPERATOR,
        "boundary_comparison": "exact integer AGC-body-token numerator / total-body-token denominator",
        "threshold_grid": [float(value) for value in threshold_spec["threshold"]],
        "primary_threshold": PRIMARY_THRESHOLD,
        "mapping_spec": MAPPING_SPEC,
        "sample_specs": ["full_sample", "exclude_scope_mismatch_repos"],
        "scope_excluded_repositories": scope_repos.to_dict(orient="records"),
        "quality_outcomes_consumed": True,
        "treatment_effect_estimated": False,
        "density_computed": False,
        "resolved_d02_burden_columns": burden_columns,
        "selection_policy": "I07 thresholds are frozen before quality analysis; never choose a threshold using downstream DiD significance.",
        "downstream_experiment": "run-x-i09",
    }
    output_metadata.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("=" * 80)
    print("run-x-i08-v1 combined ML threshold x SonarQube burden input")
    print("Status:                                  PASS")
    print(f"Thresholds:                              {len(threshold_spec)}")
    print(f"Sample specifications:                   {len(sample_repo_ids)}")
    print(f"Full-sample repo-month rows:             {full_counts['repo_month_rows']}")
    print(f"Scope-sensitivity repo-month rows:       {sensitivity_counts['repo_month_rows']}")
    print(f"Long panel rows:                         {len(long_panel)}")
    print(f"Primary threshold:                       {PRIMARY_THRESHOLD:.2f}")
    print(f"Primary full selected files:             {int(full_primary['selected_file_rows'])}")
    print(f"Primary full selected unique files:      {int(full_primary['selected_unique_historical_files'])}")
    print(f"Primary full selected issue stock:       {float(full_primary['selected_issue_total']):.0f}")
    print(f"ML-eligible expanded files:              {eligible_rows}")
    print(f"ML-eligible unique historical files:     {eligible_unique}")
    print(f"I06/D02 missing file_sha256 files:       {missing_sha['i06_missing_sha_files']}/{missing_sha['d02_missing_sha_files']}")
    print(f"Scope-sensitivity repositories excluded: {len(scope_repos)}")
    print("I07 21-threshold reproduction:           PASS")
    print("Density computed:                        0")
    print("Hard QC failures:                        0")
    print(f"I09 input panel:                         {output_panel}")
    print("=" * 80)


if __name__ == "__main__":
    main()
