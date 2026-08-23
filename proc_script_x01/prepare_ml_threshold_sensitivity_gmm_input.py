#!/usr/bin/env python3
"""Prepare ML file-composition threshold panels for run-x-g08.

This script reuses the validated A04/D02/B06/D05 lineage and builds a
zero-inclusive repo-month quality panel for 21 strict file-level ML AGC-share
cutoffs from 0.10 through 0.90 in increments of 0.04. The function-level SVM decision boundary is
never changed. Only the downstream file-composition cutoff is varied.

Primary scientific contract
----------------------------
- ML file metric: file_ml_agc_share_space_by_token_weighted
- File selection: finite ML share > threshold
- Sensitivity grid: 0.10, 0.14, ..., 0.50, ..., 0.86, 0.90
- Primary file-composition cutoff remains strict > 0.50
- Files without a finite ML share remain unclassified and are never selected
- The 0.50 repo-month burden must exactly reproduce the validated D05 primary
  configuration before downstream GMM estimation is allowed

Outputs
-------
ml_threshold_repo_month_panel.csv.gz
ml_threshold_support.csv
ml_threshold_reproduction_audit.csv
ml_threshold_qc.csv
ml_threshold_metadata.csv
"""

from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

IMPLEMENTATION_VERSION = "v2"
EXPERIMENT_NAME = "run-x-g08-dynamic-panel-gmm-ml-threshold-sensitivity"
ML_METRIC = "file_ml_agc_share_space_by_token_weighted"
PRIMARY_THRESHOLD = 0.50
STRICT_OPERATOR = ">"
DEFAULT_THRESHOLDS = tuple(round(0.10 + 0.04 * index, 2) for index in range(21))
FILE_KEYS = ("snapshot_id", "relative_path", "file_sha256")
REPO_TIME_KEYS = ("repo_id", "time_index")
JOIN_SHA_COLUMN = "_file_sha256_join"
JOIN_FILE_KEYS = ("snapshot_id", "relative_path", JOIN_SHA_COLUMN)
MISSING_SHA_SENTINEL = "__MISSING_FILE_SHA256__"


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


def parse_thresholds(text: str) -> list[float]:
    values: list[float] = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        value = float(token)
        if not 0.0 <= value <= 1.0:
            abort(f"Threshold must lie in [0,1]: {value}")
        values.append(value)
    if not values:
        abort("At least one threshold is required")
    if len(values) != len(set(values)):
        abort("Threshold values must be unique")
    values = sorted(values)
    if not any(math.isclose(value, PRIMARY_THRESHOLD, abs_tol=1e-12) for value in values):
        abort("Threshold grid must contain the primary file-composition cutoff 0.50")
    return values


def threshold_id(value: float) -> str:
    return f"t{int(round(value * 100)):02d}"


def normalize_repo_time_keys(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    out = frame.copy()
    require_columns(out, REPO_TIME_KEYS, label)
    out["repo_id"] = pd.to_numeric(out["repo_id"], errors="raise").astype(int)
    out["time_index"] = pd.to_numeric(out["time_index"], errors="raise").astype(int)
    if out[list(REPO_TIME_KEYS)].isna().any().any():
        abort(f"{label} contains missing repo_id/time_index keys")
    return out


def normalize_file_keys(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    """Normalize canonical file keys while preserving legitimate missing SHA rows."""
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


def audit_missing_sha_identity(a04: pd.DataFrame, unique_d02: pd.DataFrame) -> dict[str, int]:
    a04_missing = a04.loc[a04["file_sha256"].isna(), ["snapshot_id", "relative_path"]].copy()
    d02_missing = unique_d02.loc[
        unique_d02["file_sha256"].isna(), ["snapshot_id", "relative_path"]
    ].copy()
    if a04_missing.duplicated(["snapshot_id", "relative_path"]).any():
        abort("A04 missing-SHA rows are not unique by snapshot_id + relative_path")
    if d02_missing.duplicated(["snapshot_id", "relative_path"]).any():
        abort("D02 missing-SHA rows are not unique by snapshot_id + relative_path")
    comparison = d02_missing.merge(
        a04_missing,
        on=["snapshot_id", "relative_path"],
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    return {
        "a04_missing_sha_files": int(len(a04_missing)),
        "d02_missing_sha_files": int(len(d02_missing)),
        "d02_only_missing_sha_keys": int((comparison["_merge"] == "left_only").sum()),
        "a04_only_missing_sha_keys": int((comparison["_merge"] == "right_only").sum()),
    }


def extract_d05_primary(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if "primary_analysis" in data.columns:
        primary = pd.to_numeric(data["primary_analysis"], errors="coerce") == 1
        data = data.loc[primary].copy()
    else:
        require_columns(data, ["sample_spec", "mapping_spec"], "D05 reference")
        data = data.loc[
            (data["sample_spec"].astype(str) == "full_sample")
            & (data["mapping_spec"].astype(str) == "all_ml_files")
        ].copy()
    if data.empty:
        abort("D05 primary-reference filter produced zero rows")
    if "selected_file_rows" not in data.columns:
        if "selected_file_count" in data.columns:
            data["selected_file_rows"] = data["selected_file_count"]
        else:
            abort("D05 reference is missing selected_file_rows/selected_file_count")
    required = [
        "repo_id", "time_index", "selected_file_rows", "selected_issue_total",
        "log1p_selected_issue_total",
    ]
    require_columns(data, required, "D05 reference")
    data = normalize_repo_time_keys(data, "D05 reference")
    for column in ("selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"):
        data[column] = pd.to_numeric(data[column], errors="raise")
    if data.duplicated(list(REPO_TIME_KEYS)).any():
        abort("D05 primary reference contains duplicate repo-month keys")
    return data[required]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a04-file", required=True, type=Path)
    parser.add_argument("--d02-file", required=True, type=Path)
    parser.add_argument("--b06-file", required=True, type=Path)
    parser.add_argument("--d05-reference-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--thresholds", default=",".join(f"{value:.2f}" for value in DEFAULT_THRESHOLDS))
    parser.add_argument("--expected-a04-rows", type=int, default=494592)
    parser.add_argument("--expected-d02-rows", type=int, default=510297)
    parser.add_argument("--expected-d02-unique-files", type=int, default=494592)
    parser.add_argument("--expected-b06-rows", type=int, default=1954)
    parser.add_argument("--expected-eligible-rows", type=int, default=204509)
    parser.add_argument("--expected-eligible-unique-files", type=int, default=196644)
    parser.add_argument("--expected-primary-selected-rows", type=int, default=43325)
    parser.add_argument("--expected-primary-selected-unique-files", type=int, default=41905)
    parser.add_argument("--expected-primary-issue-stock", type=float, default=48478.0)
    args = parser.parse_args()

    thresholds = parse_thresholds(args.thresholds)
    expected_grid = list(DEFAULT_THRESHOLDS)
    if len(thresholds) != len(expected_grid) or any(
        not math.isclose(left, right, abs_tol=1e-12)
        for left, right in zip(thresholds, expected_grid)
    ):
        abort(f"G08 requires exact grid {expected_grid}; observed {thresholds}")

    for path in (args.a04_file, args.d02_file, args.b06_file, args.d05_reference_file):
        if not path.is_file():
            abort(f"Required input does not exist: {path}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading A04 ML file scores: {args.a04_file}")
    a04 = normalize_file_keys(read_table(args.a04_file), "A04")
    print(f"Reading D02 canonical file burden: {args.d02_file}")
    d02 = normalize_file_keys(normalize_repo_time_keys(read_table(args.d02_file), "D02"), "D02")
    print(f"Reading B06 authoritative panel: {args.b06_file}")
    b06 = normalize_repo_time_keys(read_table(args.b06_file), "B06")
    print(f"Reading D05 primary reference: {args.d05_reference_file}")
    d05_reference = extract_d05_primary(read_table(args.d05_reference_file))

    if len(a04) != args.expected_a04_rows:
        abort(f"A04 row mismatch: expected {args.expected_a04_rows}, observed {len(a04)}")
    if len(d02) != args.expected_d02_rows:
        abort(f"D02 row mismatch: expected {args.expected_d02_rows}, observed {len(d02)}")
    if len(b06) != args.expected_b06_rows:
        abort(f"B06 row mismatch: expected {args.expected_b06_rows}, observed {len(b06)}")
    if len(d05_reference) != args.expected_b06_rows:
        abort(f"D05 primary row mismatch: expected {args.expected_b06_rows}, observed {len(d05_reference)}")

    require_columns(a04, [ML_METRIC], "A04")
    require_columns(d02, ["sonar_issue_total"], "D02")
    if a04.duplicated(list(JOIN_FILE_KEYS)).any():
        abort("A04 contains duplicate historical-file keys after missing-SHA normalization")
    if b06.duplicated(list(REPO_TIME_KEYS)).any():
        abort("B06 contains duplicate repo-month keys")

    a04[ML_METRIC] = pd.to_numeric(a04[ML_METRIC], errors="coerce")
    d02["sonar_issue_total"] = pd.to_numeric(d02["sonar_issue_total"], errors="raise")
    if d02["sonar_issue_total"].isna().any() or (d02["sonar_issue_total"] < 0).any():
        abort("D02 sonar_issue_total must be complete and non-negative")

    unique_d02 = d02[list(FILE_KEYS) + [JOIN_SHA_COLUMN]].drop_duplicates(subset=list(JOIN_FILE_KEYS))
    if len(unique_d02) != args.expected_d02_unique_files:
        abort(
            f"D02 unique-file mismatch: expected {args.expected_d02_unique_files}, "
            f"observed {len(unique_d02)}"
        )

    missing_sha = audit_missing_sha_identity(a04, unique_d02)
    if missing_sha["d02_only_missing_sha_keys"] or missing_sha["a04_only_missing_sha_keys"]:
        abort(
            "A04/D02 missing-SHA identity mismatch: "
            f"d02_only={missing_sha['d02_only_missing_sha_keys']}, "
            f"a04_only={missing_sha['a04_only_missing_sha_keys']}"
        )

    identity = unique_d02[list(JOIN_FILE_KEYS)].merge(
        a04[list(JOIN_FILE_KEYS)],
        on=list(JOIN_FILE_KEYS),
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    d02_only = int((identity["_merge"] == "left_only").sum())
    a04_only = int((identity["_merge"] == "right_only").sum())
    if d02_only or a04_only:
        abort(f"A04/D02 historical-file identity mismatch: d02_only={d02_only}, a04_only={a04_only}")

    base = d02.merge(
        a04[list(JOIN_FILE_KEYS) + [ML_METRIC]],
        on=list(JOIN_FILE_KEYS),
        how="left",
        validate="many_to_one",
    )
    if len(base) != len(d02):
        abort(f"A04/D02 expanded join changed row count: before={len(d02)}, after={len(base)}")

    eligible = base[ML_METRIC].notna() & np.isfinite(base[ML_METRIC])
    eligible_rows = int(eligible.sum())
    eligible_unique = int(base.loc[eligible, list(JOIN_FILE_KEYS)].drop_duplicates().shape[0])
    if eligible_rows != args.expected_eligible_rows:
        abort(f"Eligible-row mismatch: expected {args.expected_eligible_rows}, observed {eligible_rows}")
    if eligible_unique != args.expected_eligible_unique_files:
        abort(
            f"Eligible unique-file mismatch: expected {args.expected_eligible_unique_files}, "
            f"observed {eligible_unique}"
        )

    panels: list[pd.DataFrame] = []
    support_rows: list[dict[str, object]] = []
    for threshold in thresholds:
        selected = eligible & (base[ML_METRIC] > threshold)
        selected_rows = base.loc[selected, ["repo_id", "time_index", "sonar_issue_total"]].copy()
        agg = selected_rows.groupby(["repo_id", "time_index"], as_index=False).agg(
            selected_file_rows=("sonar_issue_total", "size"),
            selected_issue_total=("sonar_issue_total", "sum"),
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
        panels.append(panel)

        support_rows.append({
            "threshold_id": threshold_id(threshold),
            "threshold": float(threshold),
            "primary_analysis": int(math.isclose(threshold, PRIMARY_THRESHOLD, abs_tol=1e-12)),
            "source_repo_month_rows": int(len(panel)),
            "selected_file_rows": int(selected.sum()),
            "selected_unique_historical_files": int(
                base.loc[selected, list(JOIN_FILE_KEYS)].drop_duplicates().shape[0]
            ),
            "selected_issue_total": float(panel["selected_issue_total"].sum()),
            "zero_issue_repo_month_share": float((panel["selected_issue_total"] == 0).mean()),
            "repositories_with_within_quality_variation": int(
                panel.groupby("repo_id")["log1p_selected_issue_total"].nunique().gt(1).sum()
            ),
        })

    long_panel = pd.concat(panels, ignore_index=True)
    support = pd.DataFrame(support_rows).sort_values("threshold").reset_index(drop=True)
    expected_long_rows = args.expected_b06_rows * len(thresholds)
    if len(long_panel) != expected_long_rows:
        abort(f"Long-panel row mismatch: expected {expected_long_rows}, observed {len(long_panel)}")

    for metric in ("selected_file_rows", "selected_unique_historical_files", "selected_issue_total"):
        values = support[metric].to_numpy(dtype=float)
        if np.any(np.diff(values) > 1e-9):
            abort(f"Threshold support is not monotone non-increasing for {metric}: {values}")

    primary_support = support.loc[np.isclose(support["threshold"], PRIMARY_THRESHOLD)].copy()
    if len(primary_support) != 1:
        abort("Expected exactly one primary 0.50 support row")
    primary_row = primary_support.iloc[0]
    if int(primary_row["selected_file_rows"]) != args.expected_primary_selected_rows:
        abort("Primary expanded selected-file count does not reproduce D05")
    if int(primary_row["selected_unique_historical_files"]) != args.expected_primary_selected_unique_files:
        abort("Primary unique selected-file count does not reproduce A04/D05")
    if not math.isclose(float(primary_row["selected_issue_total"]), args.expected_primary_issue_stock, abs_tol=1e-9):
        abort("Primary selected issue stock does not reproduce D05")

    t50 = long_panel.loc[np.isclose(long_panel["ml_threshold"], PRIMARY_THRESHOLD)].copy()
    reproduction = d05_reference.merge(
        t50[["repo_id", "time_index", "selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"]],
        on=["repo_id", "time_index"],
        suffixes=("_reference", "_new"),
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    key_mismatch = int((reproduction["_merge"] != "both").sum())
    file_mismatch = int((~np.isclose(
        reproduction["selected_file_rows_reference"], reproduction["selected_file_rows_new"],
        atol=0, rtol=0, equal_nan=False,
    )).sum())
    issue_mismatch = int((~np.isclose(
        reproduction["selected_issue_total_reference"], reproduction["selected_issue_total_new"],
        atol=1e-9, rtol=0, equal_nan=False,
    )).sum())
    log_mismatch = int((~np.isclose(
        reproduction["log1p_selected_issue_total_reference"],
        reproduction["log1p_selected_issue_total_new"],
        atol=1e-12, rtol=0, equal_nan=False,
    )).sum())
    if key_mismatch + file_mismatch + issue_mismatch + log_mismatch:
        abort(
            "Primary 0.50 D05 reproduction failed: "
            f"key={key_mismatch}, files={file_mismatch}, issues={issue_mismatch}, log={log_mismatch}"
        )

    output_panel = args.output_dir / "ml_threshold_repo_month_panel.csv.gz"
    output_support = args.output_dir / "ml_threshold_support.csv"
    output_reproduction = args.output_dir / "ml_threshold_reproduction_audit.csv"
    output_qc = args.output_dir / "ml_threshold_qc.csv"
    output_metadata = args.output_dir / "ml_threshold_metadata.csv"

    long_panel.to_csv(output_panel, index=False, compression="gzip")
    support.to_csv(output_support, index=False)
    pd.DataFrame([{
        "threshold": PRIMARY_THRESHOLD,
        "repo_month_rows": len(t50),
        "key_mismatches": key_mismatch,
        "selected_file_row_mismatches": file_mismatch,
        "selected_issue_total_mismatches": issue_mismatch,
        "log1p_outcome_mismatches": log_mismatch,
        "status": "pass",
    }]).to_csv(output_reproduction, index=False)

    qc_rows = [
        ("a04_rows", len(a04), args.expected_a04_rows, "pass"),
        ("d02_rows", len(d02), args.expected_d02_rows, "pass"),
        ("d02_unique_files", len(unique_d02), args.expected_d02_unique_files, "pass"),
        ("b06_rows", len(b06), args.expected_b06_rows, "pass"),
        ("threshold_count", len(thresholds), 9, "pass"),
        ("long_panel_rows", len(long_panel), expected_long_rows, "pass"),
        ("eligible_rows", eligible_rows, args.expected_eligible_rows, "pass"),
        ("eligible_unique_files", eligible_unique, args.expected_eligible_unique_files, "pass"),
        ("a04_missing_sha_files", missing_sha["a04_missing_sha_files"], missing_sha["d02_missing_sha_files"], "pass"),
        ("missing_sha_identity_mismatches", missing_sha["d02_only_missing_sha_keys"] + missing_sha["a04_only_missing_sha_keys"], 0, "pass"),
        ("d02_only_file_keys", d02_only, 0, "pass"),
        ("a04_only_file_keys", a04_only, 0, "pass"),
        ("primary_selected_file_rows", int(primary_row["selected_file_rows"]), args.expected_primary_selected_rows, "pass"),
        ("primary_selected_unique_files", int(primary_row["selected_unique_historical_files"]), args.expected_primary_selected_unique_files, "pass"),
        ("primary_issue_stock", float(primary_row["selected_issue_total"]), args.expected_primary_issue_stock, "pass"),
        ("primary_d05_reproduction_mismatches", key_mismatch + file_mismatch + issue_mismatch + log_mismatch, 0, "pass"),
    ]
    pd.DataFrame(qc_rows, columns=["check", "observed", "expected", "status"]).to_csv(output_qc, index=False)

    metadata = pd.DataFrame([
        ("experiment_name", EXPERIMENT_NAME),
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
        ("threshold_grid", ",".join(f"{value:.2f}" for value in thresholds)),
        ("primary_threshold", f"{PRIMARY_THRESHOLD:.2f}"),
        ("threshold_interpretation", "file-level token-weighted AGC composition cutoff"),
        ("function_level_classifier_boundary", "unchanged frozen SVM decision boundary"),
        ("selection_policy", "report all thresholds; never choose threshold using downstream GMM significance"),
    ], columns=["metric", "value"])
    metadata.to_csv(output_metadata, index=False)

    print("run-x-g08 ML threshold GMM input: PASS")
    print(f"Thresholds: {','.join(f'{value:.2f}' for value in thresholds)}")
    print(f"Eligible expanded file rows: {eligible_rows}")
    print(f"Eligible unique historical files: {eligible_unique}")
    print(
        "A04/D02 missing file_sha256 files: "
        f"{missing_sha['a04_missing_sha_files']}/{missing_sha['d02_missing_sha_files']} "
        "(identity mismatches=0)"
    )
    print(
        "Primary >0.50 reproduction: "
        f"files={int(primary_row['selected_file_rows'])}, "
        f"unique={int(primary_row['selected_unique_historical_files'])}, "
        f"issues={float(primary_row['selected_issue_total']):.0f}, repo-month mismatches=0"
    )
    print(f"Output panel: {output_panel}")


if __name__ == "__main__":
    main()
