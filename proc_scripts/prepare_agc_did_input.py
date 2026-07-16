#!/usr/bin/env python3
"""Prepare repository-month AGC outcomes for the strict Python DiD panel.

The script combines validated block-level detector outputs with the exact
repository-month snapshot manifest, verifies the reconstructed top-level block
outcomes against the detector's existing repository-month outputs, and then
left-joins the AGC outcomes to the strict matched DiD panel.

The primary outcome is the share of scored top-level Python function and class
blocks classified as AI-generated-like. Function-only and class-only shares are
also retained as secondary outcomes. These outcomes capture structural
similarity to AI-generated code in the detector's training distribution; they
do not establish code provenance or identify a specific AI tool.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


KEY_COLS = ["repo_name", "time", "dataset_source"]
MANIFEST_KEY_COLS = ["dataset_source", "repo_name", "month"]
COMMIT_KEY_COLS = ["dataset_source", "repo_name", "commit"]
ALLOWED_SOURCES = {"treatment", "control"}
ALLOWED_BLOCK_KINDS = {"function_definition", "class_definition"}

PANEL_IDENTITY_COLS = [
    "repo_name",
    "time",
    "dataset_source",
    "is_treatment",
]

EVENT_COLS = [
    "event",
    "post_event",
    "time_to_event",
    "lead_6",
    "lead_5",
    "lead_4",
    "lead_3",
    "lead_2",
    "lead_1",
    "lag_0",
    "lag_1",
    "lag_2",
    "lag_3",
    "lag_4",
    "lag_5",
    "lag_6",
    "cursor",
]

ACTIVITY_COLS = [
    "commits",
    "lines_added",
    "lines_removed",
    "contributors",
]

COVARIATE_COLS = [
    "stars",
    "issues",
    "age",
    "ncloc",
]

SNAPSHOT_AUDIT_COLS = [
    "latest_commit",
    "python_file_count",
    "files_analyzed",
    "failure_count",
    "agc_analysis_status",
    "agc_repo_month_matched",
]

TOP_LEVEL_COLS = [
    "top_level_blocks_scored",
    "agc_top_level_blocks",
    "human_top_level_blocks",
    "agc_top_level_block_ratio",
]

FUNCTION_COLS = [
    "function_blocks_scored",
    "agc_function_blocks",
    "human_function_blocks",
    "agc_function_block_ratio",
]

CLASS_COLS = [
    "class_blocks_scored",
    "agc_class_blocks",
    "human_class_blocks",
    "agc_class_block_ratio",
]

OUTPUT_COLS = (
    PANEL_IDENTITY_COLS
    + EVENT_COLS
    + ACTIVITY_COLS
    + COVARIATE_COLS
    + SNAPSHOT_AUDIT_COLS
    + TOP_LEVEL_COLS
    + FUNCTION_COLS
    + CLASS_COLS
)

COUNT_COLS = [
    "top_level_blocks_scored",
    "agc_top_level_blocks",
    "human_top_level_blocks",
    "function_blocks_scored",
    "agc_function_blocks",
    "human_function_blocks",
    "class_blocks_scored",
    "agc_class_blocks",
    "human_class_blocks",
]

RATIO_COLS = [
    "agc_top_level_block_ratio",
    "agc_function_block_ratio",
    "agc_class_block_ratio",
]

METADATA_COMPARE_FIELDS = [
    "experiment",
    "classifier",
    "representation",
    "model_sha256",
    "model_key",
    "embedding_model_id",
    "max_len",
    "threshold_effective",
    "expected_score_mode",
]


def setup_logging() -> None:
    """Configure console logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Prepare strict repository-month AGC DiD input."
    )
    parser.add_argument("--base-panel", required=True, type=Path)
    parser.add_argument("--snapshot-manifest", required=True, type=Path)
    parser.add_argument("--block-treatment", required=True, type=Path)
    parser.add_argument("--block-control", required=True, type=Path)
    parser.add_argument("--repo-month-treatment", required=True, type=Path)
    parser.add_argument("--repo-month-control", required=True, type=Path)
    parser.add_argument("--run-metadata-treatment", required=True, type=Path)
    parser.add_argument("--run-metadata-control", required=True, type=Path)
    parser.add_argument("--combined-validation", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--qc-dir", required=True, type=Path)
    parser.add_argument("--panel-label", default="strict")
    parser.add_argument(
        "--chunksize",
        type=int,
        default=250_000,
        help="Rows per block-prediction CSV chunk. Default: 250000.",
    )
    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    """Fail clearly when an input file is missing."""
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


def require_columns(df: pd.DataFrame, required: Iterable[str], label: str) -> None:
    """Require a set of columns in a DataFrame."""
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")


def require_unique(df: pd.DataFrame, keys: list[str], label: str) -> None:
    """Fail when a key is duplicated."""
    duplicate_count = int(df.duplicated(keys).sum())
    if duplicate_count:
        sample = df.loc[df.duplicated(keys, keep=False), keys].head(20)
        raise ValueError(
            f"{label} has {duplicate_count} duplicate rows for key {keys}.\n"
            f"Sample:\n{sample.to_string(index=False)}"
        )


def normalize_month_value(value: object) -> str:
    """Normalize a month value to YYYY-MM when possible."""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if len(text) == 6 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}"
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    return text


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Compute a ratio while preserving missingness for zero denominators."""
    numerator_numeric = pd.to_numeric(numerator, errors="coerce")
    denominator_numeric = pd.to_numeric(denominator, errors="coerce")
    result = pd.Series(np.nan, index=denominator.index, dtype="float64")
    valid = denominator_numeric.gt(0)
    result.loc[valid] = numerator_numeric.loc[valid] / denominator_numeric.loc[valid]
    return result


def atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write a CSV atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        df.to_csv(handle, index=False)
    os.replace(temp_path, path)


def load_json(path: Path, label: str) -> dict[str, Any]:
    """Load a JSON object."""
    require_file(path, label)
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def validate_detector_metadata(
    treatment_path: Path,
    control_path: Path,
    combined_validation_path: Path,
) -> pd.DataFrame:
    """Validate detector provenance and return a comparison table."""
    combined = load_json(combined_validation_path, "combined detector validation")
    if combined.get("status") != "PASS":
        raise ValueError(
            "Combined detector validation is not PASS: "
            f"{combined_validation_path}"
        )
    if combined.get("metadata_comparison_errors") not in ([], None):
        raise ValueError(
            "Combined detector validation reports metadata mismatches: "
            f"{combined.get('metadata_comparison_errors')}"
        )

    treatment = load_json(treatment_path, "treatment run metadata")
    control = load_json(control_path, "control run metadata")

    rows: list[dict[str, Any]] = []
    mismatches: list[str] = []
    for field in METADATA_COMPARE_FIELDS:
        treatment_value = treatment.get(field)
        control_value = control.get(field)
        matches = treatment_value == control_value
        rows.append(
            {
                "field": field,
                "treatment_value": treatment_value,
                "control_value": control_value,
                "matches": int(matches),
            }
        )
        if not matches:
            mismatches.append(
                f"{field}: treatment={treatment_value!r}, control={control_value!r}"
            )

    if mismatches:
        raise ValueError("Detector metadata mismatch: " + "; ".join(mismatches))

    return pd.DataFrame(rows)


def aggregate_block_file(path: Path, source: str, chunksize: int) -> pd.DataFrame:
    """Aggregate one large block-prediction CSV to commit and block kind."""
    require_file(path, f"{source} block predictions")
    usecols = [
        "dataset_source",
        "repo_name",
        "commit",
        "block_kind",
        "predicted_agc",
    ]
    partials: list[pd.DataFrame] = []
    total_rows = 0

    for chunk_number, chunk in enumerate(
        pd.read_csv(path, usecols=usecols, chunksize=chunksize, low_memory=False),
        start=1,
    ):
        total_rows += len(chunk)
        if not chunk["dataset_source"].eq(source).all():
            bad = sorted(chunk.loc[chunk["dataset_source"] != source, "dataset_source"].dropna().astype(str).unique())
            raise ValueError(
                f"{source} block file contains unexpected dataset_source values: {bad}"
            )

        unexpected_kinds = sorted(
            set(chunk["block_kind"].dropna().astype(str)) - ALLOWED_BLOCK_KINDS
        )
        if unexpected_kinds:
            raise ValueError(
                f"{source} block file contains unexpected block_kind values: "
                f"{unexpected_kinds}"
            )

        predicted = pd.to_numeric(chunk["predicted_agc"], errors="coerce")
        invalid = ~predicted.isin([0, 1])
        if invalid.any():
            raise ValueError(
                f"{source} block file has {int(invalid.sum())} invalid predicted_agc values"
            )
        chunk["predicted_agc"] = predicted.astype("int64")
        chunk["human_prediction"] = 1 - chunk["predicted_agc"]

        grouped = (
            chunk.groupby(COMMIT_KEY_COLS + ["block_kind"], as_index=False)
            .agg(
                blocks_scored=("predicted_agc", "size"),
                agc_blocks=("predicted_agc", "sum"),
                human_blocks=("human_prediction", "sum"),
            )
        )
        partials.append(grouped)
        logging.info(
            "%s block aggregation chunk %d: rows=%d cumulative=%d",
            source,
            chunk_number,
            len(chunk),
            total_rows,
        )

    if not partials:
        return pd.DataFrame(
            columns=COMMIT_KEY_COLS
            + ["block_kind", "blocks_scored", "agc_blocks", "human_blocks"]
        )

    combined = pd.concat(partials, ignore_index=True)
    combined = (
        combined.groupby(COMMIT_KEY_COLS + ["block_kind"], as_index=False)[
            ["blocks_scored", "agc_blocks", "human_blocks"]
        ]
        .sum()
    )
    logging.info("%s block rows aggregated: %d", source, total_rows)
    return combined


def make_commit_wide(block_aggregates: pd.DataFrame) -> pd.DataFrame:
    """Convert function/class commit aggregates to one row per commit."""
    function_df = block_aggregates.loc[
        block_aggregates["block_kind"] == "function_definition",
        COMMIT_KEY_COLS + ["blocks_scored", "agc_blocks", "human_blocks"],
    ].rename(
        columns={
            "blocks_scored": "function_blocks_scored",
            "agc_blocks": "agc_function_blocks",
            "human_blocks": "human_function_blocks",
        }
    )

    class_df = block_aggregates.loc[
        block_aggregates["block_kind"] == "class_definition",
        COMMIT_KEY_COLS + ["blocks_scored", "agc_blocks", "human_blocks"],
    ].rename(
        columns={
            "blocks_scored": "class_blocks_scored",
            "agc_blocks": "agc_class_blocks",
            "human_blocks": "human_class_blocks",
        }
    )

    commit_wide = function_df.merge(
        class_df,
        on=COMMIT_KEY_COLS,
        how="outer",
        validate="one_to_one",
    )

    kind_count_cols = FUNCTION_COLS[:3] + CLASS_COLS[:3]
    for column in kind_count_cols:
        if column not in commit_wide.columns:
            commit_wide[column] = 0
        commit_wide[column] = pd.to_numeric(
            commit_wide[column], errors="coerce"
        ).fillna(0).astype("int64")

    commit_wide["top_level_blocks_scored"] = (
        commit_wide["function_blocks_scored"]
        + commit_wide["class_blocks_scored"]
    )
    commit_wide["agc_top_level_blocks"] = (
        commit_wide["agc_function_blocks"] + commit_wide["agc_class_blocks"]
    )
    commit_wide["human_top_level_blocks"] = (
        commit_wide["human_function_blocks"] + commit_wide["human_class_blocks"]
    )

    return commit_wide


def load_snapshot_manifest(path: Path) -> pd.DataFrame:
    """Load and validate the exact repository-month snapshot manifest."""
    require_file(path, "snapshot manifest")
    manifest = pd.read_csv(path, low_memory=False, dtype={"latest_commit": "string"})
    required = MANIFEST_KEY_COLS + [
        "latest_commit",
        "python_file_count",
        "has_python_files",
    ]
    require_columns(manifest, required, "snapshot manifest")
    manifest["repo_name"] = manifest["repo_name"].astype(str)
    manifest["dataset_source"] = manifest["dataset_source"].astype(str)
    manifest["month"] = manifest["month"].map(normalize_month_value)
    manifest["latest_commit"] = manifest["latest_commit"].astype(str)

    invalid_sources = sorted(set(manifest["dataset_source"]) - ALLOWED_SOURCES)
    if invalid_sources:
        raise ValueError(f"Snapshot manifest has invalid sources: {invalid_sources}")
    require_unique(manifest, MANIFEST_KEY_COLS, "snapshot manifest")
    return manifest


def expand_commit_outcomes_to_month(
    manifest: pd.DataFrame,
    commit_wide: pd.DataFrame,
) -> pd.DataFrame:
    """Expand unique commit outcomes to all repository-month manifest rows."""
    join_right = commit_wide.rename(columns={"commit": "latest_commit"})
    outcomes = manifest.merge(
        join_right,
        on=["dataset_source", "repo_name", "latest_commit"],
        how="left",
        validate="many_to_one",
        indicator="__commit_match",
    )

    for column in COUNT_COLS:
        if column not in outcomes.columns:
            outcomes[column] = 0
        outcomes[column] = pd.to_numeric(outcomes[column], errors="coerce").fillna(0).astype("int64")

    outcomes["agc_top_level_block_ratio"] = safe_ratio(
        outcomes["agc_top_level_blocks"], outcomes["top_level_blocks_scored"]
    )
    outcomes["agc_function_block_ratio"] = safe_ratio(
        outcomes["agc_function_blocks"], outcomes["function_blocks_scored"]
    )
    outcomes["agc_class_block_ratio"] = safe_ratio(
        outcomes["agc_class_blocks"], outcomes["class_blocks_scored"]
    )

    return outcomes


def load_repo_month_oracle(
    treatment_path: Path,
    control_path: Path,
) -> pd.DataFrame:
    """Load validated detector repository-month outputs used as an oracle."""
    frames: list[pd.DataFrame] = []
    for source, path in (
        ("treatment", treatment_path),
        ("control", control_path),
    ):
        require_file(path, f"{source} repository-month AGC panel")
        frame = pd.read_csv(path, low_memory=False, dtype={"latest_commit": "string"})
        required = [
            "dataset_source",
            "repo_name",
            "month",
            "latest_commit",
            "python_file_count",
            "analysis_status",
            "blocks_scored",
            "human_blocks",
            "agc_blocks",
            "agc_block_ratio",
            "files_analyzed",
            "failure_count",
        ]
        require_columns(frame, required, f"{source} repository-month AGC panel")
        if not frame["dataset_source"].astype(str).eq(source).all():
            raise ValueError(
                f"{source} repository-month AGC panel contains another source"
            )
        frames.append(frame)

    oracle = pd.concat(frames, ignore_index=True)
    oracle["repo_name"] = oracle["repo_name"].astype(str)
    oracle["dataset_source"] = oracle["dataset_source"].astype(str)
    oracle["month"] = oracle["month"].map(normalize_month_value)
    oracle["latest_commit"] = oracle["latest_commit"].astype(str)
    require_unique(oracle, MANIFEST_KEY_COLS, "combined repository-month AGC oracle")
    return oracle


def compare_reconstructed_with_oracle(
    reconstructed: pd.DataFrame,
    oracle: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate reconstructed all-block outcomes against existing outputs."""
    manifest_keys = reconstructed[MANIFEST_KEY_COLS]
    oracle_keys = oracle[MANIFEST_KEY_COLS]
    key_check = manifest_keys.merge(
        oracle_keys,
        on=MANIFEST_KEY_COLS,
        how="outer",
        indicator=True,
    )
    if not key_check["_merge"].eq("both").all():
        raise ValueError(
            "Snapshot manifest and repository-month detector outputs do not have "
            "the same keys"
        )

    oracle_selected = oracle[
        MANIFEST_KEY_COLS
        + [
            "latest_commit",
            "python_file_count",
            "analysis_status",
            "blocks_scored",
            "human_blocks",
            "agc_blocks",
            "agc_block_ratio",
            "files_analyzed",
            "failure_count",
        ]
    ].rename(
        columns={
            "latest_commit": "oracle_latest_commit",
            "python_file_count": "oracle_python_file_count",
            "blocks_scored": "oracle_blocks_scored",
            "human_blocks": "oracle_human_blocks",
            "agc_blocks": "oracle_agc_blocks",
            "agc_block_ratio": "oracle_agc_block_ratio",
        }
    )

    compared = reconstructed.merge(
        oracle_selected,
        on=MANIFEST_KEY_COLS,
        how="inner",
        validate="one_to_one",
    )

    compared["latest_commit_matches"] = (
        compared["latest_commit"].astype(str)
        == compared["oracle_latest_commit"].astype(str)
    )
    compared["python_file_count_matches"] = (
        pd.to_numeric(compared["python_file_count"], errors="coerce")
        == pd.to_numeric(compared["oracle_python_file_count"], errors="coerce")
    )
    compared["top_level_blocks_match"] = (
        compared["top_level_blocks_scored"]
        == pd.to_numeric(compared["oracle_blocks_scored"], errors="coerce")
    )
    compared["agc_top_level_blocks_match"] = (
        compared["agc_top_level_blocks"]
        == pd.to_numeric(compared["oracle_agc_blocks"], errors="coerce")
    )
    compared["human_top_level_blocks_match"] = (
        compared["human_top_level_blocks"]
        == pd.to_numeric(compared["oracle_human_blocks"], errors="coerce")
    )

    left_ratio = pd.to_numeric(
        compared["agc_top_level_block_ratio"], errors="coerce"
    )
    right_ratio = pd.to_numeric(compared["oracle_agc_block_ratio"], errors="coerce")
    compared["top_level_ratio_match"] = np.isclose(
        left_ratio,
        right_ratio,
        rtol=1e-12,
        atol=1e-12,
        equal_nan=True,
    )

    check_cols = [
        "latest_commit_matches",
        "python_file_count_matches",
        "top_level_blocks_match",
        "agc_top_level_blocks_match",
        "human_top_level_blocks_match",
        "top_level_ratio_match",
    ]
    compared["all_checks_pass"] = compared[check_cols].all(axis=1)
    mismatches = compared.loc[~compared["all_checks_pass"]].copy()

    qc_rows = [
        {"check": "reconstructed_repo_month_rows", "value": len(reconstructed)},
        {"check": "oracle_repo_month_rows", "value": len(oracle)},
        {"check": "latest_commit_mismatches", "value": int((~compared["latest_commit_matches"]).sum())},
        {"check": "python_file_count_mismatches", "value": int((~compared["python_file_count_matches"]).sum())},
        {"check": "top_level_block_count_mismatches", "value": int((~compared["top_level_blocks_match"]).sum())},
        {"check": "agc_top_level_count_mismatches", "value": int((~compared["agc_top_level_blocks_match"]).sum())},
        {"check": "human_top_level_count_mismatches", "value": int((~compared["human_top_level_blocks_match"]).sum())},
        {"check": "top_level_ratio_mismatches", "value": int((~compared["top_level_ratio_match"]).sum())},
        {"check": "all_reconstructed_rows_match_oracle", "value": int(mismatches.empty)},
    ]
    qc = pd.DataFrame(qc_rows)

    if not mismatches.empty:
        raise ValueError(
            f"Reconstructed block-kind outcomes disagree with the existing "
            f"repository-month AGC panel for {len(mismatches)} rows"
        )

    outcomes = compared.copy()
    outcomes["agc_analysis_status"] = outcomes["analysis_status"].astype(str)
    outcomes = outcomes.rename(
        columns={
            "oracle_python_file_count": "oracle_python_file_count_for_qc",
        }
    )
    return outcomes, qc


def prepare_outcome_columns(compared: pd.DataFrame) -> pd.DataFrame:
    """Select the validated repository-month outcomes for panel merging."""
    columns = (
        MANIFEST_KEY_COLS
        + [
            "latest_commit",
            "python_file_count",
            "files_analyzed",
            "failure_count",
            "agc_analysis_status",
        ]
        + TOP_LEVEL_COLS
        + FUNCTION_COLS
        + CLASS_COLS
    )
    outcomes = compared[columns].copy()
    outcomes = outcomes.rename(columns={"month": "time"})
    require_unique(outcomes, KEY_COLS, "validated AGC repository-month outcomes")
    return outcomes


def load_base_panel(path: Path) -> pd.DataFrame:
    """Load and validate the strict matched DiD panel."""
    require_file(path, "strict base panel")
    panel = pd.read_csv(path, low_memory=False, dtype={"latest_commit": "string"})
    required = PANEL_IDENTITY_COLS + EVENT_COLS + ACTIVITY_COLS + COVARIATE_COLS
    require_columns(panel, required, "strict base panel")
    panel["repo_name"] = panel["repo_name"].astype(str)
    panel["dataset_source"] = panel["dataset_source"].astype(str)
    panel["time"] = panel["time"].map(normalize_month_value)
    invalid_sources = sorted(set(panel["dataset_source"]) - ALLOWED_SOURCES)
    if invalid_sources:
        raise ValueError(f"Strict base panel has invalid sources: {invalid_sources}")
    require_unique(panel, KEY_COLS, "strict base panel")

    treatment_mismatch = panel.loc[
        (panel["dataset_source"] == "treatment")
        & (pd.to_numeric(panel["is_treatment"], errors="coerce") != 1)
    ]
    control_mismatch = panel.loc[
        (panel["dataset_source"] == "control")
        & (pd.to_numeric(panel["is_treatment"], errors="coerce") != 0)
    ]
    if len(treatment_mismatch) or len(control_mismatch):
        raise ValueError(
            "dataset_source and is_treatment are inconsistent in the base panel"
        )
    return panel


def merge_base_panel(
    base: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Left-join validated AGC outcomes to the strict panel."""
    outcome_nonkeys = [column for column in outcomes.columns if column not in KEY_COLS]
    allowed_overlap = {"latest_commit"}
    unexpected_overlap = sorted(
        (set(base.columns) & set(outcome_nonkeys)) - allowed_overlap
    )
    if unexpected_overlap:
        raise ValueError(
            "Base panel already contains AGC output columns that would be overwritten: "
            f"{unexpected_overlap}"
        )

    merge_outcomes = outcomes.copy()
    if "latest_commit" in base.columns:
        merge_outcomes = merge_outcomes.rename(
            columns={"latest_commit": "agc_latest_commit_internal"}
        )

    detector_only = outcomes[KEY_COLS].merge(
        base[KEY_COLS],
        on=KEY_COLS,
        how="left",
        indicator=True,
    )
    detector_only = detector_only.loc[detector_only["_merge"] == "left_only", KEY_COLS]
    if not detector_only.empty:
        detector_only = detector_only.merge(outcomes, on=KEY_COLS, how="left", validate="one_to_one")

    merged = base.merge(
        merge_outcomes,
        on=KEY_COLS,
        how="left",
        validate="one_to_one",
        indicator="__agc_merge",
    )
    merged["agc_repo_month_matched"] = merged["__agc_merge"].eq("both").astype(int)

    if "latest_commit" in base.columns:
        matched = merged["agc_repo_month_matched"].eq(1)
        base_commit = merged["latest_commit"].astype("string")
        agc_commit = merged["agc_latest_commit_internal"].astype("string")
        mismatch = matched & base_commit.notna() & agc_commit.notna() & base_commit.ne(agc_commit)
        if mismatch.any():
            sample = merged.loc[mismatch, KEY_COLS + ["latest_commit", "agc_latest_commit_internal"]].head(20)
            raise ValueError(
                f"Base latest_commit disagrees with AGC snapshot for {int(mismatch.sum())} rows.\n"
                f"Sample:\n{sample.to_string(index=False)}"
            )
        merged["latest_commit"] = base_commit.fillna(agc_commit)
        merged = merged.drop(columns=["agc_latest_commit_internal"])

    merged["agc_analysis_status"] = merged["agc_analysis_status"].fillna(
        "missing_agc_repo_month"
    )

    unmatched_base = merged.loc[
        merged["agc_repo_month_matched"] == 0,
        [column for column in OUTPUT_COLS if column in merged.columns],
    ].copy()

    merged = merged.drop(columns=["__agc_merge"])
    return merged, unmatched_base, detector_only


def coerce_output_types(df: pd.DataFrame) -> pd.DataFrame:
    """Apply stable numeric types and validate count/ratio invariants."""
    result = df.copy()
    for column in COUNT_COLS + ["python_file_count", "files_analyzed", "failure_count"]:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")

    for column in RATIO_COLS:
        result[column] = pd.to_numeric(result[column], errors="coerce")
        invalid = result[column].notna() & ~result[column].between(0, 1, inclusive="both")
        if invalid.any():
            raise ValueError(f"{column} contains {int(invalid.sum())} values outside [0, 1]")

    matched = result["agc_repo_month_matched"].eq(1)
    count_checks = {
        "top_level_total": (
            result["top_level_blocks_scored"],
            result["function_blocks_scored"] + result["class_blocks_scored"],
        ),
        "top_level_agc": (
            result["agc_top_level_blocks"],
            result["agc_function_blocks"] + result["agc_class_blocks"],
        ),
        "top_level_human": (
            result["human_top_level_blocks"],
            result["human_function_blocks"] + result["human_class_blocks"],
        ),
        "top_level_partition": (
            result["top_level_blocks_scored"],
            result["agc_top_level_blocks"] + result["human_top_level_blocks"],
        ),
        "function_partition": (
            result["function_blocks_scored"],
            result["agc_function_blocks"] + result["human_function_blocks"],
        ),
        "class_partition": (
            result["class_blocks_scored"],
            result["agc_class_blocks"] + result["human_class_blocks"],
        ),
    }
    for label, (left, right) in count_checks.items():
        mismatch = matched & left.ne(right)
        if mismatch.any():
            raise ValueError(f"Count invariant {label} failed for {int(mismatch.sum())} rows")

    return result


def build_match_summary(
    base: pd.DataFrame,
    merged: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize repository-month coverage by source."""
    rows: list[dict[str, Any]] = []
    for source in ["treatment", "control", "all"]:
        if source == "all":
            base_part = base
            merged_part = merged
            outcomes_part = outcomes
        else:
            base_part = base.loc[base["dataset_source"] == source]
            merged_part = merged.loc[merged["dataset_source"] == source]
            outcomes_part = outcomes.loc[outcomes["dataset_source"] == source]

        matched_rows = int(merged_part["agc_repo_month_matched"].sum())
        rows.append(
            {
                "dataset_source": source,
                "base_rows": len(base_part),
                "base_repositories": base_part["repo_name"].nunique(),
                "detector_repo_month_rows": len(outcomes_part),
                "matched_base_rows": matched_rows,
                "unmatched_base_rows": len(base_part) - matched_rows,
                "match_rate": matched_rows / len(base_part) if len(base_part) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_descriptive_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Build outcome summaries by source and treatment period."""
    rows: list[dict[str, Any]] = []
    group_specs = [
        (["dataset_source"], "source"),
        (["dataset_source", "post_event"], "source_post"),
    ]
    for group_cols, group_type in group_specs:
        for group_values, group in df.groupby(group_cols, dropna=False):
            if not isinstance(group_values, tuple):
                group_values = (group_values,)
            labels = dict(zip(group_cols, group_values))
            for outcome in RATIO_COLS:
                values = pd.to_numeric(group[outcome], errors="coerce")
                nonmissing = values.dropna()
                rows.append(
                    {
                        "group_type": group_type,
                        "dataset_source": labels.get("dataset_source", "all"),
                        "post_event": labels.get("post_event", "all"),
                        "outcome": outcome,
                        "rows": len(group),
                        "nonmissing": len(nonmissing),
                        "mean": nonmissing.mean() if len(nonmissing) else np.nan,
                        "median": nonmissing.median() if len(nonmissing) else np.nan,
                        "std": nonmissing.std() if len(nonmissing) > 1 else np.nan,
                        "min": nonmissing.min() if len(nonmissing) else np.nan,
                        "max": nonmissing.max() if len(nonmissing) else np.nan,
                    }
                )
    return pd.DataFrame(rows)


def build_qc_summary(
    panel_label: str,
    base: pd.DataFrame,
    merged: pd.DataFrame,
    outcomes: pd.DataFrame,
    unmatched_base: pd.DataFrame,
    detector_only: pd.DataFrame,
) -> pd.DataFrame:
    """Build a compact key-value QC summary."""
    rows: list[dict[str, Any]] = []

    def add(check: str, value: Any) -> None:
        rows.append({"check": check, "value": value})

    add("panel_label", panel_label)
    add("base_rows", len(base))
    add("output_rows", len(merged))
    add("row_count_preserved", int(len(base) == len(merged)))
    add("base_repositories", base["repo_name"].nunique())
    add("detector_repo_month_rows", len(outcomes))
    add("matched_base_rows", int(merged["agc_repo_month_matched"].sum()))
    add("unmatched_base_rows", len(unmatched_base))
    add("detector_only_rows", len(detector_only))
    add("duplicate_output_keys", int(merged.duplicated(KEY_COLS).sum()))
    add("min_time", merged["time"].min())
    add("max_time", merged["time"].max())
    add("treatment_rows", int((merged["dataset_source"] == "treatment").sum()))
    add("control_rows", int((merged["dataset_source"] == "control").sum()))
    add("agc_failure_count_sum", pd.to_numeric(merged["failure_count"], errors="coerce").fillna(0).sum())

    for outcome in RATIO_COLS:
        values = pd.to_numeric(merged[outcome], errors="coerce")
        add(f"{outcome}_nonmissing", int(values.notna().sum()))
        add(f"{outcome}_missing", int(values.isna().sum()))
        add(f"{outcome}_mean", values.mean())
        add(f"{outcome}_median", values.median())

    return pd.DataFrame(rows)


def main() -> int:
    """Run the AGC DiD input preparation pipeline."""
    setup_logging()
    args = parse_args()
    if args.chunksize <= 0:
        raise ValueError("--chunksize must be positive")

    input_paths = [
        args.base_panel,
        args.snapshot_manifest,
        args.block_treatment,
        args.block_control,
        args.repo_month_treatment,
        args.repo_month_control,
        args.run_metadata_treatment,
        args.run_metadata_control,
        args.combined_validation,
    ]
    for path in input_paths:
        require_file(path, "required input")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.qc_dir.mkdir(parents=True, exist_ok=True)

    logging.info("Validating detector metadata")
    metadata_comparison = validate_detector_metadata(
        args.run_metadata_treatment,
        args.run_metadata_control,
        args.combined_validation,
    )

    logging.info("Aggregating treatment block predictions")
    treatment_blocks = aggregate_block_file(
        args.block_treatment, "treatment", args.chunksize
    )
    logging.info("Aggregating control block predictions")
    control_blocks = aggregate_block_file(
        args.block_control, "control", args.chunksize
    )
    block_aggregates = pd.concat(
        [treatment_blocks, control_blocks], ignore_index=True
    )
    commit_wide = make_commit_wide(block_aggregates)
    require_unique(commit_wide, COMMIT_KEY_COLS, "commit-level block outcomes")

    logging.info("Loading repository-month snapshot manifest")
    manifest = load_snapshot_manifest(args.snapshot_manifest)
    reconstructed = expand_commit_outcomes_to_month(manifest, commit_wide)

    logging.info("Loading existing repository-month AGC outputs")
    oracle = load_repo_month_oracle(
        args.repo_month_treatment,
        args.repo_month_control,
    )
    compared, aggregation_qc = compare_reconstructed_with_oracle(
        reconstructed,
        oracle,
    )
    outcomes = prepare_outcome_columns(compared)

    logging.info("Loading strict matched DiD panel")
    base = load_base_panel(args.base_panel)
    merged, unmatched_base, detector_only = merge_base_panel(base, outcomes)
    merged = coerce_output_types(merged)
    require_unique(merged, KEY_COLS, "final AGC DiD panel")

    missing_output_columns = sorted(set(OUTPUT_COLS) - set(merged.columns))
    if missing_output_columns:
        raise ValueError(
            f"Final panel is missing required output columns: {missing_output_columns}"
        )
    final_output = merged[OUTPUT_COLS].copy()

    match_summary = build_match_summary(base, merged, outcomes)
    descriptive_summary = build_descriptive_summary(final_output)
    qc_summary = build_qc_summary(
        args.panel_label,
        base,
        merged,
        outcomes,
        unmatched_base,
        detector_only,
    )
    column_manifest = pd.DataFrame(
        {
            "column_order": range(1, len(OUTPUT_COLS) + 1),
            "column": OUTPUT_COLS,
        }
    )

    output_paths = {
        "main": args.output,
        "repo_month_outcomes": args.qc_dir / "repo_month_agc_outcomes_py.csv",
        "qc": args.qc_dir / "agc_did_input_qc.csv",
        "match_summary": args.qc_dir / "agc_repo_month_match_summary.csv",
        "unmatched_base": args.qc_dir / "agc_unmatched_base_repo_months.csv",
        "detector_only": args.qc_dir / "agc_unmatched_detector_repo_months.csv",
        "metadata": args.qc_dir / "agc_detector_metadata_comparison.csv",
        "descriptive": args.qc_dir / "agc_outcome_descriptive_summary.csv",
        "aggregation_qc": args.qc_dir / "agc_block_kind_aggregation_qc.csv",
        "aggregation_mismatches": args.qc_dir / "agc_block_kind_aggregation_mismatches.csv",
        "column_manifest": args.qc_dir / "agc_output_column_manifest.csv",
    }

    atomic_write_csv(final_output, output_paths["main"])
    atomic_write_csv(outcomes, output_paths["repo_month_outcomes"])
    atomic_write_csv(qc_summary, output_paths["qc"])
    atomic_write_csv(match_summary, output_paths["match_summary"])
    atomic_write_csv(unmatched_base, output_paths["unmatched_base"])
    atomic_write_csv(detector_only, output_paths["detector_only"])
    atomic_write_csv(metadata_comparison, output_paths["metadata"])
    atomic_write_csv(descriptive_summary, output_paths["descriptive"])
    atomic_write_csv(aggregation_qc, output_paths["aggregation_qc"])
    atomic_write_csv(compared.loc[~compared["all_checks_pass"]], output_paths["aggregation_mismatches"])
    atomic_write_csv(column_manifest, output_paths["column_manifest"])

    logging.info("Saved AGC DiD panel: %s", args.output)
    logging.info("Saved QC directory: %s", args.qc_dir)
    print()
    print("QC summary:")
    print(qc_summary.to_string(index=False))
    print()
    print("Repository-month match summary:")
    print(match_summary.to_string(index=False))
    print()
    print("Completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
