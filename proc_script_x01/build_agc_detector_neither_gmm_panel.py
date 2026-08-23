#!/usr/bin/env python3
"""Build the neither-selected Python quality panel for run-x-g01.

This experiment complements the validated NPR/ML union analysis. It defines
an exact historical-file complement over the canonical Python file universe:

    NPR selected: finite file_npr_fun_space_by_token_weighted > 1.571637
    ML selected: scored file_ml_agc_share_space_by_token_weighted > 0.50
    Union:        NPR selected OR ML selected
    Neither:      NOT Union

The complement is formed at exact historical file identity before SonarQube
issue burden is aggregated. Files in the neither-selected set are therefore
files selected by neither detector; they must not be interpreted as verified
human-written or non-AGC files.

Inputs
------
D02:
    Canonical repo-month/file SonarQube issue burden and NPR file metric.
A04:
    ML file-score table at exact snapshot/file identity.
B06:
    Authoritative 1,954-row repo-month panel. It supplies the all-Python file
    count and all-Python SonarQube issue burden used for complement algebra QC.
D03 reference:
    NPR-primary repo-month panel used only for exact reproduction QC.
D05 reference:
    ML-primary repo-month panel used only for exact reproduction QC.

Outputs
-------
agc_detector_neither_repo_month_panel.csv.gz
    Zero-inclusive 1,954-row repo-month panel with detector support and the
    neither-selected issue burden used by the G01 GMM.
agc_detector_neither_support.csv
    Global support for all, NPR, ML, intersection, union, and neither sets.
agc_detector_neither_reproduction_audit.csv
    Exact D03/D05 detector-only reproduction checks.
agc_detector_neither_join_audit.csv
    Exact D02/A04 historical-file identity reconciliation checks.
agc_detector_neither_qc.csv
    Hard set-algebra and B06 reconciliation checks.
agc_detector_neither_metadata.csv
    Input provenance and selection/aggregation definitions.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

IMPLEMENTATION_VERSION = "v3"
EXPERIMENT_NAME = "run-x-g01-dynamic-panel-gmm-agc-neither"
NPR_METRIC = "file_npr_fun_space_by_token_weighted"
NPR_THRESHOLD = 1.571637
ML_METRIC = "file_ml_agc_share_space_by_token_weighted"
ML_THRESHOLD = 0.50
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


def infer_ml_scored_mask(frame: pd.DataFrame) -> pd.Series:
    if "ml_fun_status" in frame.columns:
        return frame["ml_fun_status"].astype(str).eq("scored")
    if "file_ml_fun_status" in frame.columns:
        return frame["file_ml_fun_status"].astype(str).eq("scored")
    return pd.to_numeric(frame[ML_METRIC], errors="coerce").notna()


def extract_reference(
    frame: pd.DataFrame,
    label: str,
    filters: dict[str, object],
    threshold_filter: float | None = None,
) -> pd.DataFrame:
    data = frame.copy()
    for column, value in filters.items():
        if column not in data.columns:
            abort(f"{label} is missing filter column {column}")
        data = data.loc[data[column].astype(str) == str(value)].copy()
    if threshold_filter is not None:
        threshold_column = None
        for candidate in ("threshold", "threshold_value", "npr_threshold"):
            if candidate in data.columns:
                threshold_column = candidate
                break
        if threshold_column is None:
            abort(f"{label} does not expose an NPR threshold column")
        values = pd.to_numeric(data[threshold_column], errors="coerce")
        data = data.loc[np.isclose(values, threshold_filter, atol=1e-12, rtol=0)].copy()
    if data.empty:
        abort(f"{label} reference filter produced zero rows")

    if "selected_file_rows" not in data.columns:
        if "selected_file_count" in data.columns:
            data["selected_file_rows"] = data["selected_file_count"]
        else:
            abort(f"{label} is missing selected_file_rows/selected_file_count")
    require_columns(
        data,
        ["repo_id", "time_index", "selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"],
        label,
    )
    data = normalize_keys(data, label)
    for column in ("selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"):
        data[column] = pd.to_numeric(data[column], errors="raise")
    if data.duplicated(list(REPO_TIME_KEYS)).any():
        abort(f"{label} reference contains duplicate repo-month keys")
    return data[list(REPO_TIME_KEYS) + ["selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"]]


def compare_reproduction(
    reference: pd.DataFrame,
    reconstructed: pd.DataFrame,
    detector: str,
) -> pd.DataFrame:
    check = reference.merge(
        reconstructed[list(REPO_TIME_KEYS) + ["selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"]],
        on=list(REPO_TIME_KEYS),
        how="outer",
        suffixes=("_reference", "_new"),
        indicator=True,
        validate="one_to_one",
    )
    key_mismatch = int((check["_merge"] != "both").sum())
    row_mismatch = int(
        (~np.isclose(check["selected_file_rows_reference"], check["selected_file_rows_new"], atol=0, rtol=0, equal_nan=False)).sum()
    )
    issue_mismatch = int(
        (~np.isclose(check["selected_issue_total_reference"], check["selected_issue_total_new"], atol=1e-9, rtol=0, equal_nan=False)).sum()
    )
    log_mismatch = int(
        (~np.isclose(check["log1p_selected_issue_total_reference"], check["log1p_selected_issue_total_new"], atol=1e-12, rtol=0, equal_nan=False)).sum()
    )
    return pd.DataFrame(
        [{
            "detector": detector,
            "reference_rows": len(reference),
            "new_rows": len(reconstructed),
            "key_mismatches": key_mismatch,
            "selected_file_row_mismatches": row_mismatch,
            "selected_issue_total_mismatches": issue_mismatch,
            "log1p_mismatches": log_mismatch,
            "status": "pass" if (key_mismatch + row_mismatch + issue_mismatch + log_mismatch) == 0 else "fail",
        }]
    )


def aggregate_selection(
    base: pd.DataFrame,
    mask: pd.Series,
    issue_column: str,
    prefix: str,
) -> pd.DataFrame:
    selected = base.loc[mask, ["repo_id", "time_index", issue_column]].copy()
    if selected.empty:
        return pd.DataFrame(columns=["repo_id", "time_index", f"{prefix}_file_rows", f"{prefix}_issue_total"])
    return selected.groupby(["repo_id", "time_index"], as_index=False).agg(
        **{
            f"{prefix}_file_rows": (issue_column, "size"),
            f"{prefix}_issue_total": (issue_column, "sum"),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--d02-file", required=True, type=Path)
    parser.add_argument("--a04-file", required=True, type=Path)
    parser.add_argument("--b06-file", required=True, type=Path)
    parser.add_argument("--d03-reference-file", required=True, type=Path)
    parser.add_argument("--d05-reference-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-d02-rows", type=int, default=510297)
    parser.add_argument("--expected-a04-rows", type=int, default=494592)
    parser.add_argument("--expected-b06-rows", type=int, default=1954)
    parser.add_argument("--expected-neither-expanded-rows", type=int, default=456852)
    parser.add_argument("--expected-neither-unique-files", type=int, default=443390)
    parser.add_argument("--expected-union-expanded-rows", type=int, default=53445)
    parser.add_argument("--expected-union-unique-files", type=int, default=51202)
    parser.add_argument("--expected-union-issue-stock", type=float, default=64901.0)
    args = parser.parse_args()

    for path in (args.d02_file, args.a04_file, args.b06_file, args.d03_reference_file, args.d05_reference_file):
        if not path.is_file():
            abort(f"Required input does not exist: {path}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading D02 canonical file burden: {args.d02_file}")
    d02 = normalize_keys(read_table(args.d02_file), "D02")
    print(f"Reading A04 ML file scores: {args.a04_file}")
    a04 = read_table(args.a04_file)
    print(f"Reading B06 authoritative panel: {args.b06_file}")
    b06 = normalize_keys(read_table(args.b06_file), "B06")
    print(f"Reading D03 NPR reference: {args.d03_reference_file}")
    d03 = read_table(args.d03_reference_file)
    print(f"Reading D05 ML reference: {args.d05_reference_file}")
    d05 = read_table(args.d05_reference_file)

    if len(d02) != args.expected_d02_rows:
        abort(f"D02 row mismatch: expected {args.expected_d02_rows}, observed {len(d02)}")
    if len(a04) != args.expected_a04_rows:
        abort(f"A04 row mismatch: expected {args.expected_a04_rows}, observed {len(a04)}")
    if len(b06) != args.expected_b06_rows:
        abort(f"B06 row mismatch: expected {args.expected_b06_rows}, observed {len(b06)}")

    require_columns(d02, list(FILE_KEYS) + [NPR_METRIC, "sonar_issue_total"], "D02")
    require_columns(a04, list(FILE_KEYS) + [ML_METRIC], "A04")
    require_columns(b06, ["python_file_count_manifest", "issue_total_py_sonarqube"], "B06")
    if a04.duplicated(list(FILE_KEYS)).any():
        abort("A04 must contain one row per exact historical file identity")
    if b06.duplicated(list(REPO_TIME_KEYS)).any():
        abort("B06 contains duplicate repo-month keys")

    d02["sonar_issue_total"] = pd.to_numeric(d02["sonar_issue_total"], errors="raise")
    d02[NPR_METRIC] = pd.to_numeric(d02[NPR_METRIC], errors="coerce")
    b06["python_file_count_manifest"] = pd.to_numeric(b06["python_file_count_manifest"], errors="raise").astype(int)
    b06["issue_total_py_sonarqube"] = pd.to_numeric(b06["issue_total_py_sonarqube"], errors="raise")
    if d02["sonar_issue_total"].isna().any() or (d02["sonar_issue_total"] < 0).any():
        abort("D02 sonar_issue_total must be complete and non-negative")

    a04_small_columns = list(FILE_KEYS) + [ML_METRIC]
    for optional in ("ml_fun_status", "file_ml_fun_status"):
        if optional in a04.columns:
            a04_small_columns.append(optional)
    a04_small = a04[a04_small_columns].copy()
    a04_small[ML_METRIC] = pd.to_numeric(a04_small[ML_METRIC], errors="coerce")

    merged = d02.merge(a04_small, on=list(FILE_KEYS), how="left", validate="many_to_one", indicator=True)
    d02_only_rows = int((merged["_merge"] == "left_only").sum())
    joined_rows = int((merged["_merge"] == "both").sum())
    merged.drop(columns=["_merge"], inplace=True)

    unique_d02_files = d02[list(FILE_KEYS)].drop_duplicates()
    unique_a04_files = a04[list(FILE_KEYS)].drop_duplicates()
    file_universe = unique_d02_files.merge(unique_a04_files, on=list(FILE_KEYS), how="outer", indicator=True)
    d02_unique_only = int((file_universe["_merge"] == "left_only").sum())
    a04_unique_only = int((file_universe["_merge"] == "right_only").sum())
    exact_unique_files = int((file_universe["_merge"] == "both").sum())
    if d02_only_rows != 0 or d02_unique_only != 0 or a04_unique_only != 0:
        abort(
            "D02 and A04 exact historical-file universes do not reconcile: "
            f"expanded_d02_only={d02_only_rows}, unique_d02_only={d02_unique_only}, unique_a04_only={a04_unique_only}"
        )

    ml_scored = infer_ml_scored_mask(merged)
    npr_eligible = merged[NPR_METRIC].notna() & np.isfinite(merged[NPR_METRIC])
    npr_selected = npr_eligible & (merged[NPR_METRIC] > NPR_THRESHOLD)
    ml_selected = ml_scored & (merged[ML_METRIC] > ML_THRESHOLD)
    intersection_selected = npr_selected & ml_selected
    npr_only = npr_selected & ~ml_selected
    ml_only = ml_selected & ~npr_selected
    union_selected = npr_selected | ml_selected
    neither_selected = ~union_selected
    all_files = pd.Series(True, index=merged.index, dtype=bool)

    category_masks = {
        "all": all_files,
        "npr_selected": npr_selected,
        "ml_selected": ml_selected,
        "intersection_selected": intersection_selected,
        "npr_only": npr_only,
        "ml_only": ml_only,
        "union_selected": union_selected,
        "neither_selected": neither_selected,
    }

    panel = b06[["repo_id", "time_index", "python_file_count_manifest", "issue_total_py_sonarqube"]].copy()
    for prefix, mask in category_masks.items():
        agg = aggregate_selection(merged, mask, "sonar_issue_total", prefix)
        panel = panel.merge(agg, on=list(REPO_TIME_KEYS), how="left", validate="one_to_one")
        panel[f"{prefix}_file_rows"] = panel[f"{prefix}_file_rows"].fillna(0).astype(int)
        panel[f"{prefix}_issue_total"] = panel[f"{prefix}_issue_total"].fillna(0.0)

    # Generic selected_* columns are consumed by the shared GMM specification.
    panel["selected_file_rows"] = panel["neither_selected_file_rows"]
    panel["selected_issue_total"] = panel["neither_selected_issue_total"]
    panel["log1p_selected_issue_total"] = np.log1p(panel["selected_issue_total"].astype(float))
    # Persist both detector-set rules in the row-level panel so the downstream R
    # model can verify that it is fitting the intended complement definition.
    panel["detector_union_rule"] = "NPR_primary_OR_ML_primary"
    panel["detector_neither_rule"] = "NOT(NPR_primary_OR_ML_primary)"
    panel["npr_metric"] = NPR_METRIC
    panel["npr_operator"] = ">"
    panel["npr_threshold"] = NPR_THRESHOLD
    panel["ml_metric"] = ML_METRIC
    panel["ml_operator"] = ">"
    panel["ml_threshold"] = ML_THRESHOLD

    # Detector set algebra at every repo-month.
    union_count_identity = (
        panel["union_selected_file_rows"]
        == panel["npr_selected_file_rows"] + panel["ml_selected_file_rows"] - panel["intersection_selected_file_rows"]
    )
    union_disjoint_count_identity = (
        panel["union_selected_file_rows"]
        == panel["npr_only_file_rows"] + panel["ml_only_file_rows"] + panel["intersection_selected_file_rows"]
    )
    union_issue_identity = np.isclose(
        panel["union_selected_issue_total"],
        panel["npr_selected_issue_total"] + panel["ml_selected_issue_total"] - panel["intersection_selected_issue_total"],
        atol=1e-9,
        rtol=0,
    )
    union_disjoint_issue_identity = np.isclose(
        panel["union_selected_issue_total"],
        panel["npr_only_issue_total"] + panel["ml_only_issue_total"] + panel["intersection_selected_issue_total"],
        atol=1e-9,
        rtol=0,
    )
    complement_count_identity = panel["all_file_rows"] == panel["union_selected_file_rows"] + panel["neither_selected_file_rows"]
    complement_issue_identity = np.isclose(
        panel["all_issue_total"],
        panel["union_selected_issue_total"] + panel["neither_selected_issue_total"],
        atol=1e-9,
        rtol=0,
    )

    # Reconcile the canonical file-level all-Python totals to B06 at each month.
    b06_file_count_identity = panel["all_file_rows"] == panel["python_file_count_manifest"]
    b06_issue_identity = np.isclose(
        panel["all_issue_total"], panel["issue_total_py_sonarqube"], atol=1e-9, rtol=0
    )

    # Hard set-algebra checks are defined on the canonical D02/A04 file universe.
    # B06 file counts must still reconcile exactly because both lineages contain the
    # same repo-month Python-file manifest. B06 issue totals are audited separately:
    # D02 intentionally uses canonical file paths after the D02-a/D02-b alias audit,
    # whereas B06 is a whole-snapshot SonarQube aggregate. Known filesystem-alias
    # duplicates therefore must not be reintroduced into the detector complement.
    hard_identity_checks = {
        "union_count_identity": union_count_identity,
        "union_disjoint_count_identity": union_disjoint_count_identity,
        "union_issue_identity": union_issue_identity,
        "union_disjoint_issue_identity": union_disjoint_issue_identity,
        "complement_count_identity": complement_count_identity,
        "complement_issue_identity": complement_issue_identity,
        "b06_file_count_identity": b06_file_count_identity,
    }
    failed_hard_identities = {
        name: int((~values).sum())
        for name, values in hard_identity_checks.items()
        if not bool(values.all())
    }
    if failed_hard_identities:
        abort(f"Detector/complement hard algebra failed: {failed_hard_identities}")

    b06_issue_delta = panel["issue_total_py_sonarqube"] - panel["all_issue_total"]
    b06_issue_mismatch_rows = int((~b06_issue_identity).sum())
    b06_issue_delta_sum = float(b06_issue_delta.sum())
    b06_issue_delta_abs_sum = float(b06_issue_delta.abs().sum())

    # Reproduce the previously validated detector-only panels before trusting G01.
    npr_reconstructed = panel[["repo_id", "time_index", "npr_selected_file_rows", "npr_selected_issue_total"]].rename(
        columns={"npr_selected_file_rows": "selected_file_rows", "npr_selected_issue_total": "selected_issue_total"}
    )
    npr_reconstructed["log1p_selected_issue_total"] = np.log1p(npr_reconstructed["selected_issue_total"])
    ml_reconstructed = panel[["repo_id", "time_index", "ml_selected_file_rows", "ml_selected_issue_total"]].rename(
        columns={"ml_selected_file_rows": "selected_file_rows", "ml_selected_issue_total": "selected_issue_total"}
    )
    ml_reconstructed["log1p_selected_issue_total"] = np.log1p(ml_reconstructed["selected_issue_total"])

    npr_reference = extract_reference(d03, "D03", {"sample_spec": "full_sample"}, threshold_filter=NPR_THRESHOLD)
    ml_reference = extract_reference(d05, "D05", {"sample_spec": "full_sample", "mapping_spec": "all_ml_files"})
    npr_audit = compare_reproduction(npr_reference, npr_reconstructed, "NPR")
    ml_audit = compare_reproduction(ml_reference, ml_reconstructed, "ML")
    reproduction_audit = pd.concat([npr_audit, ml_audit], ignore_index=True)
    if not (reproduction_audit["status"] == "pass").all():
        abort("Detector-only reproduction failed; G01 neither panel is not trusted")

    def global_support_row(name: str, mask: pd.Series) -> dict[str, object]:
        selected = merged.loc[mask]
        return {
            "selection": name,
            "expanded_repo_month_file_rows": int(mask.sum()),
            "unique_historical_files": int(selected[list(FILE_KEYS)].drop_duplicates().shape[0]),
            "issue_stock": float(selected["sonar_issue_total"].sum()),
            "repo_months_with_selected_files": int((panel[f"{name}_file_rows"] > 0).sum()),
            "repo_months_with_positive_issue_stock": int((panel[f"{name}_issue_total"] > 0).sum()),
        }

    support = pd.DataFrame([global_support_row(name, mask) for name, mask in category_masks.items()])
    intersection_count = int(intersection_selected.sum())
    union_count = int(union_selected.sum())
    neither_count = int(neither_selected.sum())
    npr_count = int(npr_selected.sum())
    ml_count = int(ml_selected.sum())
    jaccard = intersection_count / union_count if union_count else np.nan
    overlap_coefficient = intersection_count / min(npr_count, ml_count) if min(npr_count, ml_count) else np.nan
    support["jaccard_npr_ml"] = jaccard
    support["overlap_coefficient_npr_ml"] = overlap_coefficient

    neither_unique = int(merged.loc[neither_selected, list(FILE_KEYS)].drop_duplicates().shape[0])
    union_unique = int(merged.loc[union_selected, list(FILE_KEYS)].drop_duplicates().shape[0])
    neither_issue_stock = float(merged.loc[neither_selected, "sonar_issue_total"].sum())
    union_issue_stock = float(merged.loc[union_selected, "sonar_issue_total"].sum())
    all_issue_stock = float(merged["sonar_issue_total"].sum())
    neither_zero_share = float((panel["selected_issue_total"] == 0).mean())
    neither_within_variation_repos = int(
        panel.groupby("repo_id")["log1p_selected_issue_total"].nunique().gt(1).sum()
    )

    join_audit = pd.DataFrame(
        [
            {"check": "d02_rows", "observed": len(d02), "expected": args.expected_d02_rows, "status": "pass" if len(d02) == args.expected_d02_rows else "fail"},
            {"check": "a04_rows", "observed": len(a04), "expected": args.expected_a04_rows, "status": "pass" if len(a04) == args.expected_a04_rows else "fail"},
            {"check": "expanded_d02_rows_joined_to_a04", "observed": joined_rows, "expected": len(d02), "status": "pass" if joined_rows == len(d02) else "fail"},
            {"check": "expanded_d02_rows_missing_a04", "observed": d02_only_rows, "expected": 0, "status": "pass" if d02_only_rows == 0 else "fail"},
            {"check": "unique_d02_files", "observed": len(unique_d02_files), "expected": args.expected_a04_rows, "status": "pass" if len(unique_d02_files) == args.expected_a04_rows else "fail"},
            {"check": "unique_a04_files", "observed": len(unique_a04_files), "expected": args.expected_a04_rows, "status": "pass" if len(unique_a04_files) == args.expected_a04_rows else "fail"},
            {"check": "exact_unique_file_matches", "observed": exact_unique_files, "expected": args.expected_a04_rows, "status": "pass" if exact_unique_files == args.expected_a04_rows else "fail"},
            {"check": "unique_d02_only", "observed": d02_unique_only, "expected": 0, "status": "pass" if d02_unique_only == 0 else "fail"},
            {"check": "unique_a04_only", "observed": a04_unique_only, "expected": 0, "status": "pass" if a04_unique_only == 0 else "fail"},
        ]
    )

    qc_rows = [
        ("repo_month_rows", len(panel), args.expected_b06_rows),
        ("duplicate_repo_month_keys", int(panel.duplicated(list(REPO_TIME_KEYS)).sum()), 0),
        ("npr_reference_reproduction_failures", int((npr_audit["status"] != "pass").sum()), 0),
        ("ml_reference_reproduction_failures", int((ml_audit["status"] != "pass").sum()), 0),
        ("union_count_identity_failures", int((~union_count_identity).sum()), 0),
        ("union_disjoint_count_identity_failures", int((~union_disjoint_count_identity).sum()), 0),
        ("union_issue_identity_failures", int((~union_issue_identity).sum()), 0),
        ("union_disjoint_issue_identity_failures", int((~union_disjoint_issue_identity).sum()), 0),
        ("all_equals_union_plus_neither_count_failures", int((~complement_count_identity).sum()), 0),
        ("all_equals_union_plus_neither_issue_failures", int((~complement_issue_identity).sum()), 0),
        ("d02_all_vs_b06_file_count_failures", int((~b06_file_count_identity).sum()), 0),
        ("neither_expanded_rows", neither_count, args.expected_neither_expanded_rows),
        ("neither_unique_files", neither_unique, args.expected_neither_unique_files),
        ("union_expanded_rows", union_count, args.expected_union_expanded_rows),
        ("union_unique_files", union_unique, args.expected_union_unique_files),
        ("union_issue_stock", union_issue_stock, args.expected_union_issue_stock),
        ("neither_issue_stock_matches_d02_all_minus_union", neither_issue_stock, all_issue_stock - union_issue_stock),
        ("negative_selected_issue_rows", int((panel["selected_issue_total"] < 0).sum()), 0),
        ("log1p_recompute_mismatches", int((~np.isclose(panel["log1p_selected_issue_total"], np.log1p(panel["selected_issue_total"]), atol=1e-12, rtol=0)).sum()), 0),
    ]
    qc = pd.DataFrame(
        [
            {"check": name, "observed": observed, "expected": expected, "status": "pass" if observed == expected else "fail"}
            for name, observed, expected in qc_rows
        ]
    )

    # B06 issue-total reconciliation is intentionally audit-only. The G01
    # complement is defined on the canonical D02/A04 file universe, and D02
    # excludes confirmed duplicate filesystem-alias issue paths.
    b06_issue_audit = pd.DataFrame(
        [
            {
                "check": "d02_all_vs_b06_issue_total_mismatch_rows",
                "observed": b06_issue_mismatch_rows,
                "expected": "audit_only",
                "status": "pass",
            },
            {
                "check": "d02_all_vs_b06_issue_total_delta_sum",
                "observed": b06_issue_delta_sum,
                "expected": "audit_only",
                "status": "pass",
            },
            {
                "check": "d02_all_vs_b06_issue_total_abs_delta_sum",
                "observed": b06_issue_delta_abs_sum,
                "expected": "audit_only",
                "status": "pass",
            },
            {
                "check": "d02_canonical_all_issue_stock",
                "observed": all_issue_stock,
                "expected": "derived_from_D02",
                "status": "pass",
            },
            {
                "check": "b06_whole_snapshot_issue_stock",
                "observed": float(panel["issue_total_py_sonarqube"].sum()),
                "expected": "audit_only",
                "status": "pass",
            },
        ]
    )
    qc = pd.concat([qc, b06_issue_audit], ignore_index=True)
    if (qc["status"] != "pass").any() or (join_audit["status"] != "pass").any():
        failures = qc.loc[qc["status"] != "pass", ["check", "observed", "expected"]].to_dict("records")
        abort(f"G01 neither builder hard QC failed: {failures}")

    metadata = pd.DataFrame(
        [
            ("run", "experiment", EXPERIMENT_NAME),
            ("run", "implementation_version", IMPLEMENTATION_VERSION),
            ("input", "d02_file", str(args.d02_file)),
            ("input", "d02_sha256", sha256_file(args.d02_file)),
            ("input", "a04_file", str(args.a04_file)),
            ("input", "a04_sha256", sha256_file(args.a04_file)),
            ("input", "b06_file", str(args.b06_file)),
            ("input", "b06_sha256", sha256_file(args.b06_file)),
            ("input", "d03_reference_file", str(args.d03_reference_file)),
            ("input", "d03_reference_sha256", sha256_file(args.d03_reference_file)),
            ("input", "d05_reference_file", str(args.d05_reference_file)),
            ("input", "d05_reference_sha256", sha256_file(args.d05_reference_file)),
            ("definition", "npr_metric", NPR_METRIC),
            ("definition", "npr_operator", ">"),
            ("definition", "npr_threshold", NPR_THRESHOLD),
            ("definition", "ml_metric", ML_METRIC),
            ("definition", "ml_operator", ">"),
            ("definition", "ml_threshold", ML_THRESHOLD),
            ("definition", "union_rule", "NPR_selected OR ML_selected"),
            ("definition", "neither_rule", "NOT(NPR_selected OR ML_selected)"),
            ("definition", "set_identity", "All = Union disjoint-union Neither"),
            ("definition", "file_identity", "snapshot_id + relative_path + file_sha256"),
            ("definition", "interpretation", "neither-selected files are not equivalent to verified HWC/non-AGC files"),
            ("definition", "quality_semantics", "unresolved SonarQube issue stock among files selected by neither detector"),
            ("definition", "all_universe", "canonical D02/A04 historical Python file universe"),
            ("definition", "b06_issue_reconciliation_policy", "audit-only because D02 canonicalizes confirmed duplicate filesystem-alias issue paths"),
            ("support", "d02_canonical_all_issue_stock", all_issue_stock),
            ("support", "b06_whole_snapshot_issue_stock", float(panel["issue_total_py_sonarqube"].sum())),
            ("support", "b06_minus_d02_issue_stock", b06_issue_delta_sum),
            ("support", "b06_issue_mismatch_repo_months", b06_issue_mismatch_rows),
            ("support", "neither_zero_issue_repo_month_share", neither_zero_share),
            ("support", "neither_repositories_with_within_quality_variation", neither_within_variation_repos),
            ("support", "jaccard_npr_ml", jaccard),
            ("support", "overlap_coefficient_npr_ml", overlap_coefficient),
        ],
        columns=["section", "metric", "value"],
    )

    panel_path = args.output_dir / "agc_detector_neither_repo_month_panel.csv.gz"
    support_path = args.output_dir / "agc_detector_neither_support.csv"
    reproduction_path = args.output_dir / "agc_detector_neither_reproduction_audit.csv"
    join_path = args.output_dir / "agc_detector_neither_join_audit.csv"
    qc_path = args.output_dir / "agc_detector_neither_qc.csv"
    metadata_path = args.output_dir / "agc_detector_neither_metadata.csv"

    panel.to_csv(panel_path, index=False, compression="gzip")
    support.to_csv(support_path, index=False)
    reproduction_audit.to_csv(reproduction_path, index=False)
    join_audit.to_csv(join_path, index=False)
    qc.to_csv(qc_path, index=False)
    metadata.to_csv(metadata_path, index=False)

    print("G01 detector-neither panel: PASS")
    print(f"All expanded file rows: {len(merged)}")
    print(f"D02 canonical all issue stock: {all_issue_stock:.0f}")
    print(f"B06 whole-snapshot issue stock: {float(panel['issue_total_py_sonarqube'].sum()):.0f}")
    print(f"B06-D02 issue-stock delta: {b06_issue_delta_sum:.0f} across {b06_issue_mismatch_rows} repo-months (audit-only)")
    print(f"NPR primary selected expanded file rows: {npr_count}")
    print(f"ML primary selected expanded file rows: {ml_count}")
    print(f"Intersection expanded file rows: {intersection_count}")
    print(f"Union expanded file rows: {union_count}")
    print(f"Neither expanded file rows: {neither_count}")
    print(f"Neither unique historical files: {neither_unique}")
    print(f"Neither issue stock: {neither_issue_stock:.0f}")
    print(f"Neither zero-burden repo-month share: {neither_zero_share:.6f}")
    print(f"Neither within-quality-variation repositories: {neither_within_variation_repos}")
    print(f"Output panel: {panel_path}")


if __name__ == "__main__":
    main()
