#!/usr/bin/env python3
"""Build the NPR-intersection-ML AGC-like file quality panel for run-x-e05.

This script creates an inclusive detector-localized file set using the frozen
primary definitions from the existing NPR and ML analyses:

    NPR selected: finite file_npr_fun_space_by_token_weighted > 1.571637
    ML selected: scored file_ml_agc_share_space_by_token_weighted > 0.50
    Intersection selected: NPR selected AND ML selected

The intersection is formed at exact historical file identity before SonarQube
issue burden is aggregated. Only files selected by both frozen detectors enter
the E05 localized quality burden.

Inputs
------
D02:
    Canonical repo-month/file SonarQube burden table with the frozen NPR file
    metric. D02 is the authoritative file-level quality table.
A04:
    Frozen ML file-score table at snapshot/file level.
B06:
    Authoritative 1,954-row repo-month panel, used to guarantee a complete
    zero-inclusive repo-month output.
D03 reference:
    Frozen NPR threshold repo-month panel. The script reconstructs the primary
    NPR-only selection and requires exact repo-month reproduction.
D05 reference:
    Frozen ML repo-month panel. The script reconstructs the primary ML-only
    selection and requires exact repo-month reproduction.

Outputs
-------
agc_detector_intersection_repo_month_panel.csv.gz
    One row per B06 repo-month with detector-specific overlap support, intersection unresolved issue burden, and
    log1p intersection burden used by E05 GMM.
agc_detector_intersection_support.csv
    Global support and overlap statistics for NPR-only, ML-only, intersection,
    and union selections.
agc_detector_intersection_reproduction_audit.csv
    Exact D03 NPR-primary and D05 ML-primary reproduction checks.
agc_detector_intersection_join_audit.csv
    Exact file-identity join diagnostics.
agc_detector_intersection_qc.csv
    Hard implementation checks.
agc_detector_intersection_metadata.csv
    Frozen selection and aggregation definitions.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

IMPLEMENTATION_VERSION = "v1"
EXPERIMENT_NAME = "run-x-e05-dynamic-panel-gmm-agc-intersection"
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
) -> tuple[pd.DataFrame, pd.DataFrame]:
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
    audit = pd.DataFrame(
        [
            {
                "detector": detector,
                "reference_rows": len(reference),
                "new_rows": len(reconstructed),
                "key_mismatches": key_mismatch,
                "selected_file_row_mismatches": row_mismatch,
                "selected_issue_total_mismatches": issue_mismatch,
                "log1p_mismatches": log_mismatch,
                "status": "pass" if (key_mismatch + row_mismatch + issue_mismatch + log_mismatch) == 0 else "fail",
            }
        ]
    )
    return audit, check


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
    parser.add_argument("--expected-intersection-expanded-rows", type=int, default=3619)
    parser.add_argument("--expected-intersection-unique-files", type=int, default=3375)
    parser.add_argument("--expected-intersection-issue-stock", type=float, default=3883.0)
    args = parser.parse_args()

    for path in (args.d02_file, args.a04_file, args.b06_file, args.d03_reference_file, args.d05_reference_file):
        if not path.is_file():
            abort(f"Required input does not exist: {path}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading D02 canonical file burden: {args.d02_file}")
    d02 = read_table(args.d02_file)
    print(f"Reading A04 frozen ML file scores: {args.a04_file}")
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
    if a04.duplicated(list(FILE_KEYS)).any():
        abort("A04 must contain one row per exact snapshot/file identity")
    if b06.duplicated(list(REPO_TIME_KEYS)).any():
        abort("B06 contains duplicate repo-month keys")

    d02 = normalize_keys(d02, "D02")
    d02["sonar_issue_total"] = pd.to_numeric(d02["sonar_issue_total"], errors="raise")
    d02[NPR_METRIC] = pd.to_numeric(d02[NPR_METRIC], errors="coerce")
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
            "D02 and A04 exact file universes do not reconcile: "
            f"expanded_d02_only={d02_only_rows}, unique_d02_only={d02_unique_only}, unique_a04_only={a04_unique_only}"
        )

    ml_scored = infer_ml_scored_mask(merged)
    npr_eligible = merged[NPR_METRIC].notna() & np.isfinite(merged[NPR_METRIC])
    npr_selected = npr_eligible & (merged[NPR_METRIC] > NPR_THRESHOLD)
    ml_selected = ml_scored & (merged[ML_METRIC] > ML_THRESHOLD)
    both_selected = npr_selected & ml_selected
    npr_only = npr_selected & ~ml_selected
    ml_only = ml_selected & ~npr_selected
    union_selected = npr_selected | ml_selected

    category_masks = {
        "npr_selected": npr_selected,
        "ml_selected": ml_selected,
        "intersection_selected": both_selected,
        "npr_only": npr_only,
        "ml_only": ml_only,
        "union_selected": union_selected,
    }

    panel = b06[["repo_id", "time_index"]].copy()
    for prefix, mask in category_masks.items():
        agg = aggregate_selection(merged, mask, "sonar_issue_total", prefix)
        panel = panel.merge(agg, on=["repo_id", "time_index"], how="left", validate="one_to_one")
        panel[f"{prefix}_file_rows"] = panel[f"{prefix}_file_rows"].fillna(0).astype(int)
        panel[f"{prefix}_issue_total"] = panel[f"{prefix}_issue_total"].fillna(0.0)

    panel["selected_file_rows"] = panel["intersection_selected_file_rows"]
    panel["selected_issue_total"] = panel["intersection_selected_issue_total"]
    panel["log1p_selected_issue_total"] = np.log1p(panel["selected_issue_total"].astype(float))
    panel["detector_intersection_rule"] = "NPR_primary_AND_ML_primary"
    panel["npr_metric"] = NPR_METRIC
    panel["npr_operator"] = ">"
    panel["npr_threshold"] = NPR_THRESHOLD
    panel["ml_metric"] = ML_METRIC
    panel["ml_operator"] = ">"
    panel["ml_threshold"] = ML_THRESHOLD

    # Algebraic no-double-counting checks at every repo-month.
    count_identity = (
        panel["union_selected_file_rows"]
        == panel["npr_selected_file_rows"] + panel["ml_selected_file_rows"] - panel["intersection_selected_file_rows"]
    )
    disjoint_count_identity = (
        panel["union_selected_file_rows"]
        == panel["npr_only_file_rows"] + panel["ml_only_file_rows"] + panel["intersection_selected_file_rows"]
    )
    issue_identity = np.isclose(
        panel["union_selected_issue_total"],
        panel["npr_selected_issue_total"] + panel["ml_selected_issue_total"] - panel["intersection_selected_issue_total"],
        atol=1e-9,
        rtol=0,
    )
    disjoint_issue_identity = np.isclose(
        panel["union_selected_issue_total"],
        panel["npr_only_issue_total"] + panel["ml_only_issue_total"] + panel["intersection_selected_issue_total"],
        atol=1e-9,
        rtol=0,
    )

    if not bool(count_identity.all() and disjoint_count_identity.all() and issue_identity.all() and disjoint_issue_identity.all()):
        abort("Detector set algebra failed while auditing NPR/ML overlap")

    # Reconstruct existing frozen detector-only panels before trusting the intersection.
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
    npr_audit, _ = compare_reproduction(npr_reference, npr_reconstructed, "NPR")
    ml_audit, _ = compare_reproduction(ml_reference, ml_reconstructed, "ML")
    reproduction_audit = pd.concat([npr_audit, ml_audit], ignore_index=True)
    if not (reproduction_audit["status"] == "pass").all():
        abort("Detector-only reproduction failed; intersection panel is not trusted")

    def global_support_row(name: str, mask: pd.Series) -> dict[str, object]:
        selected = merged.loc[mask]
        return {
            "selection": name,
            "expanded_repo_month_file_rows": int(mask.sum()),
            "unique_historical_files": int(selected[list(FILE_KEYS)].drop_duplicates().shape[0]),
            "issue_stock": float(selected["sonar_issue_total"].sum()),
            "repo_months_with_selected_files": int((panel[f"{name}_file_rows"] > 0).sum()) if f"{name}_file_rows" in panel else np.nan,
            "repo_months_with_positive_issue_stock": int((panel[f"{name}_issue_total"] > 0).sum()) if f"{name}_issue_total" in panel else np.nan,
        }

    support_rows = [global_support_row(name, mask) for name, mask in category_masks.items()]
    support = pd.DataFrame(support_rows)
    intersection_count = int(both_selected.sum())
    union_count = int(union_selected.sum())
    npr_count = int(npr_selected.sum())
    ml_count = int(ml_selected.sum())
    jaccard = intersection_count / union_count if union_count else np.nan
    overlap_coefficient = intersection_count / min(npr_count, ml_count) if min(npr_count, ml_count) else np.nan
    support["jaccard_npr_ml"] = jaccard
    support["overlap_coefficient_npr_ml"] = overlap_coefficient

    intersection_zero_share = float((panel["selected_issue_total"] == 0).mean())
    intersection_within_variation_repos = int(
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
        ("duplicate_repo_month_keys", int(panel.duplicated(["repo_id", "time_index"]).sum()), 0),
        ("npr_reference_reproduction_failures", int((npr_audit["status"] != "pass").sum()), 0),
        ("ml_reference_reproduction_failures", int((ml_audit["status"] != "pass").sum()), 0),
        ("union_count_identity_failures", int((~count_identity).sum()), 0),
        ("union_disjoint_count_identity_failures", int((~disjoint_count_identity).sum()), 0),
        ("union_issue_identity_failures", int((~issue_identity).sum()), 0),
        ("union_disjoint_issue_identity_failures", int((~disjoint_issue_identity).sum()), 0),
        ("intersection_larger_than_npr_rows", int((panel["intersection_selected_file_rows"] > panel["npr_selected_file_rows"]).sum()), 0),
        ("intersection_larger_than_ml_rows", int((panel["intersection_selected_file_rows"] > panel["ml_selected_file_rows"]).sum()), 0),
        ("intersection_expanded_rows", intersection_count, args.expected_intersection_expanded_rows),
        ("intersection_unique_files", int(merged.loc[both_selected, list(FILE_KEYS)].drop_duplicates().shape[0]), args.expected_intersection_unique_files),
        ("intersection_issue_stock", float(merged.loc[both_selected, "sonar_issue_total"].sum()), args.expected_intersection_issue_stock),
        ("negative_selected_issue_rows", int((panel["selected_issue_total"] < 0).sum()), 0),
        ("log1p_recompute_mismatches", int((~np.isclose(panel["log1p_selected_issue_total"], np.log1p(panel["selected_issue_total"]), atol=1e-12, rtol=0)).sum()), 0),
    ]
    qc = pd.DataFrame(
        [
            {"check": name, "observed": observed, "expected": expected, "status": "pass" if observed == expected else "fail"}
            for name, observed, expected in qc_rows
        ]
    )
    if (qc["status"] != "pass").any() or (join_audit["status"] != "pass").any():
        abort("E05 intersection builder hard QC failed")

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
            ("definition", "intersection_rule", "NPR_selected AND ML_selected"),
            ("definition", "file_identity", "snapshot_id + relative_path + file_sha256"),
            ("definition", "consensus_policy", "only exact files selected by both frozen detectors are included"),
            ("definition", "quality_semantics", "unresolved SonarQube issue stock among intersection-selected historical Python files"),
            ("support", "intersection_zero_issue_repo_month_share", intersection_zero_share),
            ("support", "intersection_repositories_with_within_quality_variation", intersection_within_variation_repos),
            ("support", "jaccard_npr_ml", jaccard),
            ("support", "overlap_coefficient_npr_ml", overlap_coefficient),
        ],
        columns=["section", "metric", "value"],
    )

    panel_path = args.output_dir / "agc_detector_intersection_repo_month_panel.csv.gz"
    support_path = args.output_dir / "agc_detector_intersection_support.csv"
    reproduction_path = args.output_dir / "agc_detector_intersection_reproduction_audit.csv"
    join_path = args.output_dir / "agc_detector_intersection_join_audit.csv"
    qc_path = args.output_dir / "agc_detector_intersection_qc.csv"
    metadata_path = args.output_dir / "agc_detector_intersection_metadata.csv"

    panel.to_csv(panel_path, index=False, compression="gzip")
    support.to_csv(support_path, index=False)
    reproduction_audit.to_csv(reproduction_path, index=False)
    join_audit.to_csv(join_path, index=False)
    qc.to_csv(qc_path, index=False)
    metadata.to_csv(metadata_path, index=False)

    print("E05 detector-intersection panel: PASS")
    print(f"NPR primary selected expanded file rows: {npr_count}")
    print(f"ML primary selected expanded file rows: {ml_count}")
    print(f"Intersection expanded file rows: {intersection_count}")
    print(f"Union expanded file rows: {union_count}")
    print(f"NPR/ML Jaccard: {jaccard:.6f}")
    print(f"Intersection issue stock: {panel['selected_issue_total'].sum():.0f}")
    print(f"Intersection zero-burden repo-month share: {intersection_zero_share:.6f}")
    print(f"Intersection within-quality-variation repositories: {intersection_within_variation_repos}")
    print(f"Output panel: {panel_path}")


if __name__ == "__main__":
    main()
