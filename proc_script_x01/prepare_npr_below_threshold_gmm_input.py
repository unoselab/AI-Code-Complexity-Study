#!/usr/bin/env python3
"""Prepare the below-threshold NPR repo-month input panel for run-x-g02.

The experiment partitions the canonical D02 Python file universe using the
continuous file-level NPR metric while preserving unclassified files as a
separate category:

    Eligible:      finite file_npr_fun_space_by_token_weighted
    Above:         finite NPR > 1.571637
    Below:         finite NPR <= 1.571637
    Unclassified:  NPR is missing or non-finite

The G02 output is a zero-inclusive repo-month input panel for the downstream
run-x-g03 GMM experiment. Its quality variable is the SonarQube issue burden
aggregated only over the Below set. Missing/non-finite NPR files are never treated as below-threshold.

Inputs
------
D02:
    Canonical repo-month/file SonarQube burden with continuous NPR metric.
B06:
    Authoritative 1,954-row repo-month panel used for all-file count auditing
    and downstream G03 velocity/covariate joins.
D03 reference:
    Previously validated NPR-primary repo-month panel used to reproduce the
    Above set exactly before trusting the complementary Below construction.

Outputs
-------
npr_below_threshold_repo_month_panel.csv.gz
    Zero-inclusive 1,954-row panel containing the below-threshold issue burden.
npr_below_threshold_support.csv
    Global support for all, eligible, above, below, and unclassified sets.
npr_below_threshold_reproduction_audit.csv
    Exact reproduction audit against the D03 primary high-NPR panel.
npr_below_threshold_qc.csv
    Hard set-algebra and B06 reconciliation checks.
npr_below_threshold_metadata.csv
    Input provenance and threshold definitions.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

IMPLEMENTATION_VERSION = "v2"
EXPERIMENT_NAME = "run-x-g02-prepare-npr-below-threshold-gmm-input"
NPR_METRIC = "file_npr_fun_space_by_token_weighted"
NPR_THRESHOLD = 1.571637
FILE_KEYS = ("snapshot_id", "relative_path", "file_sha256")
REPO_TIME_KEYS = ("repo_id", "time_index")


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


def normalize_keys(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    out = frame.copy()
    require_columns(out, REPO_TIME_KEYS, label)
    out["repo_id"] = pd.to_numeric(out["repo_id"], errors="raise").astype(int)
    out["time_index"] = pd.to_numeric(out["time_index"], errors="raise").astype(int)
    if out[list(REPO_TIME_KEYS)].isna().any().any():
        abort(f"{label} contains missing repo_id/time_index keys")
    return out


def extract_d03_primary(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if "sample_spec" not in data.columns:
        abort("D03 reference is missing sample_spec")
    data = data.loc[data["sample_spec"].astype(str) == "full_sample"].copy()

    threshold_column = next(
        (candidate for candidate in ("threshold", "threshold_value", "npr_threshold") if candidate in data.columns),
        None,
    )
    if threshold_column is None:
        abort("D03 reference does not expose an NPR threshold column")
    threshold_values = pd.to_numeric(data[threshold_column], errors="coerce")
    data = data.loc[np.isclose(threshold_values, NPR_THRESHOLD, atol=1e-12, rtol=0)].copy()
    if data.empty:
        abort("D03 primary-reference filter produced zero rows")

    if "selected_file_rows" not in data.columns:
        if "selected_file_count" in data.columns:
            data["selected_file_rows"] = data["selected_file_count"]
        else:
            abort("D03 reference is missing selected_file_rows/selected_file_count")

    require_columns(
        data,
        ["repo_id", "time_index", "selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"],
        "D03 reference",
    )
    data = normalize_keys(data, "D03 reference")
    for column in ("selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"):
        data[column] = pd.to_numeric(data[column], errors="raise")
    if data.duplicated(list(REPO_TIME_KEYS)).any():
        abort("D03 primary reference contains duplicate repo-month keys")
    return data[list(REPO_TIME_KEYS) + ["selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"]]


def compare_reproduction(reference: pd.DataFrame, reconstructed: pd.DataFrame) -> pd.DataFrame:
    check = reference.merge(
        reconstructed,
        on=list(REPO_TIME_KEYS),
        how="outer",
        suffixes=("_reference", "_new"),
        indicator=True,
        validate="one_to_one",
    )
    key_mismatch = int((check["_merge"] != "both").sum())
    row_mismatch = int((~np.isclose(
        check["selected_file_rows_reference"], check["selected_file_rows_new"],
        atol=0, rtol=0, equal_nan=False,
    )).sum())
    issue_mismatch = int((~np.isclose(
        check["selected_issue_total_reference"], check["selected_issue_total_new"],
        atol=1e-9, rtol=0, equal_nan=False,
    )).sum())
    log_mismatch = int((~np.isclose(
        check["log1p_selected_issue_total_reference"], check["log1p_selected_issue_total_new"],
        atol=1e-12, rtol=0, equal_nan=False,
    )).sum())
    status = "pass" if (key_mismatch + row_mismatch + issue_mismatch + log_mismatch) == 0 else "fail"
    return pd.DataFrame([{
        "reference": "D03_primary_NPR_above_threshold",
        "reference_rows": len(reference),
        "new_rows": len(reconstructed),
        "key_mismatches": key_mismatch,
        "selected_file_row_mismatches": row_mismatch,
        "selected_issue_total_mismatches": issue_mismatch,
        "log1p_mismatches": log_mismatch,
        "status": status,
    }])


def aggregate_selection(base: pd.DataFrame, mask: pd.Series, prefix: str) -> pd.DataFrame:
    selected = base.loc[mask, ["repo_id", "time_index", "sonar_issue_total"]].copy()
    if selected.empty:
        return pd.DataFrame(columns=["repo_id", "time_index", f"{prefix}_file_rows", f"{prefix}_issue_total"])
    return selected.groupby(["repo_id", "time_index"], as_index=False).agg(
        **{
            f"{prefix}_file_rows": ("sonar_issue_total", "size"),
            f"{prefix}_issue_total": ("sonar_issue_total", "sum"),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--d02-file", required=True, type=Path)
    parser.add_argument("--b06-file", required=True, type=Path)
    parser.add_argument("--d03-reference-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-d02-rows", type=int, default=510297)
    parser.add_argument("--expected-d02-unique-files", type=int, default=494592)
    parser.add_argument("--expected-b06-rows", type=int, default=1954)
    parser.add_argument("--expected-eligible-rows", type=int, default=204508)
    parser.add_argument("--expected-above-rows", type=int, default=13739)
    parser.add_argument("--expected-above-issue-stock", type=float, default=20306.0)
    parser.add_argument("--expected-below-rows", type=int, default=190769)
    args = parser.parse_args()

    for path in (args.d02_file, args.b06_file, args.d03_reference_file):
        if not path.is_file():
            abort(f"Required input does not exist: {path}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading D02 canonical file burden: {args.d02_file}")
    d02 = normalize_keys(read_table(args.d02_file), "D02")
    print(f"Reading B06 authoritative panel: {args.b06_file}")
    b06 = normalize_keys(read_table(args.b06_file), "B06")
    print(f"Reading D03 NPR reference: {args.d03_reference_file}")
    d03 = read_table(args.d03_reference_file)

    if len(d02) != args.expected_d02_rows:
        abort(f"D02 row mismatch: expected {args.expected_d02_rows}, observed {len(d02)}")
    if len(b06) != args.expected_b06_rows:
        abort(f"B06 row mismatch: expected {args.expected_b06_rows}, observed {len(b06)}")

    require_columns(d02, list(FILE_KEYS) + [NPR_METRIC, "sonar_issue_total"], "D02")
    require_columns(b06, ["python_file_count_manifest", "issue_total_py_sonarqube"], "B06")
    if b06.duplicated(list(REPO_TIME_KEYS)).any():
        abort("B06 contains duplicate repo-month keys")

    d02[NPR_METRIC] = pd.to_numeric(d02[NPR_METRIC], errors="coerce")
    d02["sonar_issue_total"] = pd.to_numeric(d02["sonar_issue_total"], errors="raise")
    b06["python_file_count_manifest"] = pd.to_numeric(b06["python_file_count_manifest"], errors="raise").astype(int)
    b06["issue_total_py_sonarqube"] = pd.to_numeric(b06["issue_total_py_sonarqube"], errors="raise")
    if d02["sonar_issue_total"].isna().any() or (d02["sonar_issue_total"] < 0).any():
        abort("D02 sonar_issue_total must be complete and non-negative")

    unique_d02_files = int(d02[list(FILE_KEYS)].drop_duplicates().shape[0])
    if unique_d02_files != args.expected_d02_unique_files:
        abort(
            f"D02 unique-file mismatch: expected {args.expected_d02_unique_files}, observed {unique_d02_files}"
        )

    eligible = d02[NPR_METRIC].notna() & np.isfinite(d02[NPR_METRIC])
    above = eligible & (d02[NPR_METRIC] > NPR_THRESHOLD)
    below = eligible & (d02[NPR_METRIC] <= NPR_THRESHOLD)
    unclassified = ~eligible
    all_files = pd.Series(True, index=d02.index, dtype=bool)

    observed_counts = {
        "eligible": int(eligible.sum()),
        "above": int(above.sum()),
        "below": int(below.sum()),
    }
    expected_counts = {
        "eligible": args.expected_eligible_rows,
        "above": args.expected_above_rows,
        "below": args.expected_below_rows,
    }
    for name, expected in expected_counts.items():
        if observed_counts[name] != expected:
            abort(f"{name} row mismatch: expected {expected}, observed {observed_counts[name]}")

    above_issue_stock = float(d02.loc[above, "sonar_issue_total"].sum())
    if not np.isclose(above_issue_stock, args.expected_above_issue_stock, atol=1e-9, rtol=0):
        abort(
            f"Above-threshold issue-stock mismatch: expected {args.expected_above_issue_stock}, observed {above_issue_stock}"
        )

    masks = {
        "all": all_files,
        "npr_eligible": eligible,
        "npr_above_threshold": above,
        "npr_below_threshold": below,
        "npr_unclassified": unclassified,
    }

    panel = b06[["repo_id", "time_index", "python_file_count_manifest", "issue_total_py_sonarqube"]].copy()
    for prefix, mask in masks.items():
        agg = aggregate_selection(d02, mask, prefix)
        panel = panel.merge(agg, on=list(REPO_TIME_KEYS), how="left", validate="one_to_one")
        panel[f"{prefix}_file_rows"] = panel[f"{prefix}_file_rows"].fillna(0).astype(int)
        panel[f"{prefix}_issue_total"] = panel[f"{prefix}_issue_total"].fillna(0.0)

    # Generic selected_* columns form the downstream run-x-g03 input contract.
    panel["selected_file_rows"] = panel["npr_below_threshold_file_rows"]
    panel["selected_issue_total"] = panel["npr_below_threshold_issue_total"]
    panel["log1p_selected_issue_total"] = np.log1p(panel["selected_issue_total"].astype(float))

    panel["npr_metric"] = NPR_METRIC
    panel["npr_threshold"] = NPR_THRESHOLD
    panel["npr_eligibility_rule"] = "finite_NPR"
    panel["npr_above_rule"] = "finite_NPR_GT_primary_threshold"
    panel["npr_below_rule"] = "finite_NPR_LE_primary_threshold"
    panel["npr_unclassified_rule"] = "NPR_missing_or_nonfinite"

    # Exact set algebra at every repo-month.
    eligible_count_identity = (
        panel["npr_eligible_file_rows"]
        == panel["npr_above_threshold_file_rows"] + panel["npr_below_threshold_file_rows"]
    )
    eligible_issue_identity = np.isclose(
        panel["npr_eligible_issue_total"],
        panel["npr_above_threshold_issue_total"] + panel["npr_below_threshold_issue_total"],
        atol=1e-9,
        rtol=0,
    )
    all_count_identity = (
        panel["all_file_rows"]
        == panel["npr_eligible_file_rows"] + panel["npr_unclassified_file_rows"]
    )
    all_issue_identity = np.isclose(
        panel["all_issue_total"],
        panel["npr_eligible_issue_total"] + panel["npr_unclassified_issue_total"],
        atol=1e-9,
        rtol=0,
    )
    b06_file_count_identity = panel["all_file_rows"] == panel["python_file_count_manifest"]
    b06_issue_identity = np.isclose(
        panel["all_issue_total"], panel["issue_total_py_sonarqube"], atol=1e-9, rtol=0
    )

    hard_checks = {
        "eligible_count_identity": eligible_count_identity,
        "eligible_issue_identity": eligible_issue_identity,
        "all_count_identity": all_count_identity,
        "all_issue_identity": all_issue_identity,
        "b06_file_count_identity": b06_file_count_identity,
    }
    failed = {name: int((~values).sum()) for name, values in hard_checks.items() if not bool(values.all())}
    if failed:
        abort(f"NPR threshold partition hard algebra failed: {failed}")

    # Reproduce the validated D03 high-NPR primary subset exactly.
    above_reconstructed = panel[[
        "repo_id", "time_index", "npr_above_threshold_file_rows", "npr_above_threshold_issue_total"
    ]].rename(columns={
        "npr_above_threshold_file_rows": "selected_file_rows",
        "npr_above_threshold_issue_total": "selected_issue_total",
    })
    above_reconstructed["log1p_selected_issue_total"] = np.log1p(above_reconstructed["selected_issue_total"])
    d03_reference = extract_d03_primary(d03)
    reproduction_audit = compare_reproduction(d03_reference, above_reconstructed)
    if not (reproduction_audit["status"] == "pass").all():
        abort("D03 primary NPR reproduction failed; G02 below-threshold panel is not trusted")

    def support_row(name: str, mask: pd.Series) -> dict[str, object]:
        subset = d02.loc[mask]
        return {
            "selection": name,
            "expanded_repo_month_file_rows": int(mask.sum()),
            "unique_historical_files": int(subset[list(FILE_KEYS)].drop_duplicates().shape[0]),
            "issue_stock": float(subset["sonar_issue_total"].sum()),
            "repo_months_with_files": int((panel[f"{name}_file_rows"] > 0).sum()),
            "repo_months_with_positive_issue_stock": int((panel[f"{name}_issue_total"] > 0).sum()),
        }

    support = pd.DataFrame([support_row(name, mask) for name, mask in masks.items()])

    b06_issue_delta = panel["issue_total_py_sonarqube"] - panel["all_issue_total"]
    b06_issue_mismatch_rows = int((~b06_issue_identity).sum())
    b06_issue_delta_sum = float(b06_issue_delta.sum())

    below_unique = int(d02.loc[below, list(FILE_KEYS)].drop_duplicates().shape[0])
    below_issue_stock = float(d02.loc[below, "sonar_issue_total"].sum())
    eligible_issue_stock = float(d02.loc[eligible, "sonar_issue_total"].sum())
    unclassified_issue_stock = float(d02.loc[unclassified, "sonar_issue_total"].sum())
    below_zero_share = float((panel["selected_issue_total"] == 0).mean())
    below_variation_repos = int(panel.groupby("repo_id")["log1p_selected_issue_total"].nunique().gt(1).sum())

    qc_rows = [
        ("repo_month_rows", len(panel), args.expected_b06_rows, len(panel) == args.expected_b06_rows),
        ("duplicate_repo_month_keys", int(panel.duplicated(list(REPO_TIME_KEYS)).sum()), 0, not panel.duplicated(list(REPO_TIME_KEYS)).any()),
        ("d02_unique_historical_files", unique_d02_files, args.expected_d02_unique_files, unique_d02_files == args.expected_d02_unique_files),
        ("npr_eligible_rows", int(eligible.sum()), args.expected_eligible_rows, int(eligible.sum()) == args.expected_eligible_rows),
        ("npr_above_threshold_rows", int(above.sum()), args.expected_above_rows, int(above.sum()) == args.expected_above_rows),
        ("npr_below_threshold_rows", int(below.sum()), args.expected_below_rows, int(below.sum()) == args.expected_below_rows),
        ("npr_above_threshold_issue_stock", above_issue_stock, args.expected_above_issue_stock, np.isclose(above_issue_stock, args.expected_above_issue_stock, atol=1e-9, rtol=0)),
        ("d03_primary_reproduction_failures", int((reproduction_audit["status"] != "pass").sum()), 0, (reproduction_audit["status"] == "pass").all()),
        ("eligible_count_identity_failures", int((~eligible_count_identity).sum()), 0, eligible_count_identity.all()),
        ("eligible_issue_identity_failures", int((~eligible_issue_identity).sum()), 0, eligible_issue_identity.all()),
        ("all_count_identity_failures", int((~all_count_identity).sum()), 0, all_count_identity.all()),
        ("all_issue_identity_failures", int((~all_issue_identity).sum()), 0, all_issue_identity.all()),
        ("b06_file_count_identity_failures", int((~b06_file_count_identity).sum()), 0, b06_file_count_identity.all()),
    ]
    qc = pd.DataFrame([
        {"check": name, "observed": observed, "expected": expected, "status": "pass" if status else "fail"}
        for name, observed, expected, status in qc_rows
    ])
    if (qc["status"] == "fail").any():
        abort("G02 hard QC failed: " + ", ".join(qc.loc[qc["status"] == "fail", "check"].astype(str)))

    output_panel = args.output_dir / "npr_below_threshold_repo_month_panel.csv.gz"
    output_support = args.output_dir / "npr_below_threshold_support.csv"
    output_repro = args.output_dir / "npr_below_threshold_reproduction_audit.csv"
    output_qc = args.output_dir / "npr_below_threshold_qc.csv"
    output_meta = args.output_dir / "npr_below_threshold_metadata.csv"

    panel.to_csv(output_panel, index=False, compression="gzip")
    support.to_csv(output_support, index=False)
    reproduction_audit.to_csv(output_repro, index=False)
    qc.to_csv(output_qc, index=False)

    metadata = pd.DataFrame([
        ("run", "experiment", EXPERIMENT_NAME),
        ("run", "implementation_version", IMPLEMENTATION_VERSION),
        ("input", "d02_file", str(args.d02_file)),
        ("input", "d02_sha256", sha256_file(args.d02_file)),
        ("input", "b06_file", str(args.b06_file)),
        ("input", "b06_sha256", sha256_file(args.b06_file)),
        ("input", "d03_reference_file", str(args.d03_reference_file)),
        ("input", "d03_reference_sha256", sha256_file(args.d03_reference_file)),
        ("definition", "npr_metric", NPR_METRIC),
        ("definition", "npr_threshold", NPR_THRESHOLD),
        ("definition", "eligibility_rule", "finite NPR"),
        ("definition", "above_rule", "finite NPR > 1.571637"),
        ("definition", "below_rule", "finite NPR <= 1.571637"),
        ("definition", "unclassified_rule", "NPR missing or non-finite; excluded from G02 subset"),
        ("output", "downstream_experiment", "run-x-g03"),
        ("output", "g03_quality_column", "log1p_selected_issue_total"),
        ("output", "g03_file_count_column", "selected_file_rows"),
        ("output", "g03_issue_count_column", "selected_issue_total"),
        ("audit", "b06_issue_total_policy", "audit-only because D02 canonical alias policy differs from B06 whole-snapshot aggregation"),
        ("audit", "b06_issue_mismatch_repo_months", b06_issue_mismatch_rows),
        ("audit", "b06_minus_d02_issue_stock", b06_issue_delta_sum),
        ("support", "eligible_issue_stock", eligible_issue_stock),
        ("support", "below_issue_stock", below_issue_stock),
        ("support", "unclassified_issue_stock", unclassified_issue_stock),
        ("support", "below_unique_historical_files", below_unique),
        ("support", "below_zero_burden_repo_month_share", below_zero_share),
        ("support", "below_within_quality_variation_repositories", below_variation_repos),
    ], columns=["section", "metric", "value"])
    metadata.to_csv(output_meta, index=False)

    print("run-x-g02 NPR below-threshold GMM input: PASS")
    print(f"All expanded file rows: {len(d02)}")
    print(f"Finite-NPR eligible rows: {int(eligible.sum())}")
    print(f"Above-threshold rows: {int(above.sum())}")
    print(f"Below-threshold rows: {int(below.sum())}")
    print(f"Unclassified rows: {int(unclassified.sum())}")
    print(f"Above-threshold issue stock: {above_issue_stock:.0f}")
    print(f"Below-threshold issue stock: {below_issue_stock:.0f}")
    print(f"Below-threshold unique historical files: {below_unique}")
    print(f"Below-threshold zero-burden repo-month share: {below_zero_share:.6f}")
    print(f"Below-threshold within-quality-variation repositories: {below_variation_repos}")
    print(f"B06-D02 issue-stock delta: {b06_issue_delta_sum:.0f} across {b06_issue_mismatch_rows} repo-months (audit-only)")
    print(f"Output panel: {output_panel}")


if __name__ == "__main__":
    main()
