#!/usr/bin/env python3
"""Prepare a pair-supported fixed positive-month panel for run-py-8c.

The input sample is the original run-py-7h positive regular-module-function
sample created by run-py-7n. Propensity-score matching selected control
repositories before DiD estimation, but the current Borusyak estimator does
not use pair IDs directly. This script constructs a supplementary sensitivity
sample that retains a repository-month only when it participates in at least
one original treatment-control match observed in the same calendar month.

Definition used by this script:
  - Start from the fixed positive-month panel.
  - For every original treatment-control pair, identify calendar months in
    which both repository-month rows are present in that panel.
  - Retain the union of all treatment and control rows participating in at
    least one such pair-month.
  - Do not duplicate rows when a repository is supported by multiple pairs.

This is a post-matching panel-support sensitivity, not new propensity-score
matching and not a primary causal sample. It is intentionally labeled as
noncausal supplementary debugging because the source panel is conditioned on
realized positive outcomes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

OUTPUT_PREFIX = "pair_balanced_monthly_support"
BASELINE_OUTCOME = "npr_agc_regular_module_function_unique_bodies"
WEBSCOUT_REPO = "HelpingAI/Webscout"
WEBSCOUT_DIAGNOSTIC_MONTHS = ("2025-01", "2025-04", "2025-06")
EXPECTED_WEBSCOUT_FIXED_SUPPORT = {
    "2025-01": 1,
    "2025-04": 0,
    "2025-06": 0,
}


@dataclass(frozen=True)
class InputPaths:
    fixed_panel: Path
    zero_panel: Path
    matched_pairs: Path
    output_dir: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build an any-original-match, same-calendar-month pair-supported "
            "sensitivity panel from the run-py-7h fixed positive sample."
        )
    )
    parser.add_argument("--fixed-panel", type=Path)
    parser.add_argument("--zero-panel", type=Path)
    parser.add_argument("--matched-pairs", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--ncloc-spec",
        choices=("paper", "python_snapshot"),
        default="python_snapshot",
        help="Readiness specification used before constructing pair-month support.",
    )
    parser.add_argument(
        "--skip-frozen-count-checks",
        action="store_true",
        help="Skip expected Webscout support checks from run-py-8b.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a synthetic end-to-end self-test and exit.",
    )
    return parser.parse_args()


def require_columns(df: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def normalize_repo(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def normalize_month(series: pd.Series, label: str) -> pd.Series:
    text = series.astype("string").str.strip().str[:7]
    parsed = pd.to_datetime(text, format="%Y-%m", errors="coerce")
    invalid = parsed.isna() & text.notna() & text.ne("")
    if invalid.any():
        examples = text[invalid].drop_duplicates().head(20).tolist()
        raise ValueError(f"{label} contains invalid YYYY-MM values: {examples}")
    return parsed.dt.to_period("M").astype("string")


def detect_pair_columns(df: pd.DataFrame) -> tuple[str, str | None, list[str]]:
    treatment_candidates = (
        "treatment_repo",
        "treated_repo",
        "treatment_repo_name",
        "repo_name",
    )
    control_candidates = (
        "control_repo",
        "matched_control",
        "matched_control_repo",
        "control_repo_name",
    )
    treatment_col = next((name for name in treatment_candidates if name in df.columns), None)
    control_col = next((name for name in control_candidates if name in df.columns), None)
    wide_controls = [name for name in df.columns if name.startswith("matched_control_")]
    if treatment_col is None:
        raise ValueError("Could not identify the treatment repository column")
    if control_col is None and not wide_controls:
        raise ValueError("Could not identify control repository columns")
    return treatment_col, control_col, wide_controls


def normalize_pairs(raw: pd.DataFrame) -> pd.DataFrame:
    treatment_col, control_col, wide_controls = detect_pair_columns(raw)
    data = raw.copy()

    if control_col is None:
        id_columns = [name for name in data.columns if name not in wide_controls]
        data = data.melt(
            id_vars=id_columns,
            value_vars=wide_controls,
            var_name="matched_control_slot",
            value_name="control_repo",
        )
        data = data.rename(columns={treatment_col: "treatment_repo"})
        data["control_rank"] = pd.to_numeric(
            data["matched_control_slot"].str.extract(r"(\d+)$")[0],
            errors="coerce",
        ).astype("Int64")
    else:
        data = data.rename(
            columns={treatment_col: "treatment_repo", control_col: "control_repo"}
        )
        if "control_rank" not in data.columns:
            data["control_rank"] = pd.Series(pd.NA, index=data.index, dtype="Int64")

    data["treatment_repo"] = normalize_repo(data["treatment_repo"])
    data["control_repo"] = normalize_repo(data["control_repo"])
    data = data[
        data["treatment_repo"].notna()
        & data["control_repo"].notna()
        & data["treatment_repo"].ne("")
        & data["control_repo"].ne("")
        & data["control_repo"].str.lower().ne("nan")
    ].copy()
    data = data.drop_duplicates(["treatment_repo", "control_repo"], keep="first")
    data = data.sort_values(["treatment_repo", "control_repo"], kind="stable")
    data.insert(0, "pair_id", np.arange(1, len(data) + 1, dtype="int64"))
    return data[["pair_id", "treatment_repo", "control_repo", "control_rank"]]


def prepare_panel(raw: pd.DataFrame, label: str) -> pd.DataFrame:
    require_columns(
        raw,
        ["dataset_source", "repo_name", "time", "event", BASELINE_OUTCOME],
        label,
    )
    data = raw.copy()
    data["dataset_source"] = data["dataset_source"].astype("string").str.strip()
    data["repo_name"] = normalize_repo(data["repo_name"])
    data["time"] = normalize_month(data["time"], f"{label} time")
    if not data["dataset_source"].isin(["treatment", "control"]).all():
        unexpected = sorted(data.loc[~data["dataset_source"].isin(["treatment", "control"]), "dataset_source"].dropna().unique())
        raise ValueError(f"{label} contains unexpected dataset_source values: {unexpected}")
    if data.duplicated(["dataset_source", "repo_name", "time"]).any():
        raise ValueError(f"{label} contains duplicate repository-month keys")
    data[BASELINE_OUTCOME] = pd.to_numeric(data[BASELINE_OUTCOME], errors="raise")
    return data


def parse_logical_series(series: pd.Series, label: str) -> pd.Series:
    normalized = series.astype("string").str.strip().str.lower()
    mapping = {
        "true": True,
        "t": True,
        "1": True,
        "1.0": True,
        "false": False,
        "f": False,
        "0": False,
        "0.0": False,
    }
    parsed = normalized.map(mapping)
    if parsed.isna().any():
        examples = normalized[parsed.isna()].drop_duplicates().head(20).tolist()
        raise ValueError(f"{label} contains invalid logical values: {examples}")
    return parsed.astype(bool)


def prepare_analysis_ready_fixed_panel(
    fixed_panel: pd.DataFrame,
    ncloc_spec: str,
) -> tuple[pd.DataFrame, str, str]:
    if ncloc_spec == "paper":
        baseline_readiness = (
            "analysis_ready_regular_module_function_agc_unique_body_paper_ncloc"
        )
        hybrid_readiness = (
            "analysis_ready_regfun_selected_classmethod_agc_uniquebody_paper_ncloc"
        )
    else:
        baseline_readiness = (
            "analysis_ready_regular_module_function_agc_unique_body_"
            "python_snapshot_ncloc"
        )
        hybrid_readiness = (
            "analysis_ready_regfun_selected_classmethod_agc_uniquebody_"
            "python_snapshot_ncloc"
        )
    require_columns(
        fixed_panel,
        [baseline_readiness, hybrid_readiness],
        "Fixed positive panel readiness",
    )
    baseline_ready = parse_logical_series(
        fixed_panel[baseline_readiness], baseline_readiness
    )
    hybrid_ready = parse_logical_series(
        fixed_panel[hybrid_readiness], hybrid_readiness
    )
    if not baseline_ready.equals(hybrid_ready):
        mismatch_count = int((baseline_ready != hybrid_ready).sum())
        raise ValueError(
            "Baseline and hybrid readiness differ on "
            f"{mismatch_count} fixed-sample rows"
        )
    ready = fixed_panel.loc[baseline_ready & hybrid_ready].copy()
    ready["pair_balance_readiness_applied"] = True
    ready["pair_balance_readiness_specification"] = ncloc_spec
    return ready, baseline_readiness, hybrid_readiness


def make_presence(panel: pd.DataFrame, source: str, repo_column: str) -> pd.DataFrame:
    subset = panel.loc[panel["dataset_source"] == source, ["repo_name", "time"]].copy()
    subset = subset.rename(columns={"repo_name": repo_column})
    return subset.drop_duplicates([repo_column, "time"])


def build_pair_month_manifest(
    pairs: pd.DataFrame,
    fixed_panel: pd.DataFrame,
    zero_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    fixed_treatment = make_presence(fixed_panel, "treatment", "treatment_repo")
    fixed_control = make_presence(fixed_panel, "control", "control_repo")
    zero_treatment = make_presence(zero_panel, "treatment", "treatment_repo")
    zero_control = make_presence(zero_panel, "control", "control_repo")

    # A treatment repository can appear in multiple matched pairs, and each
    # treatment repository can appear in multiple calendar months. Therefore,
    # expanding pairs to treatment-month observations is intentionally a
    # many-to-many merge. Each pair_id-time combination must still be unique.
    fixed_pair_months = pairs.merge(
        fixed_treatment,
        on="treatment_repo",
        how="inner",
        validate="many_to_many",
    )
    if fixed_pair_months.duplicated(["pair_id", "time"]).any():
        raise ValueError("Fixed pair expansion contains duplicate pair_id-time keys")

    fixed_manifest = (
        fixed_pair_months.merge(
            fixed_control,
            on=["control_repo", "time"],
            how="inner",
            validate="many_to_one",
        )
        .sort_values(["time", "treatment_repo", "control_repo"], kind="stable")
        .reset_index(drop=True)
    )
    fixed_manifest["pair_month_id"] = np.arange(1, len(fixed_manifest) + 1, dtype="int64")
    fixed_manifest["sample"] = "original_positive_fixed"
    fixed_manifest["same_calendar_month_support"] = True

    zero_pair_months = pairs.merge(
        zero_treatment,
        on="treatment_repo",
        how="inner",
        validate="many_to_many",
    )
    if zero_pair_months.duplicated(["pair_id", "time"]).any():
        raise ValueError("Zero-panel pair expansion contains duplicate pair_id-time keys")

    zero_manifest = (
        zero_pair_months.merge(
            zero_control,
            on=["control_repo", "time"],
            how="inner",
            validate="many_to_one",
        )
        .sort_values(["time", "treatment_repo", "control_repo"], kind="stable")
        .reset_index(drop=True)
    )
    zero_manifest["sample"] = "zero_inclusive_parse_clean"
    zero_manifest["same_calendar_month_support"] = True
    return fixed_manifest, zero_manifest


def build_row_support(
    fixed_panel: pd.DataFrame,
    analysis_ready_fixed_panel: pd.DataFrame,
    pairs: pd.DataFrame,
    fixed_manifest: pd.DataFrame,
    zero_manifest: pd.DataFrame,
) -> pd.DataFrame:
    treatment_fixed_support = (
        fixed_manifest.groupby(["treatment_repo", "time"], as_index=False)
        .agg(
            pair_support_count=("pair_id", "nunique"),
            matched_counterpart_count=("control_repo", "nunique"),
        )
        .rename(columns={"treatment_repo": "repo_name"})
    )
    treatment_fixed_support["dataset_source"] = "treatment"

    control_fixed_support = (
        fixed_manifest.groupby(["control_repo", "time"], as_index=False)
        .agg(
            pair_support_count=("pair_id", "nunique"),
            matched_counterpart_count=("treatment_repo", "nunique"),
        )
        .rename(columns={"control_repo": "repo_name"})
    )
    control_fixed_support["dataset_source"] = "control"

    fixed_support = pd.concat(
        [treatment_fixed_support, control_fixed_support], ignore_index=True
    )

    treatment_zero_support = (
        zero_manifest.groupby(["treatment_repo", "time"], as_index=False)
        .agg(zero_panel_pair_support_count=("pair_id", "nunique"))
        .rename(columns={"treatment_repo": "repo_name"})
    )
    treatment_zero_support["dataset_source"] = "treatment"
    control_zero_support = (
        zero_manifest.groupby(["control_repo", "time"], as_index=False)
        .agg(zero_panel_pair_support_count=("pair_id", "nunique"))
        .rename(columns={"control_repo": "repo_name"})
    )
    control_zero_support["dataset_source"] = "control"
    zero_support = pd.concat(
        [treatment_zero_support, control_zero_support], ignore_index=True
    )

    treatment_pair_degree = (
        pairs.groupby("treatment_repo", as_index=False)
        .agg(original_matched_repository_count=("control_repo", "nunique"))
        .rename(columns={"treatment_repo": "repo_name"})
    )
    treatment_pair_degree["dataset_source"] = "treatment"
    control_pair_degree = (
        pairs.groupby("control_repo", as_index=False)
        .agg(original_matched_repository_count=("treatment_repo", "nunique"))
        .rename(columns={"control_repo": "repo_name"})
    )
    control_pair_degree["dataset_source"] = "control"
    pair_degree = pd.concat([treatment_pair_degree, control_pair_degree], ignore_index=True)

    support = fixed_panel[["dataset_source", "repo_name", "time", BASELINE_OUTCOME]].copy()
    ready_keys = analysis_ready_fixed_panel[[
        "dataset_source", "repo_name", "time"
    ]].copy()
    ready_keys["analysis_ready_for_pair_balance"] = True
    support = support.merge(
        ready_keys,
        on=["dataset_source", "repo_name", "time"],
        how="left",
        validate="one_to_one",
    )
    support["analysis_ready_for_pair_balance"] = (
        support["analysis_ready_for_pair_balance"]
        .astype("boolean")
        .fillna(False)
        .astype(bool)
    )
    support = support.merge(
        fixed_support,
        on=["dataset_source", "repo_name", "time"],
        how="left",
        validate="one_to_one",
    )
    support = support.merge(
        zero_support,
        on=["dataset_source", "repo_name", "time"],
        how="left",
        validate="one_to_one",
    )
    support = support.merge(
        pair_degree,
        on=["dataset_source", "repo_name"],
        how="left",
        validate="many_to_one",
    )
    count_columns = [
        "pair_support_count",
        "matched_counterpart_count",
        "zero_panel_pair_support_count",
        "original_matched_repository_count",
    ]
    for column in count_columns:
        support[column] = support[column].fillna(0).astype("int64")

    support["pair_balanced_support"] = support["pair_support_count"] > 0
    support["pair_support_definition"] = (
        "at_least_one_original_matched_counterpart_same_calendar_month_"
        "in_original_positive_fixed_sample"
    )
    support["exclusion_reason"] = np.select(
        [
            support["pair_balanced_support"],
            ~support["analysis_ready_for_pair_balance"],
            support["original_matched_repository_count"].eq(0),
            support["zero_panel_pair_support_count"].gt(0),
        ],
        [
            "included_pair_supported",
            "excluded_by_analysis_readiness_before_pair_balance",
            "repository_not_present_in_original_pair_manifest",
            "counterpart_support_exists_only_in_zero_inclusive_panel",
        ],
        default="no_original_matched_counterpart_same_month_in_zero_panel",
    )
    return support.sort_values(
        ["dataset_source", "repo_name", "time"], kind="stable"
    ).reset_index(drop=True)


def build_pair_balanced_panel(
    fixed_panel: pd.DataFrame,
    row_support: pd.DataFrame,
) -> pd.DataFrame:
    support_columns = [
        "dataset_source",
        "repo_name",
        "time",
        "pair_support_count",
        "matched_counterpart_count",
        "zero_panel_pair_support_count",
        "original_matched_repository_count",
        "pair_balanced_support",
        "pair_support_definition",
        "analysis_ready_for_pair_balance",
    ]
    supported = row_support.loc[row_support["pair_balanced_support"], support_columns]
    panel = fixed_panel.merge(
        supported,
        on=["dataset_source", "repo_name", "time"],
        how="inner",
        validate="one_to_one",
    )
    panel["pair_id_used_directly_in_estimator"] = False
    panel["pair_balance_applied_to_sample_construction"] = True
    panel["pair_balanced_sensitivity_only"] = True
    panel["causal_interpretation_allowed"] = False
    panel["pair_balanced_sample_restriction"] = (
        "original_module_function_outcome > 0 AND at_least_one_original_"
        "matched_counterpart_same_calendar_month"
    )
    return panel.sort_values(
        ["dataset_source", "repo_name", "time"], kind="stable"
    ).reset_index(drop=True)


def build_calendar_summary(
    fixed_panel: pd.DataFrame,
    pair_panel: pd.DataFrame,
) -> pd.DataFrame:
    fixed = (
        fixed_panel.groupby(["time", "dataset_source"], as_index=False)
        .agg(
            fixed_rows=("repo_name", "size"),
            fixed_repositories=("repo_name", "nunique"),
        )
    )
    supported = (
        pair_panel.groupby(["time", "dataset_source"], as_index=False)
        .agg(
            pair_supported_rows=("repo_name", "size"),
            pair_supported_repositories=("repo_name", "nunique"),
        )
    )
    summary = fixed.merge(
        supported,
        on=["time", "dataset_source"],
        how="left",
        validate="one_to_one",
    )
    for column in ["pair_supported_rows", "pair_supported_repositories"]:
        summary[column] = summary[column].fillna(0).astype("int64")
    summary["row_retention_share"] = (
        summary["pair_supported_rows"] / summary["fixed_rows"]
    )
    return summary.sort_values(["time", "dataset_source"], kind="stable")


def build_webscout_summary(row_support: pd.DataFrame) -> pd.DataFrame:
    rows = row_support[
        (row_support["repo_name"] == WEBSCOUT_REPO)
        & (row_support["time"].isin(WEBSCOUT_DIAGNOSTIC_MONTHS))
    ].copy()
    if len(rows) != len(WEBSCOUT_DIAGNOSTIC_MONTHS):
        found = sorted(rows["time"].tolist())
        raise ValueError(
            "Expected Webscout fixed-sample rows for all diagnostic months; "
            f"found {found}"
        )
    rows["expected_pair_support_count_from_run_py_8b"] = rows["time"].map(
        EXPECTED_WEBSCOUT_FIXED_SUPPORT
    ).astype("int64")
    rows["support_matches_run_py_8b"] = (
        rows["pair_support_count"]
        == rows["expected_pair_support_count_from_run_py_8b"]
    )
    return rows.sort_values("time", kind="stable")


def validate_outputs(
    fixed_panel: pd.DataFrame,
    analysis_ready_fixed_panel: pd.DataFrame,
    pairs: pd.DataFrame,
    fixed_manifest: pd.DataFrame,
    row_support: pd.DataFrame,
    pair_panel: pd.DataFrame,
    webscout_summary: pd.DataFrame,
    skip_frozen_count_checks: bool,
) -> pd.DataFrame:
    pair_keys = set(
        zip(
            pairs["treatment_repo"].astype(str),
            pairs["control_repo"].astype(str),
        )
    )
    manifest_keys = set(
        zip(
            fixed_manifest["treatment_repo"].astype(str),
            fixed_manifest["control_repo"].astype(str),
        )
    )
    panel_keys = set(
        zip(
            fixed_panel["dataset_source"].astype(str),
            fixed_panel["repo_name"].astype(str),
            fixed_panel["time"].astype(str),
        )
    )
    pair_panel_keys = set(
        zip(
            pair_panel["dataset_source"].astype(str),
            pair_panel["repo_name"].astype(str),
            pair_panel["time"].astype(str),
        )
    )

    checks = [
        (
            "fixed_panel_has_no_duplicate_repository_months",
            int(fixed_panel.duplicated(["dataset_source", "repo_name", "time"]).sum()),
            not fixed_panel.duplicated(["dataset_source", "repo_name", "time"]).any(),
        ),
        (
            "normalized_pair_manifest_has_unique_pairs",
            int(pairs.duplicated(["treatment_repo", "control_repo"]).sum()),
            not pairs.duplicated(["treatment_repo", "control_repo"]).any(),
        ),
        (
            "pair_month_manifest_references_original_pairs_only",
            int(len(manifest_keys - pair_keys)),
            manifest_keys.issubset(pair_keys),
        ),
        (
            "pair_balanced_panel_is_subset_of_fixed_panel",
            int(len(pair_panel_keys - panel_keys)),
            pair_panel_keys.issubset(panel_keys),
        ),
        (
            "pair_balanced_panel_has_no_duplicate_repository_months",
            int(pair_panel.duplicated(["dataset_source", "repo_name", "time"]).sum()),
            not pair_panel.duplicated(["dataset_source", "repo_name", "time"]).any(),
        ),
        (
            "every_pair_balanced_row_has_positive_pair_support",
            int((pair_panel["pair_support_count"] <= 0).sum()),
            bool((pair_panel["pair_support_count"] > 0).all()),
        ),
        (
            "pair_balanced_panel_has_treatment_and_control_rows",
            int(pair_panel["dataset_source"].nunique()),
            set(pair_panel["dataset_source"].unique()) == {"treatment", "control"},
        ),
        (
            "fixed_positive_outcome_remains_strictly_positive",
            int((pair_panel[BASELINE_OUTCOME] <= 0).sum()),
            bool((pair_panel[BASELINE_OUTCOME] > 0).all()),
        ),
        (
            "pair_balanced_panel_is_nonempty",
            int(len(pair_panel)),
            len(pair_panel) > 0,
        ),
        (
            "analysis_ready_fixed_panel_is_not_larger_than_fixed_panel",
            int(len(analysis_ready_fixed_panel)),
            0 < len(analysis_ready_fixed_panel) <= len(fixed_panel),
        ),
        (
            "pair_balanced_panel_is_smaller_than_analysis_ready_fixed_panel",
            int(len(pair_panel)),
            0 < len(pair_panel) < len(analysis_ready_fixed_panel),
        ),
        (
            "webscout_diagnostic_month_rows_complete",
            int(len(webscout_summary)),
            len(webscout_summary) == len(WEBSCOUT_DIAGNOSTIC_MONTHS),
        ),
        (
            "webscout_support_matches_run_py_8b",
            int((~webscout_summary["support_matches_run_py_8b"]).sum()),
            skip_frozen_count_checks
            or bool(webscout_summary["support_matches_run_py_8b"].all()),
        ),
        (
            "webscout_2025_04_excluded_by_pair_support",
            int(
                webscout_summary.loc[
                    webscout_summary["time"] == "2025-04", "pair_balanced_support"
                ].iloc[0]
            ),
            not bool(
                webscout_summary.loc[
                    webscout_summary["time"] == "2025-04", "pair_balanced_support"
                ].iloc[0]
            ),
        ),
        (
            "webscout_2025_06_excluded_by_pair_support",
            int(
                webscout_summary.loc[
                    webscout_summary["time"] == "2025-06", "pair_balanced_support"
                ].iloc[0]
            ),
            not bool(
                webscout_summary.loc[
                    webscout_summary["time"] == "2025-06", "pair_balanced_support"
                ].iloc[0]
            ),
        ),
        (
            "pair_ids_not_marked_for_direct_estimator_use",
            int(pair_panel["pair_id_used_directly_in_estimator"].sum()),
            not bool(pair_panel["pair_id_used_directly_in_estimator"].any()),
        ),
        (
            "analysis_labeled_noncausal",
            int(pair_panel["causal_interpretation_allowed"].sum()),
            not bool(pair_panel["causal_interpretation_allowed"].any()),
        ),
    ]
    return pd.DataFrame(checks, columns=["check_name", "value", "passed"])


def write_outputs(
    output_dir: Path,
    analysis_ready_fixed_panel: pd.DataFrame,
    pairs: pd.DataFrame,
    fixed_manifest: pd.DataFrame,
    row_support: pd.DataFrame,
    pair_panel: pd.DataFrame,
    calendar_summary: pd.DataFrame,
    webscout_summary: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    excluded_rows = row_support.loc[~row_support["pair_balanced_support"]].copy()
    summary = {
        "status": "PASS" if bool(validation["passed"].all()) else "FAIL",
        "analysis": "pair-balanced monthly-support sensitivity panel preparation",
        "pair_balance_definition": (
            "retain a fixed-positive-sample repository-month when it participates "
            "in at least one original matched treatment-control pair observed in "
            "the same calendar month"
        ),
        "normalized_pair_count": int(len(pairs)),
        "supported_pair_month_count": int(len(fixed_manifest)),
        "fixed_sample_rows": int(len(row_support)),
        "analysis_ready_fixed_sample_rows": int(len(analysis_ready_fixed_panel)),
        "pair_balanced_rows": int(len(pair_panel)),
        "excluded_fixed_sample_rows": int(len(excluded_rows)),
        "pair_balanced_repositories": int(pair_panel["repo_name"].nunique()),
        "pair_balanced_treatment_repositories": int(
            pair_panel.loc[pair_panel["dataset_source"] == "treatment", "repo_name"].nunique()
        ),
        "pair_balanced_control_repositories": int(
            pair_panel.loc[pair_panel["dataset_source"] == "control", "repo_name"].nunique()
        ),
        "pair_id_used_directly_in_estimator": False,
        "causal_interpretation_allowed": False,
        "primary_replication_replacement": False,
    }

    pairs.to_csv(output_dir / f"{OUTPUT_PREFIX}_normalized_pairs.csv", index=False)
    fixed_manifest.to_csv(
        output_dir / f"{OUTPUT_PREFIX}_pair_month_manifest.csv", index=False
    )
    row_support.to_csv(output_dir / f"{OUTPUT_PREFIX}_row_support.csv", index=False)
    excluded_rows.to_csv(
        output_dir / f"{OUTPUT_PREFIX}_excluded_fixed_rows.csv", index=False
    )
    pair_panel.to_csv(output_dir / f"{OUTPUT_PREFIX}_panel.csv", index=False)
    calendar_summary.to_csv(
        output_dir / f"{OUTPUT_PREFIX}_calendar_summary.csv", index=False
    )
    webscout_summary.to_csv(
        output_dir / f"{OUTPUT_PREFIX}_webscout_diagnostic_months.csv", index=False
    )
    validation.to_csv(output_dir / f"{OUTPUT_PREFIX}_validation.csv", index=False)
    with (output_dir / f"{OUTPUT_PREFIX}_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    status_lines = [
        summary["status"],
        "Pair balance is applied only to sample construction.",
        "Pair IDs are not passed directly to the Borusyak estimator.",
        "The source sample is outcome-conditioned and remains noncausal supplementary sensitivity.",
    ]
    (output_dir / f"{OUTPUT_PREFIX}_status.txt").write_text(
        "\n".join(status_lines) + "\n", encoding="utf-8"
    )


def run_analysis(
    paths: InputPaths,
    skip_frozen_count_checks: bool,
    ncloc_spec: str,
) -> None:
    fixed_panel = prepare_panel(pd.read_csv(paths.fixed_panel), "Fixed positive panel")
    zero_panel = prepare_panel(pd.read_csv(paths.zero_panel), "Zero-inclusive panel")
    pairs = normalize_pairs(pd.read_csv(paths.matched_pairs))
    analysis_ready_fixed_panel, _, _ = prepare_analysis_ready_fixed_panel(
        fixed_panel, ncloc_spec
    )

    if not (fixed_panel[BASELINE_OUTCOME] > 0).all():
        raise ValueError("Fixed positive panel contains nonpositive baseline outcomes")

    fixed_manifest, zero_manifest = build_pair_month_manifest(
        pairs, analysis_ready_fixed_panel, zero_panel
    )
    row_support = build_row_support(
        fixed_panel,
        analysis_ready_fixed_panel,
        pairs,
        fixed_manifest,
        zero_manifest,
    )
    pair_panel = build_pair_balanced_panel(fixed_panel, row_support)
    calendar_summary = build_calendar_summary(fixed_panel, pair_panel)
    webscout_summary = build_webscout_summary(row_support)
    validation = validate_outputs(
        fixed_panel,
        analysis_ready_fixed_panel,
        pairs,
        fixed_manifest,
        row_support,
        pair_panel,
        webscout_summary,
        skip_frozen_count_checks,
    )

    write_outputs(
        paths.output_dir,
        analysis_ready_fixed_panel,
        pairs,
        fixed_manifest,
        row_support,
        pair_panel,
        calendar_summary,
        webscout_summary,
        validation,
    )

    failed = validation.loc[~validation["passed"]]
    print("=" * 80)
    print("run-py-8c: pair-balanced monthly-support panel preparation")
    print("=" * 80)
    print(f"Status: {'PASS' if failed.empty else 'FAIL'}")
    print(f"Normalized pairs: {len(pairs)}")
    print(f"Supported pair-months: {len(fixed_manifest)}")
    print(f"Fixed positive rows: {len(fixed_panel)}")
    print(f"Analysis-ready fixed rows: {len(analysis_ready_fixed_panel)}")
    print(f"Pair-balanced rows: {len(pair_panel)}")
    print(f"Pair-balanced repositories: {pair_panel['repo_name'].nunique()}")
    print(
        "Pair-balanced treatment repositories: "
        f"{pair_panel.loc[pair_panel['dataset_source'] == 'treatment', 'repo_name'].nunique()}"
    )
    print(
        "Pair-balanced control repositories: "
        f"{pair_panel.loc[pair_panel['dataset_source'] == 'control', 'repo_name'].nunique()}"
    )
    print(f"Failed checks: {len(failed)}")
    print("\nWebscout diagnostic-month support:")
    display_columns = [
        "repo_name",
        "time",
        BASELINE_OUTCOME,
        "pair_support_count",
        "zero_panel_pair_support_count",
        "pair_balanced_support",
        "exclusion_reason",
    ]
    print(webscout_summary[display_columns].to_string(index=False))
    print(f"\nOutput directory: {paths.output_dir}")
    print("=" * 80)
    if not failed.empty:
        print("\nFailed validation checks:", file=sys.stderr)
        print(failed.to_string(index=False), file=sys.stderr)
        raise SystemExit(3)


def make_synthetic_panel() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # Include one treatment with two controls so the self-test exercises
    # the real one-to-many matching structure used by the project data.
    pairs = pd.DataFrame(
        {
            "treatment_repo": ["T/a", "T/a", "T/b", "T/c"],
            "control_repo": ["C/x", "C/z", "C/y", WEBSCOUT_REPO],
            "control_rank": [1, 2, 1, 1],
        }
    )
    fixed_rows = [
        ("treatment", "T/a", "2025-01", "2024-12", 2),
        ("control", "C/x", "2025-01", "", 1),
        ("control", "C/z", "2025-01", "", 2),
        ("treatment", "T/b", "2025-02", "2025-01", 3),
        ("control", "C/y", "2025-03", "", 4),
        ("treatment", "T/c", "2025-01", "2024-10", 2),
        ("control", WEBSCOUT_REPO, "2025-01", "", 1),
        ("control", WEBSCOUT_REPO, "2025-04", "", 3),
        ("control", WEBSCOUT_REPO, "2025-06", "", 11),
    ]
    fixed = pd.DataFrame(
        fixed_rows,
        columns=["dataset_source", "repo_name", "time", "event", BASELINE_OUTCOME],
    )
    fixed[
        "analysis_ready_regular_module_function_agc_unique_body_"
        "python_snapshot_ncloc"
    ] = True
    fixed[
        "analysis_ready_regfun_selected_classmethod_agc_uniquebody_"
        "python_snapshot_ncloc"
    ] = True
    zero = pd.concat(
        [
            fixed,
            pd.DataFrame(
                [
                    {
                        "dataset_source": "treatment",
                        "repo_name": "T/c",
                        "time": "2025-04",
                        "event": "2024-10",
                        BASELINE_OUTCOME: 0,
                        (
                            "analysis_ready_regular_module_function_agc_unique_body_"
                            "python_snapshot_ncloc"
                        ): True,
                        (
                            "analysis_ready_regfun_selected_classmethod_agc_uniquebody_"
                            "python_snapshot_ncloc"
                        ): True,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    return pairs, fixed, zero


def run_self_test() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="run-py-8c-self-test-"))
    try:
        pairs, fixed, zero = make_synthetic_panel()
        fixed_path = temp_root / "fixed.csv"
        zero_path = temp_root / "zero.csv"
        pairs_path = temp_root / "pairs.csv"
        out_dir = temp_root / "out"
        fixed.to_csv(fixed_path, index=False)
        zero.to_csv(zero_path, index=False)
        pairs.to_csv(pairs_path, index=False)

        run_analysis(
            InputPaths(
                fixed_panel=fixed_path,
                zero_panel=zero_path,
                matched_pairs=pairs_path,
                output_dir=out_dir,
            ),
            skip_frozen_count_checks=True,
            ncloc_spec="python_snapshot",
        )
        result = pd.read_csv(out_dir / f"{OUTPUT_PREFIX}_panel.csv")
        result_keys = set(zip(result["repo_name"], result["time"]))
        expected = {
            ("T/a", "2025-01"),
            ("C/x", "2025-01"),
            ("C/z", "2025-01"),
            ("T/c", "2025-01"),
            (WEBSCOUT_REPO, "2025-01"),
        }
        if result_keys != expected:
            raise AssertionError(
                f"Unexpected synthetic supported rows: {sorted(result_keys)}"
            )
        print("Self-test: PASS")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> None:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return

    required = {
        "--fixed-panel": args.fixed_panel,
        "--zero-panel": args.zero_panel,
        "--matched-pairs": args.matched_pairs,
        "--output-dir": args.output_dir,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise SystemExit("Missing required arguments: " + ", ".join(missing))
    for path in [args.fixed_panel, args.zero_panel, args.matched_pairs]:
        if not path.is_file():
            raise SystemExit(f"Required file not found: {path}")

    run_analysis(
        InputPaths(
            fixed_panel=args.fixed_panel,
            zero_panel=args.zero_panel,
            matched_pairs=args.matched_pairs,
            output_dir=args.output_dir,
        ),
        skip_frozen_count_checks=args.skip_frozen_count_checks,
        ncloc_spec=args.ncloc_spec,
    )


if __name__ == "__main__":
    main()
