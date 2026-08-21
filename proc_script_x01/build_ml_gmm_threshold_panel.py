#!/usr/bin/env python3
"""Build ML-threshold sensitivity repo-month quality panels for run-x-e03.

This script reuses frozen upstream artifacts without rerunning ML inference or
SonarQube. It joins the continuous A04 file-level ML AGC share to the canonical
D02 file-level SonarQube burden using the exact historical file identity, then
reaggregates unresolved issue stock for the requested strict file thresholds.

Primary scientific contract
---------------------------
- ML metric: file_ml_agc_share_space_by_token_weighted
- Comparison: strict greater-than (>)
- Threshold grid: 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50
- Frozen primary threshold remains 0.50.
- No threshold is selected based on the downstream GMM p-value.
- A04 no-FUN/not-prepared files remain unclassified and are never selected.
- The 0.50 repo-month burden must exactly reproduce the frozen D05 primary
  configuration before any downstream GMM estimation is allowed.

Inputs
------
A04 python_ml_fun_file_scores.csv
D02 python_fun_file_quality_burden.csv.gz
B06 quality_did_panel_python_sonarqube.csv
D05 quality_ml_fun_repo_month_panel.csv.gz (0.50 reproduction reference)

Outputs
-------
ml_gmm_threshold_repo_month_panel.csv.gz
ml_gmm_threshold_support.csv
ml_gmm_threshold_reproduction_audit.csv
ml_gmm_threshold_join_audit.csv
ml_gmm_threshold_metadata.csv
"""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

IMPLEMENTATION_VERSION = "v8"
ML_METRIC = "file_ml_agc_share_space_by_token_weighted"
STRICT_OPERATOR = ">"
DEFAULT_THRESHOLDS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50)
PRIMARY_THRESHOLD = 0.50
FILE_KEYS = ("snapshot_id", "relative_path", "file_sha256")


def abort(message: str) -> "NoReturn":
    raise SystemExit(f"ERROR: {message}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_columns(df: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = sorted(set(required) - set(df.columns))
    if missing:
        abort(f"{label} is missing required columns: {', '.join(missing)}")


def parse_thresholds(text: str) -> list[float]:
    values: list[float] = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = float(token)
        except ValueError:
            abort(f"Invalid threshold value: {token}")
        if not (0.0 <= value <= 1.0):
            abort(f"Threshold must lie in [0,1]: {value}")
        values.append(value)
    if not values:
        abort("At least one threshold is required")
    if len(set(values)) != len(values):
        abort("Threshold values must be unique")
    values = sorted(values)
    if not any(math.isclose(v, PRIMARY_THRESHOLD, abs_tol=1e-12) for v in values):
        abort("Threshold grid must include the frozen primary threshold 0.50")
    return values


def threshold_id(value: float) -> str:
    return f"t{int(round(value * 100)):02d}"


def normalize_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    text = series.astype(str).str.strip().str.lower()
    return text.isin({"1", "true", "t", "yes", "y"})


def infer_repo_time_columns(df: pd.DataFrame) -> tuple[str, str]:
    repo_candidates = ["repo_id", "repo_name"]
    time_candidates = ["time_index", "time", "repo_month", "snapshot_time"]
    repo = next((c for c in repo_candidates if c in df.columns), None)
    time = next((c for c in time_candidates if c in df.columns), None)
    if repo is None or time is None:
        abort(
            "D02 must contain a repository/month identity. "
            f"Found repo={repo}, time={time}; columns={list(df.columns)}"
        )
    return repo, time


def build_reference_lookup(d05: pd.DataFrame) -> pd.DataFrame:
    required = {
        "sample_spec",
        "mapping_spec",
        "repo_id",
        "time_index",
        "selected_issue_total",
        "log1p_selected_issue_total",
    }
    require_columns(d05, required, "D05 reference panel")
    primary = d05.loc[
        (d05["sample_spec"].astype(str) == "full_sample")
        & (d05["mapping_spec"].astype(str) == "all_ml_files")
    ].copy()
    if len(primary) != 1954:
        abort(f"Expected 1,954 D05 primary rows; found {len(primary)}")
    if primary.duplicated(["repo_id", "time_index"]).any():
        abort("D05 primary reference contains duplicate repo_id/time_index keys")
    primary["repo_id"] = pd.to_numeric(primary["repo_id"], errors="raise").astype(int)
    primary["time_index"] = pd.to_numeric(primary["time_index"], errors="raise").astype(int)
    primary["selected_issue_total"] = pd.to_numeric(primary["selected_issue_total"], errors="raise")
    primary["log1p_selected_issue_total"] = pd.to_numeric(
        primary["log1p_selected_issue_total"], errors="raise"
    )
    if "selected_file_rows" in primary.columns:
        primary["selected_file_rows"] = pd.to_numeric(primary["selected_file_rows"], errors="raise")
    elif "selected_file_count" in primary.columns:
        primary["selected_file_rows"] = pd.to_numeric(primary["selected_file_count"], errors="raise")
    else:
        primary["selected_file_rows"] = np.nan
    return primary[
        [
            "repo_id",
            "time_index",
            "selected_file_rows",
            "selected_issue_total",
            "log1p_selected_issue_total",
        ]
    ]


def infer_issue_total_column(
    merged: pd.DataFrame,
    reference: pd.DataFrame,
    scored_mask: pd.Series,
) -> tuple[str, pd.DataFrame]:
    """Infer the canonical D02 total-issue column by exact D05 reproduction.

    D02 is a frozen upstream artifact whose historical revisions used slightly
    different descriptive column names. Instead of guessing the semantic total,
    test numeric issue-like D02 columns at the frozen >0.50 rule and require an
    exact repo-month match to D05 selected_issue_total.
    """
    candidate_names = [
        c
        for c in merged.columns
        if c not in FILE_KEYS
        and c not in {ML_METRIC, "repo_id", "time_index"}
        and any(token in c.lower() for token in ("issue", "warning", "sonar"))
    ]
    # Prefer known semantic names first while still allowing provenance-safe
    # discovery through exact reproduction.
    preferred = [
        "issue_total",
        "sonar_issue_total",
        "sonarqube_issue_total",
        "unresolved_issue_total",
        "issue_total_py_sonarqube",
        "python_issue_total",
        "total_issues",
    ]
    ordered = [c for c in preferred if c in candidate_names] + [
        c for c in candidate_names if c not in preferred
    ]
    if not ordered:
        abort(
            "Could not find any issue-like D02 columns for the 0.50 reproduction test. "
            f"D02 columns after join: {list(merged.columns)}"
        )

    ref = reference[["repo_id", "time_index", "selected_issue_total"]].copy()
    ref = ref.sort_values(["repo_id", "time_index"]).reset_index(drop=True)
    audit_rows: list[dict[str, object]] = []
    exact_matches: list[str] = []
    selected = merged.loc[scored_mask & (merged[ML_METRIC] > PRIMARY_THRESHOLD)].copy()

    for column in ordered:
        numeric = pd.to_numeric(selected[column], errors="coerce")
        if numeric.isna().any():
            audit_rows.append(
                {
                    "candidate": column,
                    "numeric": 0,
                    "repo_month_mismatches": np.nan,
                    "global_sum": np.nan,
                    "reference_global_sum": float(ref["selected_issue_total"].sum()),
                    "exact_match": 0,
                    "note": "contains non-numeric/missing selected values",
                }
            )
            continue
        if (numeric < 0).any():
            continue
        temp = selected[["repo_id", "time_index"]].copy()
        temp["value"] = numeric.to_numpy()
        agg = temp.groupby(["repo_id", "time_index"], as_index=False)["value"].sum()
        check = ref.merge(agg, on=["repo_id", "time_index"], how="left")
        check["value"] = check["value"].fillna(0.0)
        diff = np.abs(check["value"].to_numpy() - check["selected_issue_total"].to_numpy())
        mismatches = int((diff > 1e-9).sum())
        exact = mismatches == 0
        audit_rows.append(
            {
                "candidate": column,
                "numeric": 1,
                "repo_month_mismatches": mismatches,
                "global_sum": float(check["value"].sum()),
                "reference_global_sum": float(check["selected_issue_total"].sum()),
                "exact_match": int(exact),
                "note": "0.50 D05 repo-month reproduction",
            }
        )
        if exact:
            exact_matches.append(column)

    audit = pd.DataFrame(audit_rows)
    if not exact_matches:
        best = audit.sort_values("repo_month_mismatches", na_position="last").head(10)
        abort(
            "No D02 issue-like column exactly reproduces D05 primary selected_issue_total at >0.50. "
            "Inspect ml_gmm_threshold_issue_column_audit.csv after rerunning with the printed columns. "
            f"Best candidates: {best.to_dict(orient='records')}"
        )
    chosen = next((c for c in preferred if c in exact_matches), exact_matches[0])
    return chosen, audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a04-file", required=True, type=Path)
    parser.add_argument("--d02-file", required=True, type=Path)
    parser.add_argument("--b06-file", required=True, type=Path)
    parser.add_argument("--d05-reference-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--thresholds", default=",".join(f"{v:.2f}" for v in DEFAULT_THRESHOLDS))
    parser.add_argument("--expected-a04-rows", type=int, default=494592)
    parser.add_argument("--expected-d02-rows", type=int, default=510297)
    parser.add_argument("--expected-b06-rows", type=int, default=1954)
    args = parser.parse_args()

    for path in (args.a04_file, args.d02_file, args.b06_file, args.d05_reference_file):
        if not path.is_file():
            abort(f"Missing input file: {path}")
    thresholds = parse_thresholds(args.thresholds)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading A04 continuous ML file scores: {args.a04_file}")
    a04 = pd.read_csv(args.a04_file, low_memory=False)
    require_columns(a04, [*FILE_KEYS, ML_METRIC], "A04 file scores")
    if len(a04) != args.expected_a04_rows:
        abort(f"A04 row count mismatch: expected {args.expected_a04_rows}, observed {len(a04)}")
    if a04.duplicated(list(FILE_KEYS)).any():
        abort("A04 contains duplicate historical file keys")
    a04[ML_METRIC] = pd.to_numeric(a04[ML_METRIC], errors="coerce")
    if "ml_fun_status" in a04.columns:
        scored = a04["ml_fun_status"].astype(str).eq("scored")
    elif "file_ml_fun_status" in a04.columns:
        scored = a04["file_ml_fun_status"].astype(str).eq("scored")
    else:
        # Frozen A04 semantics: continuous score is defined only for files with
        # scored primary FUN; no-FUN/not-prepared remain NA and unclassified.
        scored = a04[ML_METRIC].notna()
    if a04.loc[scored, ML_METRIC].isna().any():
        abort("A04 scored files contain missing ML weighted shares")
    if ((a04.loc[scored, ML_METRIC] < 0) | (a04.loc[scored, ML_METRIC] > 1)).any():
        abort("A04 ML weighted shares must lie in [0,1]")

    print(f"Reading D02 canonical file-level quality burden: {args.d02_file}")
    d02 = pd.read_csv(args.d02_file, low_memory=False)
    require_columns(d02, FILE_KEYS, "D02 file burden")
    if len(d02) != args.expected_d02_rows:
        abort(f"D02 row count mismatch: expected {args.expected_d02_rows}, observed {len(d02)}")

    print(f"Reading B06 authoritative repo-month panel: {args.b06_file}")
    b06 = pd.read_csv(args.b06_file, low_memory=False)
    require_columns(b06, ["repo_id", "time_index"], "B06 panel")
    if len(b06) != args.expected_b06_rows:
        abort(f"B06 row count mismatch: expected {args.expected_b06_rows}, observed {len(b06)}")
    b06["repo_id"] = pd.to_numeric(b06["repo_id"], errors="raise").astype(int)
    b06["time_index"] = pd.to_numeric(b06["time_index"], errors="raise").astype(int)
    if b06.duplicated(["repo_id", "time_index"]).any():
        abort("B06 contains duplicate repo_id/time_index keys")

    print(f"Reading D05 frozen 0.50 reference panel: {args.d05_reference_file}")
    d05 = pd.read_csv(args.d05_reference_file, low_memory=False)
    reference = build_reference_lookup(d05)

    # The exact A04-D02 identity is the frozen D05 join contract. D02 can have
    # repeated file identities because one historical snapshot is reused across
    # multiple repo-month rows; A04 must remain one row per historical file.
    a04_small_cols = list(FILE_KEYS) + [ML_METRIC]
    for optional in ("ml_fun_status", "file_ml_fun_status"):
        if optional in a04.columns:
            a04_small_cols.append(optional)
    a04_small = a04[a04_small_cols].copy()
    merged = d02.merge(a04_small, on=list(FILE_KEYS), how="left", validate="many_to_one", indicator=True)
    d02_only = int((merged["_merge"] == "left_only").sum())
    if d02_only:
        abort(f"D02 has {d02_only} rows without an exact A04 historical-file match")
    merged.drop(columns=["_merge"], inplace=True)

    repo_col, time_col = infer_repo_time_columns(merged)

    # Resolve every D02 row to the authoritative numeric B06 panel key. D02
    # production normally carries repo_id/time_index directly, but older frozen
    # revisions may carry repo_id/time or repo_name/time instead.
    if "repo_id" in merged.columns and "time_index" in merged.columns:
        merged["repo_id"] = pd.to_numeric(merged["repo_id"], errors="raise").astype(int)
        merged["time_index"] = pd.to_numeric(merged["time_index"], errors="raise").astype(int)
    elif "repo_id" in merged.columns and "time" in merged.columns:
        merged["repo_id"] = pd.to_numeric(merged["repo_id"], errors="raise").astype(int)
        resolver = b06[["repo_id", "time", "time_index"]].drop_duplicates()
        merged = merged.merge(resolver, on=["repo_id", "time"], how="left", validate="many_to_one")
    elif "repo_name" in merged.columns and "time_index" in merged.columns:
        merged["time_index"] = pd.to_numeric(merged["time_index"], errors="raise").astype(int)
        resolver = b06[["repo_name", "time_index", "repo_id"]].drop_duplicates()
        merged = merged.merge(resolver, on=["repo_name", "time_index"], how="left", validate="many_to_one")
    elif "repo_name" in merged.columns and "time" in merged.columns:
        resolver = b06[["repo_name", "time", "repo_id", "time_index"]].drop_duplicates()
        merged = merged.merge(resolver, on=["repo_name", "time"], how="left", validate="many_to_one")
    else:
        abort(
            "D02 does not expose a supported repo-month identity. "
            f"Detected repo={repo_col}, time={time_col}"
        )
    if "repo_id" not in merged.columns or "time_index" not in merged.columns:
        abort("Could not construct repo_id/time_index after B06 key resolution")
    if merged["repo_id"].isna().any() or merged["time_index"].isna().any():
        abort("Could not resolve all D02 rows to B06 repo_id/time_index")
    merged["repo_id"] = pd.to_numeric(merged["repo_id"], errors="raise").astype(int)
    merged["time_index"] = pd.to_numeric(merged["time_index"], errors="raise").astype(int)

    if "ml_fun_status" in merged.columns:
        merged_scored = merged["ml_fun_status"].astype(str).eq("scored")
    elif "file_ml_fun_status" in merged.columns:
        merged_scored = merged["file_ml_fun_status"].astype(str).eq("scored")
    else:
        merged_scored = merged[ML_METRIC].notna()

    issue_col, issue_audit = infer_issue_total_column(merged, reference, merged_scored)
    issue_audit_path = args.output_dir / "ml_gmm_threshold_issue_column_audit.csv"
    issue_audit.to_csv(issue_audit_path, index=False)
    print(f"Resolved canonical D02 total-issue column by exact D05 reproduction: {issue_col}")

    merged[issue_col] = pd.to_numeric(merged[issue_col], errors="raise")
    if merged[issue_col].isna().any() or (merged[issue_col] < 0).any():
        abort(f"D02 issue column {issue_col} must be complete and non-negative")

    panel_parts: list[pd.DataFrame] = []
    support_rows: list[dict[str, object]] = []
    for threshold in thresholds:
        selected = merged_scored & (merged[ML_METRIC] > threshold)
        selected_rows = merged.loc[selected, ["repo_id", "time_index", issue_col]].copy()
        agg = selected_rows.groupby(["repo_id", "time_index"], as_index=False).agg(
            selected_file_rows=(issue_col, "size"),
            selected_issue_total=(issue_col, "sum"),
        )
        panel = b06.merge(agg, on=["repo_id", "time_index"], how="left", validate="one_to_one")
        panel["selected_file_rows"] = panel["selected_file_rows"].fillna(0).astype(int)
        panel["selected_issue_total"] = panel["selected_issue_total"].fillna(0.0)
        panel["log1p_selected_issue_total"] = np.log1p(panel["selected_issue_total"].astype(float))
        panel["threshold_id"] = threshold_id(threshold)
        panel["ml_threshold"] = float(threshold)
        panel["ml_operator"] = STRICT_OPERATOR
        panel["ml_metric"] = ML_METRIC
        panel["primary_analysis"] = int(math.isclose(threshold, PRIMARY_THRESHOLD, abs_tol=1e-12))
        panel_parts.append(panel)

        zero_share = float((panel["selected_issue_total"] == 0).mean())
        variation_repos = int(
            panel.groupby("repo_id")["log1p_selected_issue_total"].nunique().gt(1).sum()
        )
        support_rows.append(
            {
                "threshold_id": threshold_id(threshold),
                "threshold": threshold,
                "primary_analysis": int(math.isclose(threshold, PRIMARY_THRESHOLD, abs_tol=1e-12)),
                "source_repo_month_rows": len(panel),
                "selected_file_rows": int(selected.sum()),
                "selected_unique_historical_files": int(
                    merged.loc[selected, list(FILE_KEYS)].drop_duplicates().shape[0]
                ),
                "selected_issue_total": float(panel["selected_issue_total"].sum()),
                "zero_issue_repo_month_share": zero_share,
                "repositories_with_within_quality_variation": variation_repos,
            }
        )

    long_panel = pd.concat(panel_parts, ignore_index=True)
    expected_long_rows = len(thresholds) * args.expected_b06_rows
    if len(long_panel) != expected_long_rows:
        abort(f"Threshold panel row count mismatch: expected {expected_long_rows}, observed {len(long_panel)}")

    # Threshold support must shrink monotonically as the strict threshold rises.
    support = pd.DataFrame(support_rows).sort_values("threshold").reset_index(drop=True)
    for metric in ("selected_file_rows", "selected_unique_historical_files", "selected_issue_total"):
        values = support[metric].to_numpy(dtype=float)
        if np.any(np.diff(values) > 1e-9):
            abort(f"Threshold support is not monotone non-increasing for {metric}: {values}")

    # The frozen primary threshold is a hard reproduction gate, not merely a
    # global-count check. Every repo-month outcome must match D05 exactly.
    t50 = long_panel.loc[np.isclose(long_panel["ml_threshold"], PRIMARY_THRESHOLD)].copy()
    t50_check = reference.merge(
        t50[["repo_id", "time_index", "selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"]],
        on=["repo_id", "time_index"],
        suffixes=("_d05", "_new"),
        how="outer",
        indicator=True,
    )
    t50_check["file_rows_match"] = (
        t50_check["selected_file_rows_d05"].isna()
        | np.isclose(t50_check["selected_file_rows_d05"], t50_check["selected_file_rows_new"], atol=0, rtol=0)
    )
    t50_check["issue_total_match"] = np.isclose(
        t50_check["selected_issue_total_d05"], t50_check["selected_issue_total_new"], atol=1e-9, rtol=0
    )
    t50_check["log_match"] = np.isclose(
        t50_check["log1p_selected_issue_total_d05"],
        t50_check["log1p_selected_issue_total_new"],
        atol=1e-12,
        rtol=0,
    )
    t50_mismatches = t50_check.loc[
        (t50_check["_merge"] != "both")
        | ~t50_check["file_rows_match"]
        | ~t50_check["issue_total_match"]
        | ~t50_check["log_match"]
    ]
    if not t50_mismatches.empty:
        abort(f"0.50 threshold failed exact D05 reproduction for {len(t50_mismatches)} repo-month rows")

    output_panel = args.output_dir / "ml_gmm_threshold_repo_month_panel.csv.gz"
    output_support = args.output_dir / "ml_gmm_threshold_support.csv"
    output_repro = args.output_dir / "ml_gmm_threshold_reproduction_audit.csv"
    output_join = args.output_dir / "ml_gmm_threshold_join_audit.csv"
    output_metadata = args.output_dir / "ml_gmm_threshold_metadata.csv"

    long_panel.to_csv(output_panel, index=False, compression="gzip")
    support.to_csv(output_support, index=False)
    pd.DataFrame(
        [
            {
                "threshold": PRIMARY_THRESHOLD,
                "repo_month_rows": len(t50_check),
                "key_mismatches": int((t50_check["_merge"] != "both").sum()),
                "selected_file_row_mismatches": int((~t50_check["file_rows_match"]).sum()),
                "selected_issue_total_mismatches": int((~t50_check["issue_total_match"]).sum()),
                "log1p_outcome_mismatches": int((~t50_check["log_match"]).sum()),
                "status": "pass",
            }
        ]
    ).to_csv(output_repro, index=False)

    pd.DataFrame(
        [
            {"check": "a04_rows", "observed": len(a04), "expected": args.expected_a04_rows, "status": "pass"},
            {"check": "d02_rows", "observed": len(d02), "expected": args.expected_d02_rows, "status": "pass"},
            {"check": "b06_rows", "observed": len(b06), "expected": args.expected_b06_rows, "status": "pass"},
            {"check": "d02_rows_without_a04_match", "observed": d02_only, "expected": 0, "status": "pass"},
            {"check": "threshold_count", "observed": len(thresholds), "expected": len(DEFAULT_THRESHOLDS), "status": "pass"},
            {"check": "long_panel_rows", "observed": len(long_panel), "expected": expected_long_rows, "status": "pass"},
        ]
    ).to_csv(output_join, index=False)

    metadata = pd.DataFrame(
        [
            ("implementation_version", IMPLEMENTATION_VERSION),
            ("a04_file", str(args.a04_file)),
            ("a04_sha256", sha256_file(args.a04_file)),
            ("d02_file", str(args.d02_file)),
            ("d02_sha256", sha256_file(args.d02_file)),
            ("b06_file", str(args.b06_file)),
            ("b06_sha256", sha256_file(args.b06_file)),
            ("d05_reference_file", str(args.d05_reference_file)),
            ("d05_reference_sha256", sha256_file(args.d05_reference_file)),
            ("ml_metric", ML_METRIC),
            ("comparison_operator", STRICT_OPERATOR),
            ("thresholds", ",".join(f"{v:.2f}" for v in thresholds)),
            ("primary_threshold", f"{PRIMARY_THRESHOLD:.2f}"),
            ("d02_issue_total_column_resolved", issue_col),
            ("selection_policy", "report all thresholds; no significance-based threshold selection"),
        ],
        columns=["metric", "value"],
    )
    metadata.to_csv(output_metadata, index=False)

    print("Threshold sensitivity input panel: PASS")
    print(f"Thresholds: {','.join(f'{v:.2f}' for v in thresholds)}")
    print(f"Primary 0.50 reproduction rows: {len(t50_check)} / mismatches=0")
    print(f"Output panel: {output_panel}")
    print(f"Support: {output_support}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
