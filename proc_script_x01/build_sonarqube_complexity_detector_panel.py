#!/usr/bin/env python3
"""Build J02 file-aligned cognitive-complexity panels for NPR and ML detectors.

J02 is a CPU-only integration stage. It combines the finalized J01 file-level
SonarQube cognitive-complexity/NCLOC measurements with the frozen combined
regular-function + class-method detector measurements:

* I01 combined FUN+C_FUN NPR file scores and the frozen I02 threshold grid.
* I06 combined FUN+C_FUN ML file scores and the corrected I07-v2 threshold grid.
* B06 authoritative 1,954-row repository-month treatment-timing panel.

The experiment never reruns SonarQube, never reruns detector inference/scoring,
and never estimates a treatment effect. It performs exact historical-file
identity alignment, audits all scope differences in both directions, applies
only frozen detector thresholds, aggregates non-negative file complexity to the
historical snapshot level, and expands those frozen snapshot measurements to the
B06 repository-month panel.

Historical-file join contract
-----------------------------
Primary key:
    SonarQube J01: (snapshot_key, component_path)
    Detector data: (snapshot_id, relative_path)

Safety identity fields are also required to agree on matched rows:
    dataset_source, repo_name, commit SHA

J02 never path-remaps an unmatched file. All unmatched files are written to
explicit audit artifacts for downstream scope/sensitivity decisions.

Outcome semantics
-----------------
Primary burden:
    selected_cognitive_complexity = sum(file cognitive_complexity)
    log1p_selected_cognitive_complexity = log1p(selected_cognitive_complexity)

Normalization robustness:
    selected_complexity_per_kloc = selected_cognitive_complexity /
                                   (selected_ncloc / 1000)
when selected_ncloc > 0; otherwise blank.

Detector semantics
------------------
NPR:
    file_npr_fun_cfun_space_by_token_weighted > frozen I02 threshold.
    Non-finite NPR is unclassified and never treated as below-threshold/HWC.

ML:
    combined AGC body tokens / combined body tokens > frozen I07-v2 threshold.
    Threshold comparison uses exact integer arithmetic, not serialized floats.
    Unscored ML files are unclassified.

Outputs under repo_x01/run-x-j02
--------------------------------
python_sonarqube_file_complexity_detector_join.csv.gz
python_sonarqube_complexity_files_outside_detector_universe.csv
python_detector_files_without_sonarqube_complexity.csv
python_sonarqube_complexity_alignment_by_snapshot.csv
python_sonarqube_complexity_threshold_global_audit.csv
python_sonarqube_complexity_repo_month_panel.csv.gz
python_sonarqube_complexity_qc.csv
python_sonarqube_complexity_summary.csv
metadata.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


SCRIPT_VERSION = "run-x-j02-v1"
EXPECTED_J01_ROWS = 493_805
EXPECTED_DETECTOR_ROWS = 494_592
EXPECTED_SNAPSHOTS = 1_496
EXPECTED_REPOSITORIES = 167
EXPECTED_B06_ROWS = 1_954
EXPECTED_TREATMENT_REPOSITORIES = 63
EXPECTED_CONTROL_REPOSITORIES = 104
EXPECTED_NPR_THRESHOLD_COUNT = 22
EXPECTED_ML_THRESHOLD_COUNT = 21
NPR_METRIC = "file_npr_fun_cfun_space_by_token_weighted"
ML_METRIC = "file_ml_fun_cfun_agc_share_space_by_token_weighted"
ML_NUMERATOR = "ml_fun_cfun_agc_space_by_tokens"
ML_DENOMINATOR = "ml_fun_cfun_space_by_tokens_total"

J01_REQUIRED = {
    "dataset_source", "repo_name", "snapshot_key", "commit_sha", "component_path",
    "cognitive_complexity", "cognitive_complexity_measure_present",
    "ncloc", "ncloc_measure_present",
}
J01_SNAPSHOT_REQUIRED = {
    "dataset_source", "repo_name", "snapshot_key", "commit_sha", "file_components",
    "project_cognitive_complexity", "file_cognitive_complexity_sum",
    "cognitive_complexity_reconciles", "project_ncloc", "file_ncloc_sum", "ncloc_reconciles", "status",
}
I01_REQUIRED = {
    "snapshot_id", "dataset_source", "repo_name", "snapshot_commit", "relative_path",
    NPR_METRIC, "file_npr_fun_cfun_status",
}
I06_REQUIRED = {
    "snapshot_id", "dataset_source", "repo_name", "snapshot_commit", "relative_path",
    ML_NUMERATOR, ML_DENOMINATOR, ML_METRIC, "file_ml_fun_cfun_agc_status",
}
THRESHOLD_REQUIRED = {
    "threshold_id", "threshold_role", "threshold", "comparison_operator", "metric",
}
B06_REQUIRED = {
    "repo_id", "repo_name", "dataset_source", "scope_role", "treatment_group",
    "time", "time_index", "event", "event_index", "time_to_event", "is_treatment",
    "post_event", "cursor", "latest_commit_effective", "snapshot_key",
    "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues",
    "quality_did_complete", "quality_scope", "quality_count_semantics",
}

BASE_PANEL_COLUMNS = [
    "repo_id", "repo_name", "dataset_source", "scope_role", "treatment_group",
    "time", "time_index", "event", "event_index", "time_to_event", "is_treatment",
    "post_event", "cursor", "latest_commit_effective", "snapshot_key",
    "log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues",
]


def clean(value: Any) -> str:
    """Normalize a possibly missing text value."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one input file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    """Fail when an input is missing required columns."""
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")


def read_csv(path: Path, string_columns: Iterable[str] = (), usecols: Iterable[str] | None = None) -> pd.DataFrame:
    """Read CSV/CSV.GZ while preserving selected identity fields as strings."""
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Required input not found: {path}")
    header = pd.read_csv(path, nrows=0)
    selected = list(usecols) if usecols is not None else None
    available = set(header.columns)
    dtype = {column: "string" for column in string_columns if column in available}
    return pd.read_csv(path, usecols=selected, dtype=dtype, low_memory=False)


def atomic_csv(df: pd.DataFrame, path: Path, compression: str | None = None) -> None:
    """Write a CSV atomically."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = ".tmp.gz" if str(path).endswith(".gz") else ".tmp"
    tmp = Path(str(path) + suffix)
    df.to_csv(tmp, index=False, compression=compression)
    os.replace(tmp, path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    """Write JSON atomically."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def add_check(rows: list[dict[str, Any]], name: str, observed: Any, expected: Any, passed: bool, note: str = "", severity: str = "hard") -> None:
    """Append one QC check."""
    rows.append({
        "check_name": name,
        "severity": severity,
        "passed": 1 if passed else 0,
        "observed": observed,
        "expected": expected,
        "note": note,
    })


def normalize_identity(df: pd.DataFrame, snapshot_col: str, path_col: str, commit_col: str) -> pd.DataFrame:
    """Create canonical file-identity columns without altering source values."""
    out = df.copy()
    out["join_snapshot"] = out[snapshot_col].map(clean)
    out["join_path"] = out[path_col].map(clean)
    out["join_dataset"] = out["dataset_source"].map(clean).str.casefold()
    out["join_repo"] = out["repo_name"].map(clean).str.casefold()
    out["join_commit"] = out[commit_col].map(clean).str.casefold()
    return out


def load_threshold_spec(path: Path, expected_metric: str, expected_count: int, label: str) -> pd.DataFrame:
    """Load and validate one previously frozen detector threshold specification."""
    spec = read_csv(path, ["threshold_id", "threshold_role", "comparison_operator", "metric"])
    require_columns(spec, THRESHOLD_REQUIRED, label)
    if len(spec) != expected_count:
        raise ValueError(f"{label} expected {expected_count} rows, observed {len(spec)}")
    if spec["threshold_id"].map(clean).duplicated().any():
        raise ValueError(f"{label} contains duplicate threshold_id values")
    if not spec["comparison_operator"].map(clean).eq(">").all():
        raise ValueError(f"{label} must use strict > for every threshold")
    if not spec["metric"].map(clean).eq(expected_metric).all():
        raise ValueError(f"{label} metric mismatch")
    spec["threshold"] = pd.to_numeric(spec["threshold"], errors="raise")
    return spec


def load_j01(path: Path) -> pd.DataFrame:
    """Load finalized J01 file-level SonarQube measurements."""
    data = read_csv(
        path,
        ["dataset_source", "repo_name", "snapshot_key", "commit_sha", "component_path", "language", "qualifier"],
    )
    require_columns(data, J01_REQUIRED, "J01 file complexity")
    data = normalize_identity(data, "snapshot_key", "component_path", "commit_sha")
    for column in ["cognitive_complexity", "ncloc", "cognitive_complexity_measure_present", "ncloc_measure_present"]:
        data[column] = pd.to_numeric(data[column], errors="raise")
    if (data[["cognitive_complexity", "ncloc"]] < 0).any().any():
        raise ValueError("J01 complexity/NCLOC must be non-negative")
    if data.duplicated(["join_snapshot", "join_path"]).any():
        raise ValueError("J01 contains duplicate snapshot/path keys")
    if "language" in data.columns and not data["language"].map(clean).str.casefold().eq("py").all():
        raise ValueError("J01 contains non-Python language rows")
    return data


def load_i01(path: Path) -> pd.DataFrame:
    """Load unique historical combined FUN+C_FUN NPR file scores."""
    data = read_csv(path, ["snapshot_id", "dataset_source", "repo_name", "snapshot_commit", "relative_path", "file_npr_fun_cfun_status"])
    require_columns(data, I01_REQUIRED, "I01 NPR file scores")
    data = normalize_identity(data, "snapshot_id", "relative_path", "snapshot_commit")
    data[NPR_METRIC] = pd.to_numeric(data[NPR_METRIC], errors="coerce")
    if data.duplicated(["join_snapshot", "join_path"]).any():
        raise ValueError("I01 contains duplicate snapshot/path keys")
    return data


def load_i06(path: Path) -> pd.DataFrame:
    """Load unique historical combined FUN+C_FUN ML file scores."""
    data = read_csv(path, ["snapshot_id", "dataset_source", "repo_name", "snapshot_commit", "relative_path", "file_ml_fun_cfun_agc_status"])
    require_columns(data, I06_REQUIRED, "I06 ML file scores")
    data = normalize_identity(data, "snapshot_id", "relative_path", "snapshot_commit")
    data[ML_METRIC] = pd.to_numeric(data[ML_METRIC], errors="coerce")
    data[ML_NUMERATOR] = pd.to_numeric(data[ML_NUMERATOR], errors="raise").astype("int64")
    data[ML_DENOMINATOR] = pd.to_numeric(data[ML_DENOMINATOR], errors="raise").astype("int64")
    if data.duplicated(["join_snapshot", "join_path"]).any():
        raise ValueError("I06 contains duplicate snapshot/path keys")
    scored = data["file_ml_fun_cfun_agc_status"].map(clean).eq("scored")
    if ((data.loc[scored, ML_DENOMINATOR] <= 0) | (data.loc[scored, ML_NUMERATOR] < 0) | (data.loc[scored, ML_NUMERATOR] > data.loc[scored, ML_DENOMINATOR])).any():
        raise ValueError("I06 scored rows contain invalid ML token numerator/denominator")
    return data


def validate_detector_identity(i01: pd.DataFrame, i06: pd.DataFrame) -> None:
    """Require the finalized NPR and ML historical-file universes to be identical."""
    keys = ["join_snapshot", "join_path"]
    left = i01[keys + ["join_dataset", "join_repo", "join_commit"]].sort_values(keys, kind="stable").reset_index(drop=True)
    right = i06[keys + ["join_dataset", "join_repo", "join_commit"]].sort_values(keys, kind="stable").reset_index(drop=True)
    if len(left) != len(right) or not left[keys].equals(right[keys]):
        raise ValueError("I01 and I06 historical file-key universes differ")
    for column in ["join_dataset", "join_repo", "join_commit"]:
        if not left[column].equals(right[column]):
            raise ValueError(f"I01/I06 identity mismatch in {column}")


def build_alignment(j01: pd.DataFrame, i01: pd.DataFrame, i06: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Align J01 with detector files and emit unmatched rows in both directions."""
    keys = ["join_snapshot", "join_path"]
    detector = i01[keys + ["join_dataset", "join_repo", "join_commit", NPR_METRIC, "file_npr_fun_cfun_status"]].merge(
        i06[keys + [ML_METRIC, ML_NUMERATOR, ML_DENOMINATOR, "file_ml_fun_cfun_agc_status"]],
        on=keys,
        how="inner",
        validate="one_to_one",
    )

    joined = j01.merge(detector, on=keys, how="left", suffixes=("_j01", "_detector"), indicator=True, validate="one_to_one")
    matched = joined["_merge"].eq("both")
    for field in ["join_dataset", "join_repo", "join_commit"]:
        mismatch = matched & ~joined[f"{field}_j01"].eq(joined[f"{field}_detector"])
        if mismatch.any():
            examples = joined.loc[mismatch, ["join_snapshot", "join_path", f"{field}_j01", f"{field}_detector"]].head(10)
            raise ValueError(f"Matched J01/detector safety identity mismatch in {field}: {examples.to_dict('records')}")

    j01_only = joined.loc[~matched].copy()
    detector_keys = detector[keys]
    detector_with_j01 = detector.merge(j01[keys], on=keys, how="left", indicator=True, validate="one_to_one")
    detector_only_keys = detector_with_j01.loc[detector_with_j01["_merge"].eq("left_only"), keys]
    detector_only = detector.merge(detector_only_keys, on=keys, how="inner", validate="one_to_one")

    keep = joined.loc[matched].copy()
    keep["dataset_source"] = keep["dataset_source"].map(clean).str.casefold()
    keep["repo_name"] = keep["repo_name"].map(clean)
    keep["snapshot_key"] = keep["snapshot_key"].map(clean)
    keep["component_path"] = keep["component_path"].map(clean)
    keep["commit_sha"] = keep["commit_sha"].map(clean).str.casefold()
    keep.drop(columns=[column for column in keep.columns if column.startswith("join_")] + ["_merge"], inplace=True, errors="ignore")

    j01_only_out = j01_only[[
        "dataset_source", "repo_name", "snapshot_key", "commit_sha", "component_path",
        "cognitive_complexity", "ncloc", "cognitive_complexity_measure_present", "ncloc_measure_present",
    ]].copy()
    j01_only_out["scope_status"] = "j01_only_no_detector_file_identity"

    detector_only_out = detector_only.rename(columns={
        "join_snapshot": "snapshot_id", "join_path": "relative_path",
        "join_dataset": "dataset_source", "join_repo": "repo_name_casefold", "join_commit": "snapshot_commit",
    })
    detector_only_out["scope_status"] = "detector_only_no_j01_sonarqube_file_identity"
    return keep, j01_only_out, detector_only_out


def load_b06(path: Path) -> pd.DataFrame:
    """Load and validate the authoritative B06 repo-month timing panel."""
    data = read_csv(path, ["repo_name", "dataset_source", "scope_role", "time", "event", "latest_commit_effective", "snapshot_key", "quality_scope", "quality_count_semantics"])
    require_columns(data, B06_REQUIRED, "B06 panel")
    data["dataset_source"] = data["dataset_source"].map(clean).str.casefold()
    data["repo_name"] = data["repo_name"].map(clean)
    data["snapshot_key"] = data["snapshot_key"].map(clean)
    data["latest_commit_effective"] = data["latest_commit_effective"].map(clean).str.casefold()
    for column in ["repo_id", "treatment_group", "time_index", "event_index"]:
        data[column] = pd.to_numeric(data[column], errors="raise").astype("int64")
    for column in ["log_age", "ncloc_py_sonarqube", "log_contributors", "log_stars", "log_issues"]:
        data[column] = pd.to_numeric(data[column], errors="raise")
    if data.duplicated(["repo_id", "time_index"]).any():
        raise ValueError("B06 contains duplicate repo_id/time_index rows")
    return data


def validate_snapshot_reconciliation(j01: pd.DataFrame, snapshot_file: Path) -> pd.DataFrame:
    """Recompute J01 snapshot totals and compare them to the finalized J01 reconciliation artifact."""
    snapshots = read_csv(snapshot_file, ["dataset_source", "repo_name", "snapshot_key", "commit_sha", "status"])
    require_columns(snapshots, J01_SNAPSHOT_REQUIRED, "J01 snapshot reconciliation")
    for column in ["file_components", "project_cognitive_complexity", "file_cognitive_complexity_sum", "project_ncloc", "file_ncloc_sum", "cognitive_complexity_reconciles", "ncloc_reconciles"]:
        snapshots[column] = pd.to_numeric(snapshots[column], errors="raise")
    grouped = j01.groupby("snapshot_key", as_index=False).agg(
        j02_file_components=("component_path", "size"),
        j02_cognitive_complexity=("cognitive_complexity", "sum"),
        j02_ncloc=("ncloc", "sum"),
    )
    merged = snapshots.merge(grouped, on="snapshot_key", how="outer", validate="one_to_one", indicator=True)
    if not merged["_merge"].eq("both").all():
        raise ValueError("J01 file output and snapshot reconciliation snapshot universes differ")
    failures = (
        merged["file_components"].ne(merged["j02_file_components"])
        | ~np.isclose(merged["file_cognitive_complexity_sum"], merged["j02_cognitive_complexity"], rtol=0.0, atol=1e-9)
        | ~np.isclose(merged["file_ncloc_sum"], merged["j02_ncloc"], rtol=0.0, atol=1e-9)
        | merged["cognitive_complexity_reconciles"].ne(1)
        | merged["ncloc_reconciles"].ne(1)
        | ~merged["status"].map(clean).eq("success")
    )
    if failures.any():
        raise ValueError(f"J01 snapshot reconciliation failed for {int(failures.sum())} snapshots")
    return merged


def threshold_selected_npr(data: pd.DataFrame, threshold: float) -> pd.Series:
    """Apply strict finite NPR selection."""
    score = pd.to_numeric(data[NPR_METRIC], errors="coerce")
    return score.notna() & np.isfinite(score.to_numpy(dtype=float)) & score.gt(threshold)


def threshold_selected_ml(data: pd.DataFrame, threshold: float) -> pd.Series:
    """Apply corrected I07-v2 exact integer token-ratio thresholding."""
    status = data["file_ml_fun_cfun_agc_status"].map(clean).eq("scored")
    numerator = pd.to_numeric(data[ML_NUMERATOR], errors="coerce")
    denominator = pd.to_numeric(data[ML_DENOMINATOR], errors="coerce")
    threshold_decimal = Decimal(str(threshold))
    percent = threshold_decimal * Decimal(100)
    if percent != percent.to_integral_value():
        raise ValueError(f"ML threshold is not an exact integer percent: {threshold}")
    pct = int(percent)
    return status & numerator.notna() & denominator.gt(0) & (numerator.astype("Int64") * 100 > denominator.astype("Int64") * pct)


def aggregate_snapshot_rows(data: pd.DataFrame, selected: pd.Series, prefix: str) -> pd.DataFrame:
    """Aggregate one nested file selection to historical snapshot totals."""
    work = data.loc[selected, ["snapshot_key", "cognitive_complexity", "ncloc", "cognitive_complexity_measure_present", "ncloc_measure_present"]].copy()
    if work.empty:
        return pd.DataFrame(columns=[
            "snapshot_key", f"{prefix}_file_count", f"{prefix}_cognitive_complexity", f"{prefix}_ncloc",
            f"{prefix}_complexity_measure_present_count", f"{prefix}_ncloc_measure_present_count",
        ])
    return work.groupby("snapshot_key", as_index=False).agg(**{
        f"{prefix}_file_count": ("cognitive_complexity", "size"),
        f"{prefix}_cognitive_complexity": ("cognitive_complexity", "sum"),
        f"{prefix}_ncloc": ("ncloc", "sum"),
        f"{prefix}_complexity_measure_present_count": ("cognitive_complexity_measure_present", "sum"),
        f"{prefix}_ncloc_measure_present_count": ("ncloc_measure_present", "sum"),
    })


def panel_from_snapshot_aggregate(b06: pd.DataFrame, agg: pd.DataFrame, scope_id: str, threshold_id: str, threshold_role: str, threshold: float | str, operator: str) -> pd.DataFrame:
    """Expand one historical snapshot aggregate to B06 repository-month rows."""
    merged = b06[BASE_PANEL_COLUMNS].merge(agg, on="snapshot_key", how="left", validate="many_to_one")
    metric_cols = [column for column in merged.columns if column.endswith(("_file_count", "_cognitive_complexity", "_ncloc", "_measure_present_count"))]
    for column in metric_cols:
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0)
    prefix = "all_python" if scope_id == "all_python" else "selected"
    rename = {
        f"{prefix}_file_count": "selected_file_count",
        f"{prefix}_cognitive_complexity": "selected_cognitive_complexity",
        f"{prefix}_ncloc": "selected_ncloc",
        f"{prefix}_complexity_measure_present_count": "selected_complexity_measure_present_count",
        f"{prefix}_ncloc_measure_present_count": "selected_ncloc_measure_present_count",
    }
    merged.rename(columns=rename, inplace=True)
    for column in rename.values():
        if column not in merged.columns:
            merged[column] = 0.0
    merged["selected_file_count"] = merged["selected_file_count"].astype("int64")
    merged["log1p_selected_cognitive_complexity"] = np.log1p(merged["selected_cognitive_complexity"].astype(float))
    merged["selected_complexity_per_kloc"] = np.where(
        merged["selected_ncloc"].gt(0),
        merged["selected_cognitive_complexity"] / (merged["selected_ncloc"] / 1000.0),
        np.nan,
    )
    merged["has_selected_files"] = merged["selected_file_count"].gt(0).astype("int64")
    merged["has_positive_complexity"] = merged["selected_cognitive_complexity"].gt(0).astype("int64")
    merged.insert(0, "scope_id", scope_id)
    merged.insert(1, "threshold_id", threshold_id)
    merged.insert(2, "threshold_role", threshold_role)
    merged.insert(3, "threshold", threshold)
    merged.insert(4, "comparison_operator", operator)
    return merged


def build_outputs(j01: pd.DataFrame, joined: pd.DataFrame, i01: pd.DataFrame, i06: pd.DataFrame, npr_spec: pd.DataFrame, ml_spec: pd.DataFrame, b06: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build all-Python plus frozen-threshold NPR/ML complexity panels and global audits."""
    panels: list[pd.DataFrame] = []
    audits: list[dict[str, Any]] = []

    all_agg = aggregate_snapshot_rows(j01, pd.Series(True, index=j01.index), "all_python")
    panels.append(panel_from_snapshot_aggregate(b06, all_agg, "all_python", "all_python", "reference_scope", "", "all"))
    audits.append({
        "scope_id": "all_python", "threshold_id": "all_python", "threshold_role": "reference_scope", "threshold": "", "comparison_operator": "all",
        "detector_file_rows": "", "detector_eligible_files": "", "detector_selected_files": "",
        "aligned_file_rows": len(j01), "aligned_eligible_files": len(j01), "aligned_selected_files": len(j01),
        "selected_without_j01_complexity": 0,
        "selected_cognitive_complexity": float(j01["cognitive_complexity"].sum()),
        "selected_ncloc": float(j01["ncloc"].sum()),
    })

    # Whole detector tables are used only for auditing selection support lost at the J01 file boundary.
    aligned_keys = joined[["snapshot_key", "component_path"]].rename(columns={"snapshot_key": "join_snapshot", "component_path": "join_path"})

    for spec in npr_spec.itertuples(index=False):
        threshold = float(spec.threshold)
        selected_aligned = threshold_selected_npr(joined, threshold)
        agg = aggregate_snapshot_rows(joined, selected_aligned, "selected")
        panels.append(panel_from_snapshot_aggregate(b06, agg, "npr_fun_cfun", clean(spec.threshold_id), clean(spec.threshold_role), threshold, ">"))

        eligible_all = pd.to_numeric(i01[NPR_METRIC], errors="coerce").notna() & np.isfinite(pd.to_numeric(i01[NPR_METRIC], errors="coerce").to_numpy(dtype=float))
        selected_all = threshold_selected_npr(i01, threshold)
        selected_keys = i01.loc[selected_all, ["join_snapshot", "join_path"]]
        selected_missing = selected_keys.merge(aligned_keys, on=["join_snapshot", "join_path"], how="left", indicator=True)
        audits.append({
            "scope_id": "npr_fun_cfun", "threshold_id": clean(spec.threshold_id), "threshold_role": clean(spec.threshold_role), "threshold": threshold, "comparison_operator": ">",
            "detector_file_rows": len(i01), "detector_eligible_files": int(eligible_all.sum()), "detector_selected_files": int(selected_all.sum()),
            "aligned_file_rows": len(joined), "aligned_eligible_files": int(pd.to_numeric(joined[NPR_METRIC], errors="coerce").notna().sum()), "aligned_selected_files": int(selected_aligned.sum()),
            "selected_without_j01_complexity": int(selected_missing["_merge"].eq("left_only").sum()),
            "selected_cognitive_complexity": float(joined.loc[selected_aligned, "cognitive_complexity"].sum()),
            "selected_ncloc": float(joined.loc[selected_aligned, "ncloc"].sum()),
        })

    for spec in ml_spec.itertuples(index=False):
        threshold = float(spec.threshold)
        selected_aligned = threshold_selected_ml(joined, threshold)
        agg = aggregate_snapshot_rows(joined, selected_aligned, "selected")
        panels.append(panel_from_snapshot_aggregate(b06, agg, "ml_fun_cfun", clean(spec.threshold_id), clean(spec.threshold_role), threshold, ">"))

        eligible_all = i06["file_ml_fun_cfun_agc_status"].map(clean).eq("scored")
        selected_all = threshold_selected_ml(i06, threshold)
        selected_keys = i06.loc[selected_all, ["join_snapshot", "join_path"]]
        selected_missing = selected_keys.merge(aligned_keys, on=["join_snapshot", "join_path"], how="left", indicator=True)
        audits.append({
            "scope_id": "ml_fun_cfun", "threshold_id": clean(spec.threshold_id), "threshold_role": clean(spec.threshold_role), "threshold": threshold, "comparison_operator": ">",
            "detector_file_rows": len(i06), "detector_eligible_files": int(eligible_all.sum()), "detector_selected_files": int(selected_all.sum()),
            "aligned_file_rows": len(joined), "aligned_eligible_files": int(joined["file_ml_fun_cfun_agc_status"].map(clean).eq("scored").sum()), "aligned_selected_files": int(selected_aligned.sum()),
            "selected_without_j01_complexity": int(selected_missing["_merge"].eq("left_only").sum()),
            "selected_cognitive_complexity": float(joined.loc[selected_aligned, "cognitive_complexity"].sum()),
            "selected_ncloc": float(joined.loc[selected_aligned, "ncloc"].sum()),
        })

    panel = pd.concat(panels, ignore_index=True)
    audit = pd.DataFrame(audits)

    # Snapshot alignment summary includes J01, detector, and matched file counts.
    j_counts = j01.groupby("snapshot_key").size().rename("j01_file_rows")
    d_counts = i01.groupby("join_snapshot").size().rename("detector_file_rows")
    m_counts = joined.groupby("snapshot_key").size().rename("matched_file_rows")
    alignment = pd.concat([j_counts, d_counts, m_counts], axis=1).fillna(0).reset_index().rename(columns={"index": "snapshot_key"})
    alignment["j01_only_file_rows"] = alignment["j01_file_rows"] - alignment["matched_file_rows"]
    alignment["detector_only_file_rows"] = alignment["detector_file_rows"] - alignment["matched_file_rows"]
    return panel, audit, alignment


def monotonic_failures(audit: pd.DataFrame, scope_id: str) -> int:
    """Count monotonicity failures over numeric threshold grids for nested selections."""
    part = audit.loc[audit["scope_id"].eq(scope_id)].copy()
    if part.empty:
        return 1
    part["threshold_numeric"] = pd.to_numeric(part["threshold"], errors="coerce")
    part = part.dropna(subset=["threshold_numeric"]).sort_values("threshold_numeric", kind="stable")
    failures = 0
    for column in ["aligned_selected_files", "selected_cognitive_complexity", "selected_ncloc"]:
        values = pd.to_numeric(part[column], errors="coerce").to_numpy(dtype=float)
        failures += int(np.sum(np.diff(values) > 1e-9))
    return failures


def run_self_test() -> None:
    """Exercise strict NPR/ML selection and snapshot aggregation on synthetic files."""
    rows = pd.DataFrame({
        "snapshot_key": ["s1", "s1", "s2"],
        "component_path": ["a.py", "b.py", "c.py"],
        "cognitive_complexity": [3.0, 0.0, 7.0],
        "ncloc": [100.0, 20.0, 200.0],
        "cognitive_complexity_measure_present": [1, 0, 1],
        "ncloc_measure_present": [1, 1, 1],
        NPR_METRIC: [1.6, np.nan, 1.5],
        "file_ml_fun_cfun_agc_status": ["scored", "no_ml_fun_cfun", "scored"],
        ML_NUMERATOR: [51, 0, 50],
        ML_DENOMINATOR: [100, 0, 100],
    })
    npr = threshold_selected_npr(rows, 1.571637)
    ml = threshold_selected_ml(rows, 0.50)
    assert npr.tolist() == [True, False, False]
    assert ml.tolist() == [True, False, False]
    agg = aggregate_snapshot_rows(rows, npr, "selected")
    assert int(agg.loc[0, "selected_file_count"]) == 1
    assert math.isclose(float(agg.loc[0, "selected_cognitive_complexity"]), 3.0)
    print("build_sonarqube_complexity_detector_panel self-test: PASS")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Build J02 cognitive-complexity panels for frozen NPR/ML detector scopes.")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--j01-file", type=Path)
    parser.add_argument("--j01-snapshot-file", type=Path)
    parser.add_argument("--i01-file", type=Path)
    parser.add_argument("--i06-file", type=Path)
    parser.add_argument("--i02-threshold-spec-file", type=Path)
    parser.add_argument("--i07-threshold-spec-file", type=Path)
    parser.add_argument("--b06-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--strict-expected-counts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return 0

    required_args = ["j01_file", "j01_snapshot_file", "i01_file", "i06_file", "i02_threshold_spec_file", "i07_threshold_spec_file", "b06_file", "output_dir"]
    missing = [name for name in required_args if getattr(args, name) is None]
    if missing:
        raise ValueError(f"Missing required arguments: {missing}")

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    j01 = load_j01(args.j01_file)
    i01 = load_i01(args.i01_file)
    i06 = load_i06(args.i06_file)
    validate_detector_identity(i01, i06)
    npr_spec = load_threshold_spec(args.i02_threshold_spec_file, NPR_METRIC, EXPECTED_NPR_THRESHOLD_COUNT, "I02 NPR threshold spec")
    ml_spec = load_threshold_spec(args.i07_threshold_spec_file, ML_METRIC, EXPECTED_ML_THRESHOLD_COUNT, "I07-v2 ML threshold spec")
    b06 = load_b06(args.b06_file)
    snapshot_recon = validate_snapshot_reconciliation(j01, args.j01_snapshot_file)

    joined, j01_only, detector_only = build_alignment(j01, i01, i06)
    panel, global_audit, alignment = build_outputs(j01, joined, i01, i06, npr_spec, ml_spec, b06)

    checks: list[dict[str, Any]] = []
    severity = "hard" if args.strict_expected_counts else "informational"
    for name, observed, expected in [
        ("j01_file_rows", len(j01), EXPECTED_J01_ROWS),
        ("i01_detector_file_rows", len(i01), EXPECTED_DETECTOR_ROWS),
        ("i06_detector_file_rows", len(i06), EXPECTED_DETECTOR_ROWS),
        ("j01_snapshots", j01["snapshot_key"].nunique(), EXPECTED_SNAPSHOTS),
        ("detector_snapshots", i01["join_snapshot"].nunique(), EXPECTED_SNAPSHOTS),
        ("b06_repo_month_rows", len(b06), EXPECTED_B06_ROWS),
        ("b06_repositories", b06["repo_id"].nunique(), EXPECTED_REPOSITORIES),
        ("b06_treatment_repositories", b06.loc[b06["treatment_group"].eq(1), "repo_id"].nunique(), EXPECTED_TREATMENT_REPOSITORIES),
        ("b06_control_repositories", b06.loc[b06["treatment_group"].eq(0), "repo_id"].nunique(), EXPECTED_CONTROL_REPOSITORIES),
    ]:
        add_check(checks, name, observed, expected, observed == expected, "Frozen production accounting.", severity)

    add_check(checks, "j01_duplicate_snapshot_paths", int(j01.duplicated(["snapshot_key", "component_path"]).sum()), 0, not j01.duplicated(["snapshot_key", "component_path"]).any(), "J01 file identity must be unique.")
    add_check(checks, "i01_duplicate_snapshot_paths", int(i01.duplicated(["join_snapshot", "join_path"]).sum()), 0, not i01.duplicated(["join_snapshot", "join_path"]).any(), "I01 file identity must be unique.")
    add_check(checks, "j01_snapshot_reconciliation_rows", len(snapshot_recon), EXPECTED_SNAPSHOTS, len(snapshot_recon) == EXPECTED_SNAPSHOTS, "J01 file sums must reconcile to the finalized snapshot artifact.")
    add_check(checks, "matched_file_rows", len(joined), "audit_only", True, "Scope difference is expected to be audited, not silently forced to equality.", "informational")
    add_check(checks, "j01_only_file_rows", len(j01_only), "audit_only", True, "Files present in SonarQube but absent from detector universe are explicit scope exclusions.", "informational")
    add_check(checks, "detector_only_file_rows", len(detector_only), "audit_only", True, "Detector files without J01 complexity are explicit scope exclusions.", "informational")
    add_check(checks, "npr_threshold_count", len(npr_spec), EXPECTED_NPR_THRESHOLD_COUNT, len(npr_spec) == EXPECTED_NPR_THRESHOLD_COUNT, "Frozen I02 threshold grid must be complete.")
    add_check(checks, "ml_threshold_count", len(ml_spec), EXPECTED_ML_THRESHOLD_COUNT, len(ml_spec) == EXPECTED_ML_THRESHOLD_COUNT, "Corrected I07-v2 threshold grid must be complete.")
    add_check(checks, "npr_threshold_monotonicity_failures", monotonic_failures(global_audit, "npr_fun_cfun"), 0, monotonic_failures(global_audit, "npr_fun_cfun") == 0, "Nested NPR selections and non-negative complexity/NCLOC sums must be monotone.")
    add_check(checks, "ml_threshold_monotonicity_failures", monotonic_failures(global_audit, "ml_fun_cfun"), 0, monotonic_failures(global_audit, "ml_fun_cfun") == 0, "Nested ML selections and non-negative complexity/NCLOC sums must be monotone.")

    expected_panel_rows = EXPECTED_B06_ROWS * (1 + EXPECTED_NPR_THRESHOLD_COUNT + EXPECTED_ML_THRESHOLD_COUNT)
    add_check(checks, "repo_month_panel_rows", len(panel), expected_panel_rows, len(panel) == expected_panel_rows, "All-Python + NPR thresholds + ML thresholds must expand to B06 exactly.")
    key_cols = ["scope_id", "threshold_id", "repo_id", "time_index"]
    add_check(checks, "repo_month_panel_duplicate_keys", int(panel.duplicated(key_cols).sum()), 0, not panel.duplicated(key_cols).any(), "Long complexity panel key must be unique.")
    add_check(checks, "negative_complexity_rows", int((panel["selected_cognitive_complexity"] < 0).sum()), 0, not (panel["selected_cognitive_complexity"] < 0).any(), "Cognitive complexity burden must be non-negative.")
    add_check(checks, "negative_ncloc_rows", int((panel["selected_ncloc"] < 0).sum()), 0, not (panel["selected_ncloc"] < 0).any(), "Selected NCLOC must be non-negative.")

    checks_df = pd.DataFrame(checks)
    hard_failures = int(((checks_df["severity"] == "hard") & (checks_df["passed"] != 1)).sum())
    status = "FAIL" if hard_failures else ("PASS_WITH_SCOPE_EXCLUSIONS" if len(j01_only) or len(detector_only) else "PASS")

    join_out = output_dir / "python_sonarqube_file_complexity_detector_join.csv.gz"
    j01_only_out = output_dir / "python_sonarqube_complexity_files_outside_detector_universe.csv"
    detector_only_out = output_dir / "python_detector_files_without_sonarqube_complexity.csv"
    align_out = output_dir / "python_sonarqube_complexity_alignment_by_snapshot.csv"
    audit_out = output_dir / "python_sonarqube_complexity_threshold_global_audit.csv"
    panel_out = output_dir / "python_sonarqube_complexity_repo_month_panel.csv.gz"
    qc_out = output_dir / "python_sonarqube_complexity_qc.csv"
    summary_out = output_dir / "python_sonarqube_complexity_summary.csv"
    metadata_out = output_dir / "metadata.json"

    atomic_csv(joined, join_out, compression="gzip")
    atomic_csv(j01_only, j01_only_out)
    atomic_csv(detector_only, detector_only_out)
    atomic_csv(alignment, align_out)
    atomic_csv(global_audit, audit_out)
    atomic_csv(panel, panel_out, compression="gzip")
    atomic_csv(checks_df, qc_out)

    summary = pd.DataFrame([
        ["implementation", "version", SCRIPT_VERSION, ""],
        ["run", "status", status, ""],
        ["run", "hard_qc_failures", hard_failures, ""],
        ["input", "j01_file_rows", len(j01), ""],
        ["input", "detector_file_rows", len(i01), "I01 and I06 exact same historical file universe."],
        ["alignment", "matched_file_rows", len(joined), "Exact snapshot/path matches."],
        ["alignment", "j01_only_file_rows", len(j01_only), "Never path-remapped."],
        ["alignment", "detector_only_file_rows", len(detector_only), "No J01 complexity measurement."],
        ["panel", "repo_month_rows_per_scope_threshold", len(b06), "Authoritative B06 panel."],
        ["panel", "npr_thresholds", len(npr_spec), "Frozen I02 grid."],
        ["panel", "ml_thresholds", len(ml_spec), "Corrected I07-v2 grid."],
        ["panel", "long_rows", len(panel), "Includes all_python reference scope."],
        ["method", "npr_metric", NPR_METRIC, "Strict >; non-finite unclassified."],
        ["method", "ml_metric", ML_METRIC, "Exact integer token-ratio strict >."],
        ["method", "primary_complexity_outcome", "log1p_selected_cognitive_complexity", "File complexity summed before log1p."],
        ["method", "normalization_robustness", "selected_complexity_per_kloc", "Blank when selected NCLOC is zero."],
    ], columns=["section", "metric", "value", "note"])
    atomic_csv(summary, summary_out)

    metadata = {
        "run": SCRIPT_VERSION,
        "status": status,
        "hard_qc_failures": hard_failures,
        "inputs": {
            "j01_file": str(args.j01_file), "j01_file_sha256": sha256_file(args.j01_file),
            "j01_snapshot_file": str(args.j01_snapshot_file), "j01_snapshot_file_sha256": sha256_file(args.j01_snapshot_file),
            "i01_file": str(args.i01_file), "i01_file_sha256": sha256_file(args.i01_file),
            "i06_file": str(args.i06_file), "i06_file_sha256": sha256_file(args.i06_file),
            "i02_threshold_spec_file": str(args.i02_threshold_spec_file), "i02_threshold_spec_sha256": sha256_file(args.i02_threshold_spec_file),
            "i07_threshold_spec_file": str(args.i07_threshold_spec_file), "i07_threshold_spec_sha256": sha256_file(args.i07_threshold_spec_file),
            "b06_file": str(args.b06_file), "b06_file_sha256": sha256_file(args.b06_file),
        },
        "semantics": {
            "file_join": "exact snapshot identity + repository-relative path; dataset/repo/commit safety checks",
            "path_remapping": False,
            "sonarqube_rescan": False,
            "detector_rescoring": False,
            "treatment_effect_estimation": False,
            "npr_unclassified_policy": "non-finite NPR remains unclassified",
            "ml_unclassified_policy": "non-scored ML remains unclassified",
            "ml_boundary_policy": "exact integer token-ratio comparison from corrected I07-v2",
            "complexity_burden": "sum file cognitive complexity within selected file scope, then log1p",
        },
        "scope_audit": {
            "matched_file_rows": len(joined),
            "j01_only_file_rows": len(j01_only),
            "detector_only_file_rows": len(detector_only),
        },
        "outputs": {
            "file_join": str(join_out), "j01_only": str(j01_only_out), "detector_only": str(detector_only_out),
            "alignment_by_snapshot": str(align_out), "threshold_global_audit": str(audit_out),
            "repo_month_panel": str(panel_out), "qc": str(qc_out), "summary": str(summary_out),
        },
    }
    atomic_json(metadata, metadata_out)

    print("=" * 80)
    print(f"{SCRIPT_VERSION} SonarQube cognitive-complexity detector panel summary")
    print(f"Status:                              {status}")
    print(f"J01 file rows:                       {len(j01)}")
    print(f"Detector historical file rows:       {len(i01)}")
    print(f"Exact matched file rows:              {len(joined)}")
    print(f"J01-only file rows:                   {len(j01_only)}")
    print(f"Detector-only file rows:              {len(detector_only)}")
    print(f"NPR / ML thresholds:                  {len(npr_spec)} / {len(ml_spec)}")
    print(f"Long repo-month panel rows:           {len(panel)}")
    print(f"Hard QC failures:                     {hard_failures}")
    print(f"Panel output:                          {panel_out}")
    print(f"Global threshold audit:               {audit_out}")
    print(f"QC output:                             {qc_out}")
    print("=" * 80)
    return 1 if hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
