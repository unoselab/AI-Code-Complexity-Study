#!/usr/bin/env python3
"""
Audit readiness of the NPR-CM quality-to-velocity dynamic-panel GMM inputs.

This K01 audit is intentionally model-free. It validates that the existing H03
CM-localized NPR quality panel can be joined to the authoritative B06 Python
velocity/covariate panel under the same exact-calendar contract used by the
existing NPR-RF and ML-RF dynamic-panel analyses.

Primary analysis contract checked here:
- Detector: NPR
- Localization scope: CM (class methods)
- Primary detector cutoff: tau_NPR = 1.571637
- Selection operator inherited from H03: strict >
- Localized quality outcome: log1p(selected_issue_total)
- Velocity outcome: log_lines_added_py_source
- Exact-calendar support: current t must have exact t-1 and t-2 rows
- Expected active GMM sample: 1,631 repo-month rows from 146 repositories
- Expected active repository split: 61 treated and 85 controls
- Expected active post-adoption treated rows: 350

The script does not fit a GMM model and does not call any previous analysis
script. It writes audit artifacts only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_VERSION = "run-x-k01-v1"
PRIMARY_THRESHOLD = 1.571637
EXPECTED_NPR_METRIC = "file_npr_cfun_space_by_token_weighted"
EXPECTED_COMPARISON = ">"


@dataclass
class Check:
    check: str
    observed: Any
    expected: Any
    status: str
    note: str


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def require_columns(df: pd.DataFrame, required: list[str], label: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def numeric(df: pd.DataFrame, columns: list[str], label: str) -> None:
    for column in columns:
        before_nonempty = df[column].notna() & df[column].astype(str).str.strip().ne("")
        converted = pd.to_numeric(df[column], errors="coerce")
        generated_na = int((before_nonempty & converted.isna()).sum())
        if generated_na:
            raise ValueError(f"{label}.{column} generated {generated_na} NA values during numeric coercion")
        df[column] = converted


def add_check(checks: list[Check], name: str, observed: Any, expected: Any, ok: bool, note: str) -> None:
    checks.append(Check(name, observed, expected, "pass" if ok else "fail", note))


def build_exact_calendar_sample(primary: pd.DataFrame, b06: pd.DataFrame) -> pd.DataFrame:
    """Return current-month rows with exact t-1 and t-2 calendar support."""
    base = primary.merge(
        b06[["repo_id", "time_index", "log_lines_added_py_source"]],
        on=["repo_id", "time_index"],
        how="left",
        validate="one_to_one",
    )

    q_lookup = primary[["repo_id", "time_index", "log1p_selected_issue_total"]].copy()
    q_lag1 = q_lookup.rename(
        columns={"time_index": "time_index_lag1", "log1p_selected_issue_total": "quality_lag1"}
    )
    q_lag2 = q_lookup.rename(
        columns={"time_index": "time_index_lag2", "log1p_selected_issue_total": "quality_lag2"}
    )

    v_lookup = b06[["repo_id", "time_index", "log_lines_added_py_source"]].copy()
    v_lag1 = v_lookup.rename(
        columns={"time_index": "time_index_lag1", "log_lines_added_py_source": "velocity_lag1"}
    )
    v_lag2 = v_lookup.rename(
        columns={"time_index": "time_index_lag2", "log_lines_added_py_source": "velocity_lag2"}
    )

    base["time_index_lag1"] = base["time_index"] - 1
    base["time_index_lag2"] = base["time_index"] - 2
    base = base.merge(q_lag1, on=["repo_id", "time_index_lag1"], how="left", validate="many_to_one")
    base = base.merge(q_lag2, on=["repo_id", "time_index_lag2"], how="left", validate="many_to_one")
    base = base.merge(v_lag1, on=["repo_id", "time_index_lag1"], how="left", validate="many_to_one")
    base = base.merge(v_lag2, on=["repo_id", "time_index_lag2"], how="left", validate="many_to_one")

    support = base[
        base[["quality_lag1", "quality_lag2", "velocity_lag1", "velocity_lag2"]].notna().all(axis=1)
    ].copy()
    return support.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)


def run_audit(args: argparse.Namespace) -> int:
    h03_path = Path(args.h03_panel_file)
    b06_path = Path(args.b06_panel_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    h03 = pd.read_csv(h03_path, compression="infer", low_memory=False)
    b06 = pd.read_csv(b06_path, low_memory=False)

    h03_required = [
        "sample_spec", "threshold_id", "threshold_role", "threshold",
        "comparison_operator", "npr_metric", "repo_id", "repo_name",
        "dataset_source", "treatment_group", "time_index", "event_index",
        "selected_issue_total", "log1p_selected_issue_total",
    ]
    b06_required = [
        "repo_id", "repo_name", "dataset_source", "treatment_group",
        "time_index", "event_index", "log_lines_added_py_source",
        "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues",
    ]
    require_columns(h03, h03_required, "H03 panel")
    require_columns(b06, b06_required, "B06 panel")

    numeric(h03, ["threshold", "repo_id", "treatment_group", "time_index", "event_index",
                  "selected_issue_total", "log1p_selected_issue_total"], "H03 panel")
    numeric(b06, ["repo_id", "treatment_group", "time_index", "event_index",
                  "log_lines_added_py_source", "log_age", "ncloc_py_sonarqube",
                  "log_contributors", "log_stars", "log_issues"], "B06 panel")

    primary = h03[
        h03["sample_spec"].map(clean_text).eq("full_sample")
        & h03["threshold_role"].map(clean_text).eq("primary")
        & np.isclose(h03["threshold"].astype(float), args.primary_threshold, atol=1e-12, rtol=0.0)
    ].copy()
    primary = primary.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)
    b06 = b06.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)

    checks: list[Check] = []
    add_check(checks, "python_3_11", platform.python_version(), "3.11.x",
              sys.version_info[:2] == (3, 11), "Project runtime contract.")
    add_check(checks, "h03_long_rows", len(h03), args.expected_h03_long_rows,
              len(h03) == args.expected_h03_long_rows, "Expected H03 threshold x sample long-panel rows.")
    add_check(checks, "primary_full_rows", len(primary), args.expected_panel_rows,
              len(primary) == args.expected_panel_rows, "Primary full-sample repo-month rows.")
    add_check(checks, "primary_repositories", int(primary["repo_id"].nunique()), args.expected_repositories,
              int(primary["repo_id"].nunique()) == args.expected_repositories, "Primary H03 repository count.")
    add_check(checks, "primary_treatment_repositories",
              int(primary.loc[primary["treatment_group"].eq(1), "repo_id"].nunique()),
              args.expected_treatment_repositories,
              int(primary.loc[primary["treatment_group"].eq(1), "repo_id"].nunique()) == args.expected_treatment_repositories,
              "Primary H03 treated repositories.")
    add_check(checks, "primary_control_repositories",
              int(primary.loc[primary["treatment_group"].eq(0), "repo_id"].nunique()),
              args.expected_control_repositories,
              int(primary.loc[primary["treatment_group"].eq(0), "repo_id"].nunique()) == args.expected_control_repositories,
              "Primary H03 control repositories.")
    add_check(checks, "primary_duplicate_repo_time_rows",
              int(primary.duplicated(["repo_id", "time_index"]).sum()), 0,
              not primary.duplicated(["repo_id", "time_index"]).any(), "Repo-month key must be unique.")

    operators = sorted({clean_text(x) for x in primary["comparison_operator"].dropna().unique()})
    metrics = sorted({clean_text(x) for x in primary["npr_metric"].dropna().unique()})
    add_check(checks, "primary_comparison_operator", "|".join(operators), EXPECTED_COMPARISON,
              operators == [EXPECTED_COMPARISON], "Primary NPR selection must remain strict >.")
    add_check(checks, "primary_npr_metric", "|".join(metrics), EXPECTED_NPR_METRIC,
              metrics == [EXPECTED_NPR_METRIC], "K01 must audit CM/class-method NPR, not RF or RF+CM.")

    recomputed = np.log1p(primary["selected_issue_total"].astype(float))
    max_log_diff = float(np.nanmax(np.abs(recomputed - primary["log1p_selected_issue_total"].astype(float)))) if len(primary) else float("nan")
    add_check(checks, "primary_log1p_recomputation_max_abs_diff", max_log_diff, 1e-12,
              bool(np.isfinite(max_log_diff) and max_log_diff <= 1e-12),
              "Localized quality must equal log1p(selected_issue_total).")

    b06_dup = int(b06.duplicated(["repo_id", "time_index"]).sum())
    add_check(checks, "b06_rows", len(b06), args.expected_panel_rows,
              len(b06) == args.expected_panel_rows, "Authoritative B06 row count.")
    add_check(checks, "b06_duplicate_repo_time_rows", b06_dup, 0, b06_dup == 0,
              "B06 repo-month key must be unique.")

    identity_cols = ["repo_id", "time_index", "repo_name", "dataset_source", "treatment_group", "event_index"]
    merged = primary[identity_cols].merge(
        b06[identity_cols], on=["repo_id", "time_index"], how="outer",
        suffixes=("_h03", "_b06"), indicator=True, validate="one_to_one"
    )
    unmatched = int(merged["_merge"].ne("both").sum())
    add_check(checks, "h03_b06_unmatched_repo_months", unmatched, 0, unmatched == 0,
              "Primary H03 and B06 must have the same full-sample repo-month universe.")

    mismatch_count = 0
    if unmatched == 0:
        for col in ["repo_name", "dataset_source", "treatment_group", "event_index"]:
            left = merged[f"{col}_h03"].map(clean_text)
            right = merged[f"{col}_b06"].map(clean_text)
            mismatch_count += int(left.ne(right).sum())
    add_check(checks, "h03_b06_identity_field_mismatches", mismatch_count, 0, mismatch_count == 0,
              "Repository identity, treatment group, and event index must agree.")

    b06_model_cols = ["log_lines_added_py_source", "log_age", "ncloc_py_sonarqube",
                      "log_contributors", "log_stars", "log_issues"]
    nonfinite = 0
    for col in b06_model_cols:
        values = b06[col].astype(float).to_numpy()
        nonfinite += int((~np.isfinite(values)).sum())
    add_check(checks, "b06_nonfinite_model_values", nonfinite, 0, nonfinite == 0,
              "Velocity and time-varying controls must be finite before lag construction.")

    exact = build_exact_calendar_sample(primary, b06)
    active_repos = int(exact["repo_id"].nunique())
    active_treated_repos = int(exact.loc[exact["treatment_group"].eq(1), "repo_id"].nunique())
    active_control_repos = int(exact.loc[exact["treatment_group"].eq(0), "repo_id"].nunique())
    post_mask = exact["treatment_group"].eq(1) & exact["event_index"].gt(0) & exact["time_index"].ge(exact["event_index"])
    post_rows = int(post_mask.sum())

    add_check(checks, "exact_calendar_active_rows", len(exact), args.expected_active_rows,
              len(exact) == args.expected_active_rows,
              "Current t must have exact t-1 and t-2 calendar support.")
    add_check(checks, "exact_calendar_active_repositories", active_repos, args.expected_active_repositories,
              active_repos == args.expected_active_repositories, "Expected common GMM repository support.")
    add_check(checks, "exact_calendar_treatment_repositories", active_treated_repos,
              args.expected_active_treatment_repositories,
              active_treated_repos == args.expected_active_treatment_repositories,
              "Expected treated repositories in active GMM sample.")
    add_check(checks, "exact_calendar_control_repositories", active_control_repos,
              args.expected_active_control_repositories,
              active_control_repos == args.expected_active_control_repositories,
              "Expected controls in active GMM sample.")
    add_check(checks, "exact_calendar_post_adoption_treated_rows", post_rows,
              args.expected_active_post_treated_rows,
              post_rows == args.expected_active_post_treated_rows,
              "Expected post-adoption treated observations after exact-calendar filtering.")

    lag_nonfinite = 0
    for col in ["quality_lag1", "quality_lag2", "velocity_lag1", "velocity_lag2", "log_lines_added_py_source"]:
        lag_nonfinite += int((~np.isfinite(exact[col].astype(float).to_numpy())).sum())
    add_check(checks, "active_lag_nonfinite_values", lag_nonfinite, 0, lag_nonfinite == 0,
              "Active exact-calendar sample must have finite quality/velocity lag values.")

    variation = exact.groupby("repo_id", sort=False)["log1p_selected_issue_total"].nunique(dropna=True)
    within_variation_repos = int((variation > 1).sum())
    positive_rows = int(exact["selected_issue_total"].gt(0).sum())

    audit_summary = pd.DataFrame([
        {
            "analysis": "NPR-CM quality_{t-1} -> velocity_t",
            "detector": "NPR",
            "scope": "CM",
            "primary_threshold": args.primary_threshold,
            "comparison_operator": EXPECTED_COMPARISON,
            "quality_metric": "log1p_selected_issue_total",
            "velocity_metric": "log_lines_added_py_source",
            "h03_primary_rows": len(primary),
            "h03_primary_repositories": int(primary["repo_id"].nunique()),
            "selected_issue_stock": int(primary["selected_issue_total"].sum()),
            "repo_months_with_positive_issue_burden": int(primary["selected_issue_total"].gt(0).sum()),
            "active_rows": len(exact),
            "active_repositories": active_repos,
            "active_treatment_repositories": active_treated_repos,
            "active_control_repositories": active_control_repos,
            "active_post_adoption_treated_rows": post_rows,
            "active_positive_issue_rows": positive_rows,
            "active_repositories_with_within_quality_variation": within_variation_repos,
        }
    ])

    checks_df = pd.DataFrame([asdict(c) for c in checks])
    hard_failures = int(checks_df["status"].eq("fail").sum())
    status = "PASS" if hard_failures == 0 else "FAIL"

    checks_path = output_dir / "k01_npr_cm_gmm_input_checks.csv"
    summary_path = output_dir / "k01_npr_cm_gmm_input_summary.csv"
    active_path = output_dir / "k01_npr_cm_exact_calendar_sample.csv.gz"
    metadata_path = output_dir / "metadata.json"
    json_path = output_dir / "summary.json"

    checks_df.to_csv(checks_path, index=False)
    audit_summary.to_csv(summary_path, index=False)
    exact.to_csv(active_path, index=False, compression="gzip")

    metadata = {
        "script_version": SCRIPT_VERSION,
        "python_version": platform.python_version(),
        "h03_panel_file": str(h03_path),
        "h03_panel_sha256": sha256_file(h03_path),
        "b06_panel_file": str(b06_path),
        "b06_panel_sha256": sha256_file(b06_path),
        "primary_threshold": args.primary_threshold,
        "detector": "NPR",
        "scope": "CM",
        "does_fit_gmm": False,
        "exact_calendar_rule": "require exact t-1 and t-2 repo-month rows",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "status": status,
        "hard_qc_failures": hard_failures,
        "checks": len(checks),
        "h03_primary_rows": len(primary),
        "h03_primary_repositories": int(primary["repo_id"].nunique()),
        "active_rows": len(exact),
        "active_repositories": active_repos,
        "active_treatment_repositories": active_treated_repos,
        "active_control_repositories": active_control_repos,
        "active_post_adoption_treated_rows": post_rows,
        "active_repositories_with_within_quality_variation": within_variation_repos,
        "outputs": [str(checks_path), str(summary_path), str(active_path), str(metadata_path)],
    }
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"K01 audit status:                         {status}")
    print(f"Hard QC failures:                        {hard_failures}")
    print(f"Primary H03 rows/repositories:           {len(primary)}/{int(primary['repo_id'].nunique())}")
    print(f"Exact-calendar active rows/repositories: {len(exact)}/{active_repos}")
    print(f"Active treated/control repositories:     {active_treated_repos}/{active_control_repos}")
    print(f"Active post-adoption treated rows:       {post_rows}")
    print(f"Within-quality-variation repositories:   {within_variation_repos}")
    return 0 if hard_failures == 0 else 1


def self_test() -> int:
    """Small deterministic test of the exact-calendar lag logic."""
    primary = pd.DataFrame(
        {
            "repo_id": [1, 1, 1, 1, 2, 2, 2],
            "time_index": [1, 2, 3, 4, 1, 3, 4],
            "log1p_selected_issue_total": np.log1p([0, 1, 2, 3, 0, 2, 4]),
            "selected_issue_total": [0, 1, 2, 3, 0, 2, 4],
            "treatment_group": [0, 0, 0, 0, 1, 1, 1],
            "event_index": [0, 0, 0, 0, 3, 3, 3],
        }
    )
    b06 = primary[["repo_id", "time_index"]].copy()
    b06["log_lines_added_py_source"] = [0.0, 0.2, 0.3, 0.4, 0.0, 0.3, 0.5]
    exact = build_exact_calendar_sample(primary, b06)
    keys = list(map(tuple, exact[["repo_id", "time_index"]].to_numpy()))
    assert keys == [(1, 3), (1, 4)], keys
    print("audit_npr_cm_gmm_inputs self-test: PASS")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--h03-panel-file")
    parser.add_argument("--b06-panel-file")
    parser.add_argument("--output-dir")
    parser.add_argument("--primary-threshold", type=float, default=PRIMARY_THRESHOLD)
    parser.add_argument("--expected-h03-long-rows", type=int, default=85118)
    parser.add_argument("--expected-panel-rows", type=int, default=1954)
    parser.add_argument("--expected-repositories", type=int, default=167)
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument("--expected-active-rows", type=int, default=1631)
    parser.add_argument("--expected-active-repositories", type=int, default=146)
    parser.add_argument("--expected-active-treatment-repositories", type=int, default=61)
    parser.add_argument("--expected-active-control-repositories", type=int, default=85)
    parser.add_argument("--expected-active-post-treated-rows", type=int, default=350)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return self_test()
    missing = [name for name in ["h03_panel_file", "b06_panel_file", "output_dir"] if not getattr(args, name)]
    if missing:
        raise SystemExit(f"Missing required arguments: {', '.join(missing)}")
    return run_audit(args)


if __name__ == "__main__":
    raise SystemExit(main())
