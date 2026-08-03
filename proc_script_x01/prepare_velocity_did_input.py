#!/usr/bin/env python3
"""
Prepare the original-style pooled Python velocity DiD input (v3).

This stage builds a unique repository-month panel from the original matched
sample. It does not duplicate a control repository because the same control was
matched to multiple treatment repositories. The matching relationship is used
to define the candidate control pool; the final pooled panel contains each
repository-month at most once.

Treatment inclusion:
- dataset_source is treatment;
- a valid Cursor adoption event is present;
- the repository-month is Python-eligible.

Control inclusion:
- the repository belongs to the unique union of controls matched to valid-event
  candidate treatment repositories in run-x-a04;
- the control repository-month exists in the original panel window;
- the repository-month is Python-eligible.

The run-x-a04 pairwise coverage values are merged into treatment rows only as
quality-control fields. A treatment row is not removed merely because its own
three matched controls have zero usable Python slots in that month. The
Borusyak first stage uses the pooled untreated observations in the matched
panel, not only the three controls assigned to one treatment repository.

The script writes both:
- a pooled Python panel before Model A complete-case filtering;
- a Model A-ready panel with complete velocity outcomes and covariates.

Raw metrics are preserved. Log1p-transformed columns are added explicitly for
future R analysis. The script also creates a unique snapshot manifest for the
later Python-only SonarQube run that will produce ncloc_py for Model C.

Version 2 protects the pooled control group from treated-control
contamination. If a repository listed in the original control dataset later has
a Cursor adoption event, only its strictly pre-adoption rows may remain in the
control pool. Rows at or after adoption are censored and recorded explicitly in
the exclusion and QC outputs.

Version 3 merges the targeted whole-repository NCLOC recovery produced by
run-x-a05b. Recovered values may fill only originally missing NCLOC cells. The
merge requires repository, calendar month, dataset source, and effective commit
to match exactly. Existing replication-package NCLOC values are never
overwritten, and all recovery provenance is retained in the output panels.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


PAIR_REQUIRED_COLUMNS = {
    "treatment_repo",
    "control_rank",
    "control_repo",
}

PANEL_REQUIRED_COLUMNS = {
    "repo_name",
    "time",
    "event",
    "dataset_source",
    "python_eligible",
    "scan_status",
    "commits",
    "lines_added",
    "contributors",
    "stars",
    "issues",
    "age",
    "ncloc",
    "latest_commit_effective",
    "commit_resolution",
    "months_since_observed_commit",
    "is_treatment",
    "cursor",
}

REUSE_REQUIRED_COLUMNS = {
    "control_repo",
    "matched_treatment_count_all",
    "matched_treatment_count_candidates",
    "candidate_treatment_month_slots",
    "candidate_python_eligible_slots",
    "control_clone_found",
    "pair_statuses",
    "monthly_history_rows",
    "monthly_python_rows",
    "monthly_no_python_rows",
    "monthly_unknown_rows",
    "first_month",
    "last_month",
}

COVERAGE_REQUIRED_COLUMNS = {
    "treatment_repo",
    "treatment_month",
    "original_control_slots",
    "python_eligible_controls",
    "no_python_controls",
    "snapshot_unknown_controls",
    "missing_clone_controls",
    "missing_monthly_history_controls",
    "no_prior_snapshot_controls",
    "has_any_python_control",
    "has_all_three_python_controls",
    "coverage_class",
}

NCLOC_PATCH_REQUIRED_COLUMNS = {
    "snapshot_key",
    "dataset_source",
    "scope_role",
    "repo_name",
    "time",
    "latest_commit_effective",
    "project_key",
    "project_version",
    "status",
    "ncloc_recovered",
    "git_precheck_status",
    "scanner_log_path",
    "ncloc_patch_available",
    "ncloc_patch_source",
}

MODEL_A_RAW_COLUMNS = [
    "commits",
    "lines_added",
    "age",
    "ncloc",
    "contributors",
    "stars",
    "issues",
]

LOG1P_SOURCE_COLUMNS = [
    "commits",
    "lines_added",
    "age",
    "contributors",
    "stars",
    "issues",
]

STRING_COLUMNS = [
    "repo_name",
    "time",
    "event",
    "dataset_source",
    "scan_status",
    "latest_commit_original",
    "latest_commit_effective",
    "latest_commit",
    "commit_resolution",
    "eligibility_join_status",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build an original-style pooled Python repository-month panel for "
            "velocity DiD analysis."
        )
    )
    parser.add_argument("--matching-pairs-file", required=True, type=Path)
    parser.add_argument("--panel-file", required=True, type=Path)
    parser.add_argument("--control-reuse-file", required=True, type=Path)
    parser.add_argument("--coverage-file", required=True, type=Path)
    parser.add_argument("--ncloc-recovery-patch-file", required=True, type=Path)
    parser.add_argument("--pooled-panel-output", required=True, type=Path)
    parser.add_argument("--model-a-complete-case-output", required=True, type=Path)
    parser.add_argument("--model-a-panel-output", required=True, type=Path)
    parser.add_argument("--treatment-estimability-audit-output", required=True, type=Path)
    parser.add_argument("--row-exclusions-output", required=True, type=Path)
    parser.add_argument("--control-pool-audit-output", required=True, type=Path)
    parser.add_argument("--model-c-snapshot-manifest-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument("--start-month", default="2024-01")
    parser.add_argument("--end-month", default="2025-08")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def normalize_bool_series(values: pd.Series, label: str) -> pd.Series:
    """Normalize common Boolean encodings to nullable integer flags."""
    text = values.map(clean_text).str.casefold()
    true_values = {"1", "true", "t", "yes", "y"}
    false_values = {"0", "false", "f", "no", "n"}
    invalid = ~text.isin(true_values | false_values | {""})
    if invalid.any():
        examples = sorted(text.loc[invalid].unique().tolist())[:10]
        raise ValueError(f"{label} contains invalid Boolean values: {examples}")

    result = pd.Series(pd.NA, index=values.index, dtype="Int64")
    result.loc[text.isin(true_values)] = 1
    result.loc[text.isin(false_values)] = 0
    return result


def repo_key(value: object) -> str:
    return clean_text(value).casefold()


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{label} is missing required columns: {', '.join(sorted(missing))}"
        )


def parse_month_value(value: str, label: str) -> pd.Period:
    text = clean_text(value)
    try:
        return pd.Period(text, freq="M")
    except Exception as exc:
        raise ValueError(f"{label} must use YYYY-MM format: {value!r}") from exc


def parse_month_series(values: pd.Series, label: str) -> pd.Series:
    text = values.map(clean_text)
    parsed = pd.to_datetime(text, format="%Y-%m", errors="coerce")
    invalid = text.ne("") & parsed.isna()
    if invalid.any():
        examples = sorted(text.loc[invalid].unique().tolist())[:10]
        raise ValueError(f"{label} contains invalid YYYY-MM values: {examples}")
    result = pd.Series(pd.NaT, index=values.index, dtype="period[M]")
    valid = parsed.notna()
    if valid.any():
        result.loc[valid] = parsed.loc[valid].dt.to_period("M")
    return result


def read_csv_stable(path: Path, string_columns: Iterable[str]) -> pd.DataFrame:
    dtype = {column: "string" for column in string_columns}
    return pd.read_csv(path, dtype=dtype, low_memory=False)


def validate_args(args: argparse.Namespace) -> tuple[pd.Period, pd.Period]:
    for path in [
        args.matching_pairs_file,
        args.panel_file,
        args.control_reuse_file,
        args.coverage_file,
        args.ncloc_recovery_patch_file,
    ]:
        if not path.is_file():
            raise FileNotFoundError(f"Required input file not found: {path}")

    start_period = parse_month_value(args.start_month, "start-month")
    end_period = parse_month_value(args.end_month, "end-month")
    if start_period > end_period:
        raise ValueError("start-month cannot be later than end-month")
    return start_period, end_period


def normalize_pairs(pairs: pd.DataFrame) -> pd.DataFrame:
    require_columns(pairs, PAIR_REQUIRED_COLUMNS, "matching pairs CSV")
    data = pairs.copy()
    data["treatment_repo"] = data["treatment_repo"].map(clean_text)
    data["control_repo"] = data["control_repo"].map(clean_text)
    data["treatment_key"] = data["treatment_repo"].map(repo_key)
    data["control_key"] = data["control_repo"].map(repo_key)
    data["control_rank"] = pd.to_numeric(data["control_rank"], errors="raise").astype(int)

    if data[["treatment_key", "control_key"]].eq("").any().any():
        raise ValueError("Matching pairs contain blank treatment or control names")

    duplicated = data.duplicated(["treatment_key", "control_rank"], keep=False)
    if duplicated.any():
        sample = data.loc[
            duplicated, ["treatment_repo", "control_rank", "control_repo"]
        ].head(20)
        raise ValueError(
            "Matching pairs contain duplicate treatment/control-rank rows: "
            + repr(sample.to_dict(orient="records"))
        )

    counts = data.groupby("treatment_key")["control_rank"].agg(
        count="size", ranks=lambda values: tuple(sorted(set(values)))
    )
    invalid = counts[(counts["count"] != 3) | (counts["ranks"] != (1, 2, 3))]
    if not invalid.empty:
        raise ValueError(
            "Each treatment must have exactly control ranks 1, 2, and 3: "
            + repr(invalid.head(20).reset_index().to_dict(orient="records"))
        )
    return data


def normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    require_columns(panel, PANEL_REQUIRED_COLUMNS, "enriched panel CSV")
    data = panel.copy()
    for column in STRING_COLUMNS:
        if column in data.columns:
            data[column] = data[column].map(clean_text)

    data["dataset_source"] = data["dataset_source"].str.casefold()
    data["repo_key"] = data["repo_name"].map(repo_key)
    data["time_period"] = parse_month_series(data["time"], "panel.time")
    data["event_period"] = parse_month_series(data["event"], "panel.event")
    data["python_eligible"] = pd.to_numeric(
        data["python_eligible"], errors="coerce"
    ).astype("Int64")
    data["cursor_flag"] = normalize_bool_series(data["cursor"], "panel.cursor")

    for column in MODEL_A_RAW_COLUMNS + [
        "time_to_event",
        "post_event",
        "is_treatment",
        "months_since_observed_commit",
        "python_file_count_all",
        "python_file_count_source",
    ]:
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")

    duplicated = data.duplicated(["dataset_source", "repo_key", "time"], keep=False)
    if duplicated.any():
        sample = data.loc[
            duplicated, ["dataset_source", "repo_name", "time"]
        ].head(20)
        raise ValueError(
            "Enriched panel contains duplicate source/repository-month rows: "
            + repr(sample.to_dict(orient="records"))
        )
    return data


def normalize_ncloc_patch(patch: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize the run-x-a05b repo-month NCLOC patch."""
    require_columns(patch, NCLOC_PATCH_REQUIRED_COLUMNS, "NCLOC recovery patch CSV")
    data = patch.copy()

    for column in [
        "snapshot_key",
        "dataset_source",
        "scope_role",
        "repo_name",
        "time",
        "latest_commit_effective",
        "project_key",
        "project_version",
        "status",
        "git_precheck_status",
        "scanner_log_path",
        "ncloc_patch_source",
    ]:
        data[column] = data[column].map(clean_text)

    data["dataset_source"] = data["dataset_source"].str.casefold()
    data["scope_role"] = data["scope_role"].str.casefold()
    data["status"] = data["status"].str.casefold()
    data["repo_key"] = data["repo_name"].map(repo_key)
    data["time_period"] = parse_month_series(data["time"], "NCLOC patch.time")
    data["commit_key"] = data["latest_commit_effective"].str.casefold()
    data["ncloc_recovered"] = pd.to_numeric(
        data["ncloc_recovered"], errors="coerce"
    )
    data["ncloc_patch_available_flag"] = normalize_bool_series(
        data["ncloc_patch_available"], "NCLOC patch.ncloc_patch_available"
    )

    blank_key = (
        data["repo_key"].eq("")
        | data["time"].eq("")
        | data["commit_key"].eq("")
        | data["dataset_source"].eq("")
    )
    if blank_key.any():
        sample = data.loc[
            blank_key,
            ["dataset_source", "repo_name", "time", "latest_commit_effective"],
        ].head(20)
        raise ValueError(
            "NCLOC recovery patch contains blank merge keys: "
            + repr(sample.to_dict(orient="records"))
        )

    invalid_source = ~data["dataset_source"].isin(["treatment", "control"])
    if invalid_source.any():
        examples = sorted(data.loc[invalid_source, "dataset_source"].unique().tolist())
        raise ValueError(f"NCLOC recovery patch has invalid dataset_source values: {examples}")

    invalid_role = data["scope_role"].ne(data["dataset_source"])
    if invalid_role.any():
        sample = data.loc[
            invalid_role, ["repo_name", "dataset_source", "scope_role"]
        ].head(20)
        raise ValueError(
            "NCLOC recovery patch scope_role does not match dataset_source: "
            + repr(sample.to_dict(orient="records"))
        )

    invalid_value = data["ncloc_recovered"].isna() | data["ncloc_recovered"].lt(0)
    invalid_status = data["status"].ne("success")
    invalid_available = data["ncloc_patch_available_flag"].ne(1)
    invalid = invalid_value | invalid_status | invalid_available
    if invalid.any():
        sample = data.loc[
            invalid,
            [
                "repo_name",
                "time",
                "status",
                "ncloc_recovered",
                "ncloc_patch_available",
            ],
        ].head(20)
        raise ValueError(
            "NCLOC recovery patch contains unresolved or invalid rows: "
            + repr(sample.to_dict(orient="records"))
        )

    duplicated = data.duplicated(
        ["dataset_source", "repo_key", "time", "commit_key"], keep=False
    )
    if duplicated.any():
        sample = data.loc[
            duplicated,
            ["dataset_source", "repo_name", "time", "latest_commit_effective"],
        ].head(20)
        raise ValueError(
            "NCLOC recovery patch contains duplicate merge keys: "
            + repr(sample.to_dict(orient="records"))
        )

    return data


def apply_ncloc_recovery(
    panel: pd.DataFrame, patch: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Fill only originally missing NCLOC values and preserve provenance."""
    data = panel.copy()
    data["ncloc_original"] = pd.to_numeric(data["ncloc"], errors="coerce")
    data["ncloc_recovered"] = np.nan
    data["ncloc_source"] = np.where(
        data["ncloc_original"].notna(), "replication_panel", "missing"
    )
    data["ncloc_recovery_applied"] = 0
    data["ncloc_recovery_snapshot_key"] = ""
    data["ncloc_recovery_scanner_log"] = ""
    data["ncloc_recovery_project_key"] = ""
    data["ncloc_recovery_project_version"] = ""
    data["ncloc_recovery_status"] = ""
    data["ncloc_recovery_git_precheck_status"] = ""
    data["commit_key"] = data["latest_commit_effective"].map(clean_text).str.casefold()

    patch_fields = patch[
        [
            "dataset_source",
            "repo_key",
            "time",
            "commit_key",
            "snapshot_key",
            "ncloc_recovered",
            "ncloc_patch_source",
            "scanner_log_path",
            "project_key",
            "project_version",
            "status",
            "git_precheck_status",
        ]
    ].rename(
        columns={
            "snapshot_key": "patch_snapshot_key",
            "ncloc_recovered": "patch_ncloc_recovered",
            "ncloc_patch_source": "patch_ncloc_source",
            "scanner_log_path": "patch_scanner_log_path",
            "project_key": "patch_project_key",
            "project_version": "patch_project_version",
            "status": "patch_status",
            "git_precheck_status": "patch_git_precheck_status",
        }
    )

    merged = data.merge(
        patch_fields,
        on=["dataset_source", "repo_key", "time", "commit_key"],
        how="left",
        validate="one_to_one",
        indicator="ncloc_patch_merge",
    )

    matched = merged["ncloc_patch_merge"].eq("both")
    matched_rows = int(matched.sum())
    unmatched_patch_rows = int(len(patch) - matched_rows)
    if unmatched_patch_rows != 0:
        panel_keys = set(
            zip(
                data["dataset_source"],
                data["repo_key"],
                data["time"],
                data["commit_key"],
            )
        )
        unmatched = patch[
            ~patch.apply(
                lambda row: (
                    row["dataset_source"],
                    row["repo_key"],
                    row["time"],
                    row["commit_key"],
                ) in panel_keys,
                axis=1,
            )
        ]
        sample = unmatched[
            ["dataset_source", "repo_name", "time", "latest_commit_effective"]
        ].head(20)
        raise ValueError(
            f"{unmatched_patch_rows} NCLOC patch rows did not match the enriched panel: "
            + repr(sample.to_dict(orient="records"))
        )

    overwrite = matched & merged["ncloc_original"].notna()
    overwritten_rows = int(overwrite.sum())
    if overwritten_rows != 0:
        sample = merged.loc[
            overwrite,
            [
                "dataset_source",
                "repo_name",
                "time",
                "latest_commit_effective",
                "ncloc_original",
                "patch_ncloc_recovered",
            ],
        ].head(20)
        raise ValueError(
            "NCLOC recovery would overwrite existing replication values: "
            + repr(sample.to_dict(orient="records"))
        )

    apply_mask = matched & merged["ncloc_original"].isna()
    merged.loc[apply_mask, "ncloc_recovered"] = merged.loc[
        apply_mask, "patch_ncloc_recovered"
    ]
    merged.loc[apply_mask, "ncloc"] = merged.loc[
        apply_mask, "patch_ncloc_recovered"
    ]
    merged.loc[apply_mask, "ncloc_source"] = merged.loc[
        apply_mask, "patch_ncloc_source"
    ]
    merged.loc[apply_mask, "ncloc_recovery_applied"] = 1
    merged.loc[apply_mask, "ncloc_recovery_snapshot_key"] = merged.loc[
        apply_mask, "patch_snapshot_key"
    ]
    merged.loc[apply_mask, "ncloc_recovery_scanner_log"] = merged.loc[
        apply_mask, "patch_scanner_log_path"
    ]
    merged.loc[apply_mask, "ncloc_recovery_project_key"] = merged.loc[
        apply_mask, "patch_project_key"
    ]
    merged.loc[apply_mask, "ncloc_recovery_project_version"] = merged.loc[
        apply_mask, "patch_project_version"
    ]
    merged.loc[apply_mask, "ncloc_recovery_status"] = merged.loc[
        apply_mask, "patch_status"
    ]
    merged.loc[apply_mask, "ncloc_recovery_git_precheck_status"] = merged.loc[
        apply_mask, "patch_git_precheck_status"
    ]

    drop_columns = [
        "commit_key",
        "patch_snapshot_key",
        "patch_ncloc_recovered",
        "patch_ncloc_source",
        "patch_scanner_log_path",
        "patch_project_key",
        "patch_project_version",
        "patch_status",
        "patch_git_precheck_status",
        "ncloc_patch_merge",
    ]
    merged = merged.drop(columns=drop_columns)

    audit = {
        "patch_rows": int(len(patch)),
        "matched_rows": matched_rows,
        "applied_rows": int(apply_mask.sum()),
        "overwritten_existing_rows": overwritten_rows,
        "unmatched_rows": unmatched_patch_rows,
        "treatment_applied_rows": int(
            (merged["ncloc_recovery_applied"].eq(1) & merged["dataset_source"].eq("treatment")).sum()
        ),
        "control_applied_rows": int(
            (merged["ncloc_recovery_applied"].eq(1) & merged["dataset_source"].eq("control")).sum()
        ),
    }
    return merged, audit


def normalize_reuse(reuse: pd.DataFrame) -> pd.DataFrame:
    require_columns(reuse, REUSE_REQUIRED_COLUMNS, "control reuse CSV")
    data = reuse.copy()
    data["control_repo"] = data["control_repo"].map(clean_text)
    data["control_key"] = data["control_repo"].map(repo_key)
    for column in [
        "matched_treatment_count_all",
        "matched_treatment_count_candidates",
        "candidate_treatment_month_slots",
        "candidate_python_eligible_slots",
        "monthly_history_rows",
        "monthly_python_rows",
        "monthly_no_python_rows",
        "monthly_unknown_rows",
    ]:
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0).astype(int)

    duplicated = data.duplicated("control_key", keep=False)
    if duplicated.any():
        sample = data.loc[duplicated, ["control_repo"]].head(20)
        raise ValueError(
            "Control reuse CSV contains duplicate controls: "
            + repr(sample.to_dict(orient="records"))
        )
    return data


def normalize_coverage(coverage: pd.DataFrame) -> pd.DataFrame:
    require_columns(coverage, COVERAGE_REQUIRED_COLUMNS, "coverage CSV")
    data = coverage.copy()
    data["treatment_repo"] = data["treatment_repo"].map(clean_text)
    data["treatment_key"] = data["treatment_repo"].map(repo_key)
    data["treatment_month"] = data["treatment_month"].map(clean_text)
    for column in [
        "original_control_slots",
        "python_eligible_controls",
        "no_python_controls",
        "snapshot_unknown_controls",
        "missing_clone_controls",
        "missing_monthly_history_controls",
        "no_prior_snapshot_controls",
        "has_any_python_control",
        "has_all_three_python_controls",
    ]:
        data[column] = pd.to_numeric(data[column], errors="coerce").astype("Int64")

    duplicated = data.duplicated(["treatment_key", "treatment_month"], keep=False)
    if duplicated.any():
        sample = data.loc[
            duplicated, ["treatment_repo", "treatment_month"]
        ].head(20)
        raise ValueError(
            "Coverage CSV contains duplicate treatment repository-month rows: "
            + repr(sample.to_dict(orient="records"))
        )
    return data


def classify_scope_rows(
    panel: pd.DataFrame,
    candidate_control_keys: set[str],
    start_period: pd.Period,
    end_period: pd.Period,
) -> pd.DataFrame:
    data = panel.copy()
    data["scope_role"] = "outside_scope"
    data["base_inclusion_status"] = "excluded_outside_scope"
    data["base_exclusion_reason"] = "outside_valid_treatment_or_candidate_control_scope"

    # Control-adoption metadata are retained in every output so that later
    # stages can verify that no post-adoption control row entered the model.
    data["control_has_adoption_event"] = 0
    data["control_event_effective"] = ""
    data["control_post_adoption_row"] = 0
    data["control_adoption_signal_without_event"] = 0

    in_window = data["time_period"].between(start_period, end_period)

    treatment_mask = data["dataset_source"].eq("treatment")
    valid_event = data["event_period"].notna()
    treatment_python = data["python_eligible"].eq(1)

    treatment_scope = treatment_mask & in_window
    data.loc[treatment_scope, "scope_role"] = "treatment"
    data.loc[treatment_scope & ~valid_event, "base_exclusion_reason"] = "missing_valid_event"
    data.loc[
        treatment_scope & valid_event & data["python_eligible"].eq(0),
        "base_exclusion_reason",
    ] = "treatment_no_python"
    data.loc[
        treatment_scope & valid_event & data["python_eligible"].isna(),
        "base_exclusion_reason",
    ] = "treatment_python_unknown"
    treatment_include = treatment_scope & valid_event & treatment_python
    data.loc[treatment_include, "base_inclusion_status"] = "included_python_pooled"
    data.loc[treatment_include, "base_exclusion_reason"] = ""

    control_scope = (
        data["dataset_source"].eq("control")
        & data["repo_key"].isin(candidate_control_keys)
        & in_window
    )
    data.loc[control_scope, "scope_role"] = "control"

    # A control repository can appear in the original control dataset and
    # nevertheless adopt Cursor later. Resolve one adoption month per control
    # repository from all nonblank event values, then censor rows at or after
    # that month. This keeps strictly pre-adoption rows as not-yet-treated
    # observations while preventing treated-control contamination.
    control_event_rows = data.loc[
        control_scope & data["event_period"].notna(),
        ["repo_key", "event_period"],
    ].drop_duplicates()
    if not control_event_rows.empty:
        event_counts = control_event_rows.groupby("repo_key")["event_period"].nunique()
        conflicts = event_counts[event_counts.gt(1)]
        if not conflicts.empty:
            conflict_keys = set(conflicts.index)
            sample = data.loc[
                control_scope & data["repo_key"].isin(conflict_keys),
                ["repo_name", "time", "event"],
            ].head(30)
            raise ValueError(
                "Candidate controls contain conflicting adoption months: "
                + repr(sample.to_dict(orient="records"))
            )
        control_event_map = (
            control_event_rows.drop_duplicates("repo_key")
            .set_index("repo_key")["event_period"]
            .to_dict()
        )
    else:
        control_event_map = {}

    effective_event = data["repo_key"].map(control_event_map)
    has_control_event = control_scope & effective_event.notna()
    data.loc[has_control_event, "control_has_adoption_event"] = 1
    data.loc[has_control_event, "control_event_effective"] = effective_event.loc[
        has_control_event
    ].astype(str)

    post_by_event = has_control_event & (data["time_period"] >= effective_event)
    post_by_flag = control_scope & (
        data["is_treatment"].eq(1) | data["cursor_flag"].eq(1)
    )
    post_adoption = post_by_event | post_by_flag
    data.loc[post_adoption, "control_post_adoption_row"] = 1
    data.loc[post_by_flag & ~has_control_event, "control_adoption_signal_without_event"] = 1

    data.loc[
        control_scope & data["python_eligible"].eq(0), "base_exclusion_reason"
    ] = "control_no_python"
    data.loc[
        control_scope & data["python_eligible"].isna(), "base_exclusion_reason"
    ] = "control_python_unknown"

    # Adoption censoring has priority over Python status because these rows
    # must never enter the untreated control pool, even when Python-eligible.
    data.loc[post_adoption, "base_exclusion_reason"] = "control_post_adoption_censored"

    control_include = (
        control_scope
        & data["python_eligible"].eq(1)
        & ~post_adoption
    )
    data.loc[control_include, "base_inclusion_status"] = "included_python_pooled"
    data.loc[control_include, "base_exclusion_reason"] = ""

    return data


def merge_treatment_coverage(
    pooled: pd.DataFrame, coverage: pd.DataFrame
) -> pd.DataFrame:
    data = pooled.copy()
    coverage_fields = [
        "treatment_key",
        "treatment_month",
        "original_control_slots",
        "python_eligible_controls",
        "no_python_controls",
        "snapshot_unknown_controls",
        "missing_clone_controls",
        "missing_monthly_history_controls",
        "no_prior_snapshot_controls",
        "has_any_python_control",
        "has_all_three_python_controls",
        "coverage_class",
    ]
    renamed = coverage[coverage_fields].rename(
        columns={"treatment_key": "repo_key", "treatment_month": "time"}
    )
    data = data.merge(renamed, on=["repo_key", "time"], how="left", validate="one_to_one")

    treatment_rows = data["scope_role"].eq("treatment")
    missing = treatment_rows & data["coverage_class"].isna()
    if missing.any():
        sample = data.loc[missing, ["repo_name", "time"]].head(20)
        raise ValueError(
            "Treatment candidate rows are missing run-x-a04 coverage records: "
            + repr(sample.to_dict(orient="records"))
        )
    return data


def add_time_and_model_columns(
    pooled: pd.DataFrame, start_period: pd.Period
) -> pd.DataFrame:
    data = pooled.copy()
    data["time_index"] = data["time_period"].map(
        lambda value: int(value.ordinal - start_period.ordinal + 1)
    )
    data["time_yyyymm"] = data["time"].str.replace("-", "", regex=False).astype(int)

    data["treatment_group"] = data["scope_role"].eq("treatment").astype(int)
    data["event_index"] = 0
    data["event_yyyymm"] = 0
    treatment = data["treatment_group"].eq(1)
    data.loc[treatment, "event_index"] = data.loc[treatment, "event_period"].map(
        lambda value: int(value.ordinal - start_period.ordinal + 1)
    )
    data.loc[treatment, "event_yyyymm"] = (
        data.loc[treatment, "event"].str.replace("-", "", regex=False).astype(int)
    )

    # Stable numeric repository IDs make the later R input deterministic.
    repo_names = sorted(data["repo_name"].unique().tolist(), key=str.casefold)
    repo_id_map = {name: index + 1 for index, name in enumerate(repo_names)}
    data["repo_id"] = data["repo_name"].map(repo_id_map).astype(int)

    for column in LOG1P_SOURCE_COLUMNS:
        numeric = pd.to_numeric(data[column], errors="coerce")
        invalid = numeric.notna() & numeric.lt(0)
        if invalid.any():
            sample = data.loc[invalid, ["repo_name", "time", column]].head(20)
            raise ValueError(
                f"Cannot apply log1p to negative {column} values: "
                + repr(sample.to_dict(orient="records"))
            )
        data[f"log_{column}"] = np.log1p(numeric)

    data["model_a_complete"] = data[MODEL_A_RAW_COLUMNS].notna().all(axis=1).astype(int)
    data["model_a_exclusion_reason"] = ""
    for column in MODEL_A_RAW_COLUMNS:
        missing = data[column].isna()
        data.loc[
            missing & data["model_a_exclusion_reason"].eq(""),
            "model_a_exclusion_reason",
        ] = f"missing_{column}"

    # Model C will use the same pooled sample after ncloc_py is produced.
    data["model_c_snapshot_key"] = (
        data["dataset_source"].astype(str)
        + "|"
        + data["repo_name"].astype(str)
        + "|"
        + data["latest_commit_effective"].astype(str)
    )

    return data


def build_treatment_estimability_audit(
    model_a_complete: pd.DataFrame,
) -> pd.DataFrame:
    treatment = model_a_complete[
        model_a_complete["scope_role"].eq("treatment")
    ].copy()
    treatment["is_pre_treatment"] = (
        treatment["time_index"] < treatment["event_index"]
    ).astype(int)
    treatment["is_post_treatment"] = (
        treatment["time_index"] >= treatment["event_index"]
    ).astype(int)

    audit = (
        treatment.groupby(
            ["repo_name", "repo_key", "event", "event_index"], as_index=False
        )
        .agg(
            model_a_complete_rows=("time", "size"),
            pre_treatment_complete_rows=("is_pre_treatment", "sum"),
            post_treatment_complete_rows=("is_post_treatment", "sum"),
            first_complete_month=("time", "min"),
            last_complete_month=("time", "max"),
        )
        .sort_values("repo_name")
        .reset_index(drop=True)
    )
    audit["borusyak_estimable"] = (
        audit["pre_treatment_complete_rows"].gt(0)
        & audit["post_treatment_complete_rows"].gt(0)
    ).astype(int)
    audit["estimability_reason"] = "estimable"
    audit.loc[
        audit["pre_treatment_complete_rows"].eq(0),
        "estimability_reason",
    ] = "no_pre_treatment_complete_case_row"
    audit.loc[
        audit["post_treatment_complete_rows"].eq(0),
        "estimability_reason",
    ] = "no_post_treatment_complete_case_row"
    return audit


def build_estimable_model_a_panel(
    model_a_complete: pd.DataFrame,
    pairs: pd.DataFrame,
    treatment_audit: pd.DataFrame,
) -> tuple[pd.DataFrame, set[str], set[str]]:
    estimable_treatment_keys = set(
        treatment_audit.loc[
            treatment_audit["borusyak_estimable"].eq(1), "repo_key"
        ]
    )
    estimable_control_keys = set(
        pairs.loc[
            pairs["treatment_key"].isin(estimable_treatment_keys), "control_key"
        ]
    )

    keep = (
        model_a_complete["scope_role"].eq("treatment")
        & model_a_complete["repo_key"].isin(estimable_treatment_keys)
    ) | (
        model_a_complete["scope_role"].eq("control")
        & model_a_complete["repo_key"].isin(estimable_control_keys)
    )
    estimable = model_a_complete.loc[keep].copy()

    if estimable.empty:
        raise ValueError("No Model A rows remain after Borusyak estimability checks")

    retained_treatment = estimable[estimable["scope_role"].eq("treatment")].copy()
    retained_treatment["is_pre"] = (
        retained_treatment["time_index"] < retained_treatment["event_index"]
    ).astype(int)
    retained_counts = retained_treatment.groupby("repo_key")["is_pre"].sum()
    if (retained_counts <= 0).any():
        raise ValueError("Estimable Model A panel contains treatment units without pre-treatment rows")

    return estimable, estimable_treatment_keys, estimable_control_keys


def build_control_pool_audit(
    reuse: pd.DataFrame,
    pairs: pd.DataFrame,
    classified_panel: pd.DataFrame,
    pooled: pd.DataFrame,
    model_a_complete: pd.DataFrame,
    model_a_estimable: pd.DataFrame,
    estimable_treatment_keys: set[str],
) -> pd.DataFrame:
    candidate = reuse[reuse["matched_treatment_count_candidates"].gt(0)].copy()
    candidate = candidate.sort_values("control_repo").reset_index(drop=True)

    estimable_pair_counts = (
        pairs[pairs["treatment_key"].isin(estimable_treatment_keys)]
        .groupby("control_key", as_index=False)
        .agg(matched_estimable_treatment_count=("treatment_key", "nunique"))
    )
    candidate = candidate.merge(estimable_pair_counts, on="control_key", how="left")
    candidate["matched_estimable_treatment_count"] = pd.to_numeric(
        candidate["matched_estimable_treatment_count"], errors="coerce"
    ).fillna(0).astype(int)
    candidate["linked_to_estimable_treatment"] = (
        candidate["matched_estimable_treatment_count"].gt(0)
    ).astype(int)

    panel_controls = classified_panel[
        classified_panel["scope_role"].eq("control")
    ].copy()
    pooled_controls = pooled[pooled["scope_role"].eq("control")].copy()
    complete_controls = model_a_complete[
        model_a_complete["scope_role"].eq("control")
    ].copy()
    estimable_controls = model_a_estimable[
        model_a_estimable["scope_role"].eq("control")
    ].copy()

    def aggregate_counts(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["control_key"])
        grouped = df.groupby("repo_key", as_index=False).agg(
            **{
                f"{prefix}_row_count": ("time", "size"),
                f"{prefix}_first_month": ("time", "min"),
                f"{prefix}_last_month": ("time", "max"),
            }
        )
        return grouped.rename(columns={"repo_key": "control_key"})

    for frame, prefix in [
        (panel_controls, "panel"),
        (pooled_controls, "python_panel"),
        (complete_controls, "model_a_complete"),
        (estimable_controls, "model_a_estimable"),
    ]:
        candidate = candidate.merge(
            aggregate_counts(frame, prefix), on="control_key", how="left"
        )

    status_counts = (
        panel_controls.assign(
            python_status=panel_controls["python_eligible"].map(
                lambda value: (
                    "python" if value == 1 else "no_python" if value == 0 else "unknown"
                )
            )
        )
        .groupby(["repo_key", "python_status"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
        .rename(columns={"repo_key": "control_key"})
    )
    if not status_counts.empty:
        status_counts = status_counts.rename(
            columns={
                "python": "panel_python_rows",
                "no_python": "panel_no_python_rows",
                "unknown": "panel_unknown_python_rows",
            }
        )
        candidate = candidate.merge(status_counts, on="control_key", how="left")

    if not panel_controls.empty:
        adoption_audit = (
            panel_controls.groupby("repo_key", as_index=False)
            .agg(
                control_has_adoption_event=("control_has_adoption_event", "max"),
                control_event_effective=(
                    "control_event_effective",
                    lambda values: next(
                        (clean_text(value) for value in values if clean_text(value)),
                        "",
                    ),
                ),
                panel_post_adoption_rows=("control_post_adoption_row", "sum"),
                panel_post_adoption_python_rows=(
                    "python_eligible",
                    lambda values: 0,
                ),
                control_adoption_signal_without_event_rows=(
                    "control_adoption_signal_without_event", "sum"
                ),
            )
            .rename(columns={"repo_key": "control_key"})
        )
        post_python = (
            panel_controls.loc[panel_controls["control_post_adoption_row"].eq(1)]
            .groupby("repo_key")['python_eligible']
            .apply(lambda values: int(values.eq(1).sum()))
            .rename("panel_post_adoption_python_rows")
            .reset_index()
            .rename(columns={"repo_key": "control_key"})
        )
        adoption_audit = adoption_audit.drop(
            columns=["panel_post_adoption_python_rows"]
        ).merge(post_python, on="control_key", how="left")
        candidate = candidate.merge(adoption_audit, on="control_key", how="left")

    count_columns = [
        "panel_row_count",
        "python_panel_row_count",
        "model_a_complete_row_count",
        "model_a_estimable_row_count",
        "panel_no_python_rows",
        "panel_python_rows",
        "panel_unknown_python_rows",
        "control_has_adoption_event",
        "panel_post_adoption_rows",
        "panel_post_adoption_python_rows",
        "control_adoption_signal_without_event_rows",
    ]
    for column in count_columns:
        if column not in candidate.columns:
            candidate[column] = 0
        candidate[column] = pd.to_numeric(
            candidate[column], errors="coerce"
        ).fillna(0).astype(int)
    if "control_event_effective" not in candidate.columns:
        candidate["control_event_effective"] = ""
    candidate["control_event_effective"] = candidate[
        "control_event_effective"
    ].map(clean_text)

    candidate["control_pool_status"] = "no_panel_rows"
    has_panel = candidate["panel_row_count"].gt(0)
    no_python_only = (
        has_panel
        & candidate["panel_python_rows"].eq(0)
        & candidate["panel_no_python_rows"].gt(0)
        & candidate["panel_unknown_python_rows"].eq(0)
    )
    unknown_only = (
        has_panel
        & candidate["panel_python_rows"].eq(0)
        & candidate["panel_no_python_rows"].eq(0)
        & candidate["panel_unknown_python_rows"].gt(0)
    )
    mixed_unusable = (
        has_panel
        & candidate["panel_python_rows"].eq(0)
        & candidate["panel_no_python_rows"].gt(0)
        & candidate["panel_unknown_python_rows"].gt(0)
    )
    all_python_censored = (
        has_panel
        & candidate["python_panel_row_count"].eq(0)
        & candidate["panel_python_rows"].gt(0)
        & candidate["panel_post_adoption_python_rows"].eq(
            candidate["panel_python_rows"]
        )
    )

    candidate.loc[no_python_only, "control_pool_status"] = "panel_rows_no_python"
    candidate.loc[unknown_only, "control_pool_status"] = "panel_rows_python_unknown"
    candidate.loc[mixed_unusable, "control_pool_status"] = "panel_rows_no_python_or_unknown"
    candidate.loc[all_python_censored, "control_pool_status"] = "all_python_rows_post_adoption_censored"
    candidate.loc[
        candidate["python_panel_row_count"].gt(0), "control_pool_status"
    ] = "python_panel_available"
    candidate.loc[
        candidate["model_a_complete_row_count"].gt(0), "control_pool_status"
    ] = "model_a_complete_available"
    candidate.loc[
        candidate["model_a_estimable_row_count"].gt(0), "control_pool_status"
    ] = "model_a_estimable_available"
    candidate.loc[
        candidate["linked_to_estimable_treatment"].eq(0)
        & candidate["model_a_complete_row_count"].gt(0),
        "control_pool_status",
    ] = "not_linked_to_estimable_treatment"

    return candidate


def build_model_c_manifest(pooled: pd.DataFrame) -> pd.DataFrame:
    data = pooled.copy()
    if data["latest_commit_effective"].eq("").any():
        sample = data.loc[
            data["latest_commit_effective"].eq(""),
            ["dataset_source", "repo_name", "time"],
        ].head(20)
        raise ValueError(
            "Python pooled rows contain blank effective commits: "
            + repr(sample.to_dict(orient="records"))
        )

    aggregation = {
        "repo_month_rows": ("time", "size"),
        "first_panel_month": ("time", "min"),
        "last_panel_month": ("time", "max"),
        "commit_resolution_values": (
            "commit_resolution",
            lambda values: " | ".join(sorted({clean_text(value) for value in values if clean_text(value)})),
        ),
        "max_months_since_observed_commit": ("months_since_observed_commit", "max"),
    }
    for optional in [
        "clone_path",
        "python_file_count_all",
        "python_file_count_source",
        "tracked_file_count",
    ]:
        if optional in data.columns:
            if optional == "clone_path":
                aggregation[optional] = (optional, "first")
            else:
                aggregation[optional] = (optional, "max")

    if "ncloc" in data.columns:
        inconsistent_ncloc = (
            data.groupby(
                ["dataset_source", "repo_name", "latest_commit_effective"]
            )["ncloc"]
            .nunique(dropna=False)
            .gt(1)
        )
        if inconsistent_ncloc.any():
            raise ValueError(
                "The same Model C snapshot has inconsistent final NCLOC values"
            )
        aggregation["ncloc_model_a"] = ("ncloc", "first")

    if "ncloc_source" in data.columns:
        aggregation["ncloc_source_values"] = (
            "ncloc_source",
            lambda values: " | ".join(
                sorted({clean_text(value) for value in values if clean_text(value)})
            ),
        )
    if "ncloc_recovery_applied" in data.columns:
        aggregation["ncloc_recovery_applied_repo_month_rows"] = (
            "ncloc_recovery_applied", "sum"
        )
    if "ncloc_recovery_snapshot_key" in data.columns:
        aggregation["ncloc_recovery_snapshot_key"] = (
            "ncloc_recovery_snapshot_key",
            lambda values: next(
                (clean_text(value) for value in values if clean_text(value)), ""
            ),
        )

    manifest = (
        data.groupby(
            ["dataset_source", "repo_name", "repo_key", "latest_commit_effective"],
            as_index=False,
        )
        .agg(**aggregation)
        .sort_values(["dataset_source", "repo_name", "first_panel_month"])
        .reset_index(drop=True)
    )
    manifest["ncloc_py"] = pd.NA
    manifest["ncloc_py_status"] = "pending_sonarqube"
    return manifest


def make_exclusions(
    classified: pd.DataFrame,
    pooled: pd.DataFrame,
    model_a_complete: pd.DataFrame,
    estimable_treatment_keys: set[str],
    estimable_control_keys: set[str],
) -> pd.DataFrame:
    base_excluded = classified[
        classified["scope_role"].isin(["treatment", "control"])
        & classified["base_inclusion_status"].ne("included_python_pooled")
    ].copy()
    base_excluded["exclusion_stage"] = "python_pooled_panel"
    base_excluded["exclusion_reason"] = base_excluded["base_exclusion_reason"]

    complete_case_excluded = pooled[pooled["model_a_complete"].eq(0)].copy()
    complete_case_excluded["exclusion_stage"] = "model_a_complete_case"
    complete_case_excluded["exclusion_reason"] = complete_case_excluded[
        "model_a_exclusion_reason"
    ]

    estimability_excluded = model_a_complete[
        (
            model_a_complete["scope_role"].eq("treatment")
            & ~model_a_complete["repo_key"].isin(estimable_treatment_keys)
        )
        | (
            model_a_complete["scope_role"].eq("control")
            & ~model_a_complete["repo_key"].isin(estimable_control_keys)
        )
    ].copy()
    estimability_excluded["exclusion_stage"] = "model_a_estimability"
    estimability_excluded["exclusion_reason"] = ""
    estimability_excluded.loc[
        estimability_excluded["scope_role"].eq("treatment"),
        "exclusion_reason",
    ] = "treatment_has_no_pre_treatment_complete_case_row"
    estimability_excluded.loc[
        estimability_excluded["scope_role"].eq("control"),
        "exclusion_reason",
    ] = "control_not_linked_to_estimable_treatment"

    columns = [
        "exclusion_stage",
        "exclusion_reason",
        "scope_role",
        "dataset_source",
        "repo_name",
        "time",
        "event",
        "time_to_event",
        "python_eligible",
        "scan_status",
        "commits",
        "lines_added",
        "age",
        "ncloc",
        "ncloc_original",
        "ncloc_recovered",
        "ncloc_source",
        "ncloc_recovery_applied",
        "ncloc_recovery_snapshot_key",
        "contributors",
        "stars",
        "issues",
        "latest_commit_effective",
        "commit_resolution",
    ]
    frames = [base_excluded, complete_case_excluded, estimability_excluded]
    exclusions = pd.concat(
        [frame.reindex(columns=columns) for frame in frames],
        ignore_index=True,
    )
    return exclusions.sort_values(
        ["exclusion_stage", "scope_role", "repo_name", "time"]
    ).reset_index(drop=True)


def append_summary(rows: list[dict[str, object]], section: str, metric: str, value: object, note: str = "") -> None:
    rows.append({"section": section, "metric": metric, "value": value, "note": note})


def build_summary(
    panel: pd.DataFrame,
    reuse: pd.DataFrame,
    pairs: pd.DataFrame,
    classified: pd.DataFrame,
    pooled: pd.DataFrame,
    model_a_complete: pd.DataFrame,
    model_a_estimable: pd.DataFrame,
    treatment_audit: pd.DataFrame,
    control_audit: pd.DataFrame,
    manifest: pd.DataFrame,
    exclusions: pd.DataFrame,
    recovery_audit: dict[str, int],
    start_period: pd.Period,
    end_period: pd.Period,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    append_summary(rows, "implementation", "version", "v3")
    append_summary(rows, "definition", "panel_design", "original_style_unique_repository_month_pool")
    append_summary(rows, "definition", "treatment_rule", "valid_event_and_python_eligible_repo_month")
    append_summary(rows, "definition", "control_rule", "candidate_unique_control_and_python_eligible_repo_month")
    append_summary(rows, "definition", "control_reuse_weighting", "none", "A reused control repository-month appears once in the pooled panel.")
    append_summary(rows, "definition", "control_adoption_handling", "censor_at_adoption_month", "A candidate control that later adopts Cursor contributes only strictly pre-adoption rows.")
    append_summary(rows, "definition", "analysis_window", f"{start_period}:{end_period}")
    append_summary(rows, "definition", "model_a_complete_case", "commits_lines_added_age_ncloc_contributors_stars_issues_nonmissing")
    append_summary(rows, "definition", "ncloc_recovery", "fill_originally_missing_values_only", "Strict match on dataset source, repository, month, and effective commit; existing values are never overwritten.")
    append_summary(rows, "definition", "borusyak_estimability", "treated_repository_requires_pre_and_post_complete_case_rows")
    append_summary(rows, "definition", "estimable_control_pool", "controls_linked_to_estimable_treatments_only")
    append_summary(rows, "definition", "model_c_status", "snapshot_manifest_for_model_a_estimable_panel", "ncloc_py is pending Python-only SonarQube.")

    candidate_controls = reuse[reuse["matched_treatment_count_candidates"].gt(0)]
    append_summary(rows, "input", "enriched_panel_rows", len(panel))
    append_summary(rows, "input", "matching_pair_rows", len(pairs))
    append_summary(rows, "input", "candidate_unique_controls", len(candidate_controls))
    append_summary(rows, "input", "candidate_control_assignments", int(candidate_controls["matched_treatment_count_candidates"].sum()))

    append_summary(rows, "ncloc_recovery", "patch_rows", recovery_audit["patch_rows"])
    append_summary(rows, "ncloc_recovery", "matched_rows", recovery_audit["matched_rows"])
    append_summary(rows, "ncloc_recovery", "applied_rows", recovery_audit["applied_rows"])
    append_summary(rows, "ncloc_recovery", "treatment_applied_rows", recovery_audit["treatment_applied_rows"])
    append_summary(rows, "ncloc_recovery", "control_applied_rows", recovery_audit["control_applied_rows"])
    append_summary(rows, "ncloc_recovery", "overwritten_existing_rows", recovery_audit["overwritten_existing_rows"])
    append_summary(rows, "ncloc_recovery", "unmatched_rows", recovery_audit["unmatched_rows"])
    append_summary(rows, "ncloc_recovery", "pooled_rows_using_recovered_ncloc", int(pooled["ncloc_recovery_applied"].sum()))
    append_summary(rows, "ncloc_recovery", "estimable_rows_using_recovered_ncloc", int(model_a_estimable["ncloc_recovery_applied"].sum()))
    append_summary(rows, "ncloc_recovery", "pooled_rows_still_missing_ncloc", int(pooled["ncloc"].isna().sum()))

    treatment_scope = classified[classified["scope_role"].eq("treatment")]
    control_scope = classified[classified["scope_role"].eq("control")]
    append_summary(rows, "scope", "treatment_panel_rows", len(treatment_scope))
    append_summary(rows, "scope", "candidate_control_panel_rows", len(control_scope))
    append_summary(rows, "scope", "candidate_control_repositories_in_panel", control_scope["repo_name"].nunique())
    append_summary(rows, "scope", "candidate_controls_missing_from_panel", int((control_audit["panel_row_count"] == 0).sum()))

    for role in ["treatment", "control"]:
        role_pooled = pooled[pooled["scope_role"].eq(role)]
        role_complete = model_a_complete[model_a_complete["scope_role"].eq(role)]
        role_estimable = model_a_estimable[model_a_estimable["scope_role"].eq(role)]
        append_summary(rows, "pooled_python", f"{role}_rows", len(role_pooled))
        append_summary(rows, "pooled_python", f"{role}_repositories", role_pooled["repo_name"].nunique())
        append_summary(rows, "model_a_complete", f"{role}_rows", len(role_complete))
        append_summary(rows, "model_a_complete", f"{role}_repositories", role_complete["repo_name"].nunique())
        append_summary(rows, "model_a_estimable", f"{role}_rows", len(role_estimable))
        append_summary(rows, "model_a_estimable", f"{role}_repositories", role_estimable["repo_name"].nunique())

    append_summary(rows, "pooled_python", "total_rows", len(pooled))
    append_summary(rows, "pooled_python", "total_repositories", pooled["repo_name"].nunique())
    append_summary(rows, "pooled_python", "duplicate_repo_month_rows", int(pooled.duplicated(["repo_key", "time"]).sum()))
    append_summary(rows, "model_a_complete", "total_rows", len(model_a_complete))
    append_summary(rows, "model_a_complete", "total_repositories", model_a_complete["repo_name"].nunique())
    append_summary(rows, "model_a_complete", "rows_excluded_for_missing_fields", int((pooled["model_a_complete"] == 0).sum()))
    append_summary(rows, "model_a_estimable", "total_rows", len(model_a_estimable))
    append_summary(rows, "model_a_estimable", "total_repositories", model_a_estimable["repo_name"].nunique())

    append_summary(rows, "estimability", "candidate_treatment_repositories", len(treatment_audit))
    append_summary(rows, "estimability", "estimable_treatment_repositories", int(treatment_audit["borusyak_estimable"].sum()))
    append_summary(rows, "estimability", "treatment_repositories_without_pre_rows", int((treatment_audit["pre_treatment_complete_rows"] == 0).sum()))
    append_summary(rows, "estimability", "treatment_repositories_without_post_rows", int((treatment_audit["post_treatment_complete_rows"] == 0).sum()))
    append_summary(rows, "estimability", "unique_controls_linked_to_estimable_treatments", int((control_audit["linked_to_estimable_treatment"] == 1).sum()))
    append_summary(rows, "estimability", "controls_contributing_model_a_rows", int((control_audit["model_a_estimable_row_count"] > 0).sum()))

    missing_model_a = pooled.loc[pooled["model_a_complete"].eq(0), "model_a_exclusion_reason"].value_counts()
    for reason, count in missing_model_a.items():
        append_summary(rows, "model_a_exclusion", str(reason), int(count))

    base_reasons = classified.loc[
        classified["scope_role"].isin(["treatment", "control"])
        & classified["base_inclusion_status"].ne("included_python_pooled"),
        "base_exclusion_reason",
    ].value_counts()
    for reason, count in base_reasons.items():
        append_summary(rows, "python_exclusion", str(reason), int(count))

    append_summary(rows, "control_pool", "controls_with_panel_rows", int((control_audit["panel_row_count"] > 0).sum()))
    append_summary(rows, "control_pool", "controls_with_python_panel_rows", int((control_audit["python_panel_row_count"] > 0).sum()))
    append_summary(rows, "control_pool", "controls_with_model_a_complete_rows", int((control_audit["model_a_complete_row_count"] > 0).sum()))
    append_summary(rows, "control_pool", "controls_with_model_a_estimable_rows", int((control_audit["model_a_estimable_row_count"] > 0).sum()))
    append_summary(rows, "control_adoption", "candidate_controls_with_adoption_event", int((control_audit["control_has_adoption_event"] > 0).sum()))
    append_summary(rows, "control_adoption", "post_adoption_rows_censored", int((classified["base_exclusion_reason"] == "control_post_adoption_censored").sum()))
    append_summary(rows, "control_adoption", "post_adoption_python_rows_censored", int(((classified["base_exclusion_reason"] == "control_post_adoption_censored") & classified["python_eligible"].eq(1)).sum()))
    append_summary(rows, "control_adoption", "adoption_signal_without_event_rows", int(classified["control_adoption_signal_without_event"].sum()))
    append_summary(rows, "model_c", "unique_snapshots_pending_ncloc_py", len(manifest))
    append_summary(rows, "qc", "exclusion_rows", len(exclusions))
    append_summary(rows, "qc", "pooled_future_event_index_errors", int(((pooled["treatment_group"] == 1) & (pooled["event_index"] <= 0)).sum()))
    append_summary(rows, "qc", "pooled_control_post_adoption_rows", int((pooled["scope_role"].eq("control") & pooled["control_post_adoption_row"].eq(1)).sum()))
    append_summary(rows, "qc", "pooled_control_is_treatment_rows", int((pooled["scope_role"].eq("control") & pooled["is_treatment"].eq(1)).sum()))
    append_summary(rows, "qc", "pooled_control_cursor_true_rows", int((pooled["scope_role"].eq("control") & pooled["cursor_flag"].eq(1)).sum()))
    append_summary(rows, "qc", "estimable_duplicate_repo_month_rows", int(model_a_estimable.duplicated(["repo_key", "time"]).sum()))

    return pd.DataFrame(rows)


def order_panel_columns(data: pd.DataFrame) -> pd.DataFrame:
    preferred = [
        "repo_id",
        "repo_name",
        "dataset_source",
        "scope_role",
        "treatment_group",
        "time",
        "time_index",
        "time_yyyymm",
        "event",
        "event_index",
        "event_yyyymm",
        "post_event",
        "time_to_event",
        "control_has_adoption_event",
        "control_event_effective",
        "control_post_adoption_row",
        "control_adoption_signal_without_event",
        "cursor_flag",
        "commits",
        "log_commits",
        "lines_added",
        "log_lines_added",
        "lines_removed",
        "contributors",
        "log_contributors",
        "stars",
        "log_stars",
        "issues",
        "log_issues",
        "issue_comments",
        "age",
        "log_age",
        "ncloc",
        "ncloc_original",
        "ncloc_recovered",
        "ncloc_source",
        "ncloc_recovery_applied",
        "ncloc_recovery_snapshot_key",
        "ncloc_recovery_scanner_log",
        "ncloc_recovery_project_key",
        "ncloc_recovery_project_version",
        "ncloc_recovery_status",
        "ncloc_recovery_git_precheck_status",
        "model_a_complete",
        "model_a_exclusion_reason",
        "python_eligible",
        "scan_status",
        "latest_commit_original",
        "latest_commit_effective",
        "latest_commit",
        "commit_resolution",
        "months_since_observed_commit",
        "model_c_snapshot_key",
        "original_control_slots",
        "python_eligible_controls",
        "no_python_controls",
        "snapshot_unknown_controls",
        "missing_clone_controls",
        "missing_monthly_history_controls",
        "no_prior_snapshot_controls",
        "has_any_python_control",
        "has_all_three_python_controls",
        "coverage_class",
    ]
    ordered = [column for column in preferred if column in data.columns]
    remaining = [column for column in data.columns if column not in ordered and not column.endswith("_period") and column != "repo_key"]
    return data[ordered + remaining]


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logging.info("Wrote %d rows to %s", len(df), path)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    try:
        start_period, end_period = validate_args(args)

        pairs = read_csv_stable(
            args.matching_pairs_file,
            ["treatment_repo", "control_repo", "pair_status"],
        )
        panel = read_csv_stable(args.panel_file, STRING_COLUMNS)
        reuse = read_csv_stable(
            args.control_reuse_file,
            ["control_repo", "pair_statuses", "first_month", "last_month"],
        )
        coverage = read_csv_stable(
            args.coverage_file,
            ["treatment_repo", "treatment_month", "coverage_class"],
        )
        ncloc_patch = read_csv_stable(
            args.ncloc_recovery_patch_file,
            [
                "snapshot_key",
                "dataset_source",
                "scope_role",
                "repo_name",
                "time",
                "latest_commit_effective",
                "project_key",
                "project_version",
                "status",
                "git_precheck_status",
                "scanner_log_path",
                "ncloc_patch_source",
            ],
        )

        pairs = normalize_pairs(pairs)
        panel = normalize_panel(panel)
        reuse = normalize_reuse(reuse)
        coverage = normalize_coverage(coverage)
        ncloc_patch = normalize_ncloc_patch(ncloc_patch)
        panel, recovery_audit = apply_ncloc_recovery(panel, ncloc_patch)

        candidate_controls = reuse[reuse["matched_treatment_count_candidates"].gt(0)].copy()
        candidate_control_keys = set(candidate_controls["control_key"])
        if len(candidate_control_keys) == 0:
            raise ValueError("No candidate controls were found in the control reuse input")

        classified = classify_scope_rows(
            panel, candidate_control_keys, start_period, end_period
        )
        pooled = classified[
            classified["base_inclusion_status"].eq("included_python_pooled")
        ].copy()
        pooled = merge_treatment_coverage(pooled, coverage)
        pooled = add_time_and_model_columns(pooled, start_period)

        contaminated_controls = pooled[
            pooled["scope_role"].eq("control")
            & (
                pooled["control_post_adoption_row"].eq(1)
                | pooled["is_treatment"].eq(1)
                | pooled["cursor_flag"].eq(1)
            )
        ]
        if not contaminated_controls.empty:
            sample = contaminated_controls[
                [
                    "repo_name",
                    "time",
                    "event",
                    "control_event_effective",
                    "is_treatment",
                    "cursor",
                ]
            ].head(20)
            raise ValueError(
                "Pooled panel contains post-adoption or treated control rows: "
                + repr(sample.to_dict(orient="records"))
            )

        duplicated = pooled.duplicated(["repo_key", "time"], keep=False)
        if duplicated.any():
            sample = pooled.loc[duplicated, ["repo_name", "time", "scope_role"]].head(20)
            raise ValueError(
                "Pooled panel contains duplicate repository-month rows: "
                + repr(sample.to_dict(orient="records"))
            )

        model_a_complete = pooled[pooled["model_a_complete"].eq(1)].copy()
        treatment_audit = build_treatment_estimability_audit(model_a_complete)
        (
            model_a_estimable,
            estimable_treatment_keys,
            estimable_control_keys,
        ) = build_estimable_model_a_panel(model_a_complete, pairs, treatment_audit)

        control_audit = build_control_pool_audit(
            reuse,
            pairs,
            classified,
            pooled,
            model_a_complete,
            model_a_estimable,
            estimable_treatment_keys,
        )
        manifest = build_model_c_manifest(model_a_estimable)
        exclusions = make_exclusions(
            classified,
            pooled,
            model_a_complete,
            estimable_treatment_keys,
            estimable_control_keys,
        )
        summary = build_summary(
            panel,
            reuse,
            pairs,
            classified,
            pooled,
            model_a_complete,
            model_a_estimable,
            treatment_audit,
            control_audit,
            manifest,
            exclusions,
            recovery_audit,
            start_period,
            end_period,
        )

        pooled_output = order_panel_columns(pooled.sort_values(["repo_name", "time"]))
        complete_output = order_panel_columns(
            model_a_complete.sort_values(["repo_name", "time"])
        )
        estimable_output = order_panel_columns(
            model_a_estimable.sort_values(["repo_name", "time"])
        )

        write_csv(pooled_output, args.pooled_panel_output)
        write_csv(complete_output, args.model_a_complete_case_output)
        write_csv(estimable_output, args.model_a_panel_output)
        write_csv(treatment_audit, args.treatment_estimability_audit_output)
        write_csv(exclusions, args.row_exclusions_output)
        write_csv(control_audit, args.control_pool_audit_output)
        write_csv(manifest, args.model_c_snapshot_manifest_output)
        write_csv(summary, args.summary_output)

        logging.info(
            "Completed run-x-a05-v3: %d pooled rows, %d complete-case rows, %d estimable Model A rows, %d Model C snapshots",
            len(pooled_output),
            len(complete_output),
            len(estimable_output),
            len(manifest),
        )
        return 0
    except Exception:
        logging.exception("run-x-a05 failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
