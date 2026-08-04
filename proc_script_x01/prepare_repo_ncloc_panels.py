#!/usr/bin/env python3
"""Prepare C05 Python-primary repository-level NCLOC DiD panels.

This program joins the paper-provided whole-repository NCLOC with the locally
recomputed cloc NCLOC from C04b. It preserves the full C03 paper scope, creates
an exact common sample for backend comparison, derives sequential calendar and
adoption indices, and writes Borusyak-estimable panels.

The program never averages, calibrates, or imputes one NCLOC backend from the
other. Missing paper NCLOC remains missing. Clone-unavailable repositories do
not receive local NCLOC values.

Primary analysis specifications:
1. Paper NCLOC on the paper complete-case sample.
2. Paper NCLOC on the exact paper/local common sample.
3. Local cloc paper-taxonomy NCLOC on the same exact common sample.

A fourth local all-recognized cloc panel is emitted only as a robustness input.

Because the first stage includes repository fixed effects and is fitted on
untreated observations, a treated repository needs at least one pre-adoption
row and at least one treated row. Complete-case and Borusyak-estimable panels
are written separately so this additional support restriction is explicit and
auditable.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


IMPLEMENTATION_VERSION = "v1"

PAPER_PANEL_REQUIRED_COLUMNS = {
    "scope_role",
    "repo_name",
    "repo_name_key",
    "time",
    "is_treatment",
    "event",
    "post_event",
    "time_to_event",
    "commits",
    "lines_added",
    "contributors",
    "stars",
    "issues",
    "age",
    "paper_ncloc",
    "dataset_source",
    "clone_available",
    "snapshot_available",
    "repo_snapshot_key",
    "resolved_commit",
}

LOCAL_PANEL_REQUIRED_COLUMNS = {
    "scope_role",
    "repo_name",
    "repo_name_key",
    "time",
    "repo_snapshot_key",
    "cloc_available",
    "cloc_snapshot_status",
    "ncloc_local_cloc_all_recognized",
    "ncloc_local_cloc_paper_taxonomy",
    "ncloc_local_cloc_not_in_paper_taxonomy",
    "paper_taxonomy_code_share",
    "paper_taxonomy_version",
    "paper_taxonomy_count_backend",
}

MODEL_RAW_COLUMNS = [
    "commits",
    "lines_added",
    "age",
    "contributors",
    "stars",
    "issues",
]

LOG1P_COLUMNS = {
    "commits": "log_commits",
    "lines_added": "log_lines_added",
    "age": "log_age",
    "contributors": "log_contributors",
    "stars": "log_stars",
    "issues": "log_issues",
}

KEY_COLUMNS = ["scope_role", "repo_name_key", "time"]


class QcCollector:
    """Collect machine-readable quality-control checks."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(
        self,
        category: str,
        check_name: str,
        observed: Any,
        expected: Any,
        status: str,
        note: str = "",
    ) -> None:
        self.rows.append(
            {
                "category": category,
                "check_name": check_name,
                "observed": observed,
                "expected": expected,
                "status": status,
                "note": note,
            }
        )

    def exact(
        self,
        category: str,
        check_name: str,
        observed: int | float,
        expected: int | float,
        note: str = "",
    ) -> None:
        self.add(
            category,
            check_name,
            observed,
            expected,
            "pass" if observed == expected else "fail",
            note,
        )

    def zero(self, category: str, check_name: str, observed: int, note: str = "") -> None:
        self.exact(category, check_name, observed, 0, note)

    def true(self, category: str, check_name: str, condition: bool, note: str = "") -> None:
        self.add(
            category,
            check_name,
            int(bool(condition)),
            1,
            "pass" if condition else "fail",
            note,
        )

    def dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)

    def failure_count(self) -> int:
        return sum(row["status"] == "fail" for row in self.rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare paper and local whole-repository NCLOC DiD panels."
    )
    parser.add_argument("--paper-panel-file", required=True, type=Path)
    parser.add_argument("--local-repo-month-file", required=True, type=Path)

    parser.add_argument("--combined-panel-output", required=True, type=Path)
    parser.add_argument("--paper-full-complete-output", required=True, type=Path)
    parser.add_argument("--paper-full-estimable-output", required=True, type=Path)
    parser.add_argument("--paper-common-complete-output", required=True, type=Path)
    parser.add_argument("--paper-common-estimable-output", required=True, type=Path)
    parser.add_argument("--local-taxonomy-common-complete-output", required=True, type=Path)
    parser.add_argument("--local-taxonomy-common-estimable-output", required=True, type=Path)
    parser.add_argument("--local-all-common-complete-output", required=True, type=Path)
    parser.add_argument("--local-all-common-estimable-output", required=True, type=Path)
    parser.add_argument("--backend-comparison-output", required=True, type=Path)
    parser.add_argument("--treatment-estimability-output", required=True, type=Path)
    parser.add_argument("--legacy-timing-audit-output", required=True, type=Path)
    parser.add_argument("--sample-summary-output", required=True, type=Path)
    parser.add_argument("--qc-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)

    parser.add_argument("--strict-expected-counts", type=int, choices=[0, 1], default=1)
    parser.add_argument("--expected-paper-panel-rows", type=int, default=2461)
    parser.add_argument("--expected-treatment-paper-rows", type=int, default=1223)
    parser.add_argument("--expected-control-paper-rows", type=int, default=1238)
    parser.add_argument("--expected-paper-repositories", type=int, default=248)
    parser.add_argument("--expected-treatment-repositories", type=int, default=121)
    parser.add_argument("--expected-control-repositories", type=int, default=127)
    parser.add_argument("--expected-local-rows", type=int, default=2411)
    parser.add_argument("--expected-local-repositories", type=int, default=242)
    parser.add_argument("--expected-paper-ncloc-missing", type=int, default=168)
    parser.add_argument("--expected-paper-full-complete-rows", type=int, default=2293)
    parser.add_argument("--expected-common-rows", type=int, default=2250)
    parser.add_argument("--expected-paper-full-estimable-rows", type=int, default=2127)
    parser.add_argument("--expected-common-estimable-rows", type=int, default=2090)
    parser.add_argument("--expected-paper-full-estimable-treatment-repositories", type=int, default=72)
    parser.add_argument("--expected-common-estimable-treatment-repositories", type=int, default=69)
    parser.add_argument("--expected-legacy-timing-mismatch-rows", type=int, default=19)
    parser.add_argument("--expected-legacy-timing-mismatch-repositories", type=int, default=5)
    parser.add_argument("--expected-months", type=int, default=20)
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


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def read_csv_stable(path: Path, string_columns: Iterable[str]) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Required input file not found: {path}")
    header = pd.read_csv(path, nrows=0)
    dtype = {column: "string" for column in string_columns if column in header.columns}
    return pd.read_csv(path, dtype=dtype, low_memory=False)


def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    df.to_csv(temporary, index=False)
    temporary.replace(target)


def parse_month_series(values: pd.Series, label: str) -> pd.Series:
    text = values.map(clean_text)
    parsed = pd.to_datetime(text, format="%Y-%m", errors="coerce")
    invalid = text.ne("") & parsed.isna()
    if invalid.any():
        examples = sorted(text.loc[invalid].unique().tolist())[:10]
        raise ValueError(f"{label} contains invalid YYYY-MM values: {examples}")
    result = pd.Series(pd.NaT, index=values.index, dtype="period[M]")
    valid = parsed.notna()
    result.loc[valid] = parsed.loc[valid].dt.to_period("M")
    return result


def normalize_bool(values: pd.Series, label: str) -> pd.Series:
    text = values.map(clean_text).str.casefold()
    true_values = {"1", "true", "t", "yes", "y"}
    false_values = {"0", "false", "f", "no", "n"}
    invalid = ~text.isin(true_values | false_values | {""})
    if invalid.any():
        examples = sorted(text.loc[invalid].unique().tolist())[:10]
        raise ValueError(f"{label} contains invalid Boolean values: {examples}")
    result = pd.Series(pd.NA, index=values.index, dtype="boolean")
    result.loc[text.isin(true_values)] = True
    result.loc[text.isin(false_values)] = False
    return result


def normalize_inputs(
    paper_raw: pd.DataFrame,
    local_raw: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    require_columns(paper_raw, PAPER_PANEL_REQUIRED_COLUMNS, "C03 paper panel")
    require_columns(local_raw, LOCAL_PANEL_REQUIRED_COLUMNS, "C04b local repo-month panel")

    paper = paper_raw.copy()
    local = local_raw.copy()

    for frame in [paper, local]:
        frame["scope_role"] = frame["scope_role"].map(clean_text).str.casefold()
        frame["repo_name"] = frame["repo_name"].map(clean_text)
        frame["repo_name_key"] = frame["repo_name_key"].map(clean_text).str.casefold()
        frame["time"] = frame["time"].map(clean_text)
        frame["repo_snapshot_key"] = frame["repo_snapshot_key"].map(clean_text)

    if not set(paper["scope_role"].unique()).issubset({"treatment", "control"}):
        raise ValueError("C03 paper panel contains unexpected scope_role values")
    if not set(local["scope_role"].unique()).issubset({"treatment", "control"}):
        raise ValueError("C04b local panel contains unexpected scope_role values")

    paper["clone_available"] = normalize_bool(paper["clone_available"], "clone_available").fillna(False)
    paper["snapshot_available"] = normalize_bool(paper["snapshot_available"], "snapshot_available").fillna(False)
    local["cloc_available"] = normalize_bool(local["cloc_available"], "cloc_available").fillna(False)

    numeric_paper = MODEL_RAW_COLUMNS + ["paper_ncloc", "is_treatment", "post_event", "time_to_event"]
    for column in numeric_paper:
        paper[column] = pd.to_numeric(paper[column], errors="coerce")

    numeric_local = [
        "ncloc_local_cloc_all_recognized",
        "ncloc_local_cloc_paper_taxonomy",
        "ncloc_local_cloc_not_in_paper_taxonomy",
        "paper_taxonomy_code_share",
    ]
    for column in numeric_local:
        local[column] = pd.to_numeric(local[column], errors="coerce")

    if paper.duplicated(KEY_COLUMNS).any():
        sample = paper.loc[paper.duplicated(KEY_COLUMNS, keep=False), KEY_COLUMNS].head(20)
        raise ValueError(f"C03 paper panel contains duplicate keys: {sample.to_dict('records')}")
    if local.duplicated(KEY_COLUMNS).any():
        sample = local.loc[local.duplicated(KEY_COLUMNS, keep=False), KEY_COLUMNS].head(20)
        raise ValueError(f"C04b local panel contains duplicate keys: {sample.to_dict('records')}")

    return paper, local


def add_timing_and_transforms(panel: pd.DataFrame, start_month: str, end_month: str) -> pd.DataFrame:
    data = panel.copy()
    data["_time_period"] = parse_month_series(data["time"], "paper panel time")
    data["_event_period"] = parse_month_series(data["event"], "paper panel event")

    start_period = pd.Period(start_month, freq="M")
    end_period = pd.Period(end_month, freq="M")
    expected_periods = list(pd.period_range(start_period, end_period, freq="M"))
    observed_periods = sorted(data["_time_period"].dropna().unique().tolist())
    if observed_periods != expected_periods:
        raise ValueError(
            "Observed calendar months do not match the configured continuous window: "
            f"observed={observed_periods}; expected={expected_periods}"
        )

    time_index_map = {period: index + 1 for index, period in enumerate(expected_periods)}
    data["time_index"] = data["_time_period"].map(time_index_map).astype(int)
    data["time_yyyymm"] = data["_time_period"].map(lambda value: int(value.strftime("%Y%m")))

    data["treatment_group"] = data["scope_role"].eq("treatment").astype(int)
    treatment_missing_event = data["treatment_group"].eq(1) & data["_event_period"].isna()
    control_with_event = data["treatment_group"].eq(0) & data["_event_period"].notna()
    if treatment_missing_event.any() or control_with_event.any():
        raise ValueError(
            "Treatment/control event definitions are inconsistent: "
            f"treatment_missing_event={int(treatment_missing_event.sum())}; "
            f"control_with_event={int(control_with_event.sum())}"
        )

    data["event_index"] = 0
    treatment_mask = data["treatment_group"].eq(1)
    missing_event_window = treatment_mask & ~data["_event_period"].isin(expected_periods)
    if missing_event_window.any():
        examples = data.loc[missing_event_window, ["repo_name", "event"]].drop_duplicates().head(20)
        raise ValueError(f"Treatment events fall outside the analysis window: {examples.to_dict('records')}")
    data.loc[treatment_mask, "event_index"] = (
        data.loc[treatment_mask, "_event_period"].map(time_index_map).astype(int)
    )
    data["event_yyyymm"] = 0
    data.loc[treatment_mask, "event_yyyymm"] = data.loc[treatment_mask, "_event_period"].map(
        lambda value: int(value.strftime("%Y%m"))
    )

    data["event_time_normalized"] = np.nan
    data.loc[treatment_mask, "event_time_normalized"] = (
        data.loc[treatment_mask, "time_index"] - data.loc[treatment_mask, "event_index"]
    )
    data["absorbing_treated"] = (
        treatment_mask & data["time_index"].ge(data["event_index"])
    ).astype(int)

    data["legacy_is_treatment"] = data["is_treatment"].fillna(0).astype(int)
    data["legacy_post_event"] = data["post_event"].fillna(0).astype(int)
    data["legacy_is_treatment_mismatch"] = data["legacy_is_treatment"].ne(data["absorbing_treated"])
    data["legacy_post_event_mismatch"] = data["legacy_post_event"].ne(data["absorbing_treated"])
    data["legacy_timing_mismatch_any"] = (
        data["legacy_is_treatment_mismatch"] | data["legacy_post_event_mismatch"]
    )

    repo_names = (
        data[["repo_name_key", "repo_name"]]
        .drop_duplicates()
        .sort_values(["repo_name_key", "repo_name"], kind="stable")
        .reset_index(drop=True)
    )
    repo_names["repo_id"] = np.arange(1, len(repo_names) + 1, dtype=int)
    data = data.merge(repo_names[["repo_name_key", "repo_id"]], on="repo_name_key", how="left", validate="many_to_one")

    for source, target in LOG1P_COLUMNS.items():
        values = pd.to_numeric(data[source], errors="coerce")
        if (values.dropna() < 0).any():
            raise ValueError(f"{source} contains negative values and cannot be log1p transformed")
        data[target] = np.log1p(values)

    data["_time_period"] = data["_time_period"].astype(str)
    data["_event_period"] = data["_event_period"].astype(str).replace("NaT", "")
    return data


def build_estimability_audit(data: pd.DataFrame) -> pd.DataFrame:
    treatments = (
        data.loc[data["treatment_group"].eq(1), ["repo_id", "repo_name", "repo_name_key", "event", "event_index"]]
        .drop_duplicates()
        .sort_values(["repo_name_key"], kind="stable")
        .reset_index(drop=True)
    )

    rows: list[dict[str, Any]] = []
    for record in treatments.itertuples(index=False):
        repo_rows = data[data["repo_name_key"].eq(record.repo_name_key)]
        output: dict[str, Any] = {
            "repo_id": int(record.repo_id),
            "repo_name": record.repo_name,
            "repo_name_key": record.repo_name_key,
            "event": record.event,
            "event_index": int(record.event_index),
        }
        for prefix, sample_column in [
            ("paper_full", "paper_full_complete_case"),
            ("common", "common_backend_sample"),
        ]:
            sample = repo_rows[repo_rows[sample_column]]
            pre_rows = int((sample["event_time_normalized"] < 0).sum())
            treated_rows = int((sample["event_time_normalized"] >= 0).sum())
            event_zero_rows = int((sample["event_time_normalized"] == 0).sum())
            output[f"{prefix}_rows"] = len(sample)
            output[f"{prefix}_pre_rows"] = pre_rows
            output[f"{prefix}_treated_rows"] = treated_rows
            output[f"{prefix}_event_zero_rows"] = event_zero_rows
            output[f"{prefix}_has_pre"] = pre_rows > 0
            output[f"{prefix}_has_treated"] = treated_rows > 0
            output[f"{prefix}_borusyak_estimable"] = pre_rows > 0 and treated_rows > 0
            reasons: list[str] = []
            if len(sample) == 0:
                reasons.append("no_rows_in_sample")
            if pre_rows == 0:
                reasons.append("no_untreated_pre_observation")
            if treated_rows == 0:
                reasons.append("no_treated_observation")
            output[f"{prefix}_non_estimable_reason"] = ";".join(reasons)
        rows.append(output)

    return pd.DataFrame(rows)


def add_sample_flags(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = data.copy()
    panel["paper_ncloc_available"] = panel["paper_ncloc"].notna()
    panel["local_cloc_available"] = panel["ncloc_local_cloc_paper_taxonomy"].notna()
    panel["non_ncloc_model_complete"] = panel[MODEL_RAW_COLUMNS].notna().all(axis=1)
    panel["paper_full_complete_case"] = (
        panel["non_ncloc_model_complete"] & panel["paper_ncloc_available"]
    )
    panel["common_backend_sample"] = (
        panel["paper_full_complete_case"] & panel["local_cloc_available"]
    )

    audit = build_estimability_audit(panel)
    support = audit[
        [
            "repo_name_key",
            "paper_full_has_pre",
            "paper_full_has_treated",
            "paper_full_borusyak_estimable",
            "common_has_pre",
            "common_has_treated",
            "common_borusyak_estimable",
        ]
    ]
    panel = panel.merge(support, on="repo_name_key", how="left", validate="many_to_one")

    controls = panel["treatment_group"].eq(0)
    for column in [
        "paper_full_has_pre",
        "paper_full_has_treated",
        "paper_full_borusyak_estimable",
        "common_has_pre",
        "common_has_treated",
        "common_borusyak_estimable",
    ]:
        panel.loc[controls, column] = True
        panel[column] = panel[column].astype("boolean").fillna(False).astype(bool)

    panel["paper_full_estimable_sample"] = (
        panel["paper_full_complete_case"] & panel["paper_full_borusyak_estimable"]
    )
    panel["common_estimable_sample"] = (
        panel["common_backend_sample"] & panel["common_borusyak_estimable"]
    )

    paper_reason = pd.Series("", index=panel.index, dtype="string")
    paper_reason.loc[~panel["non_ncloc_model_complete"]] = "missing_non_ncloc_model_field"
    paper_reason.loc[panel["non_ncloc_model_complete"] & ~panel["paper_ncloc_available"]] = "missing_paper_ncloc"
    treatment_no_pre = (
        panel["treatment_group"].eq(1)
        & panel["paper_full_complete_case"]
        & ~panel["paper_full_has_pre"]
    )
    paper_reason.loc[treatment_no_pre] = "treatment_has_no_pre_observation"
    panel["paper_full_estimable_exclusion_reason"] = paper_reason

    common_reason = pd.Series("", index=panel.index, dtype="string")
    common_reason.loc[~panel["non_ncloc_model_complete"]] = "missing_non_ncloc_model_field"
    common_reason.loc[panel["non_ncloc_model_complete"] & ~panel["paper_ncloc_available"]] = "missing_paper_ncloc"
    common_reason.loc[
        panel["paper_full_complete_case"] & ~panel["local_cloc_available"]
    ] = "local_snapshot_unavailable"
    common_no_pre = (
        panel["treatment_group"].eq(1)
        & panel["common_backend_sample"]
        & ~panel["common_has_pre"]
    )
    common_reason.loc[common_no_pre] = "treatment_has_no_pre_observation"
    panel["common_estimable_exclusion_reason"] = common_reason

    return panel, audit


def build_analysis_panel(
    combined: pd.DataFrame,
    mask_column: str,
    metric_column: str,
    specification: str,
    sample_definition: str,
    backend: str,
    backend_label: str,
) -> pd.DataFrame:
    panel = combined.loc[combined[mask_column]].copy()
    panel["analysis_specification"] = specification
    panel["analysis_sample_definition"] = sample_definition
    panel["ncloc_backend"] = backend
    panel["ncloc_backend_label"] = backend_label
    panel["ncloc_backend_metric"] = metric_column
    panel["ncloc"] = pd.to_numeric(panel[metric_column], errors="coerce")
    panel["model_input_complete"] = panel[
        [
            "log_commits",
            "log_lines_added",
            "log_age",
            "ncloc",
            "log_contributors",
            "log_stars",
            "log_issues",
        ]
    ].notna().all(axis=1)
    if not panel["model_input_complete"].all():
        raise ValueError(f"{specification} contains incomplete model input rows")

    priority = [
        "repo_id",
        "repo_name",
        "repo_name_key",
        "dataset_source",
        "scope_role",
        "treatment_group",
        "time",
        "time_index",
        "time_yyyymm",
        "event",
        "event_index",
        "event_yyyymm",
        "event_time_normalized",
        "absorbing_treated",
        "time_to_event",
        "commits",
        "log_commits",
        "lines_added",
        "log_lines_added",
        "age",
        "log_age",
        "contributors",
        "log_contributors",
        "stars",
        "log_stars",
        "issues",
        "log_issues",
        "ncloc",
        "paper_ncloc",
        "ncloc_local_cloc_paper_taxonomy",
        "ncloc_local_cloc_all_recognized",
        "ncloc_local_cloc_not_in_paper_taxonomy",
        "analysis_specification",
        "analysis_sample_definition",
        "ncloc_backend",
        "ncloc_backend_label",
        "ncloc_backend_metric",
        "model_input_complete",
        "paper_full_complete_case",
        "common_backend_sample",
        "paper_full_estimable_sample",
        "common_estimable_sample",
        "legacy_is_treatment",
        "legacy_post_event",
        "legacy_timing_mismatch_any",
        "clone_available",
        "snapshot_available",
        "cloc_available",
        "repo_snapshot_key",
        "resolved_commit",
    ]
    ordered = [column for column in priority if column in panel.columns]
    remaining = [column for column in panel.columns if column not in ordered and not column.startswith("_")]
    panel = panel[ordered + remaining]
    panel = panel.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)
    return panel


def build_backend_comparison(combined: pd.DataFrame) -> pd.DataFrame:
    comparison = combined.loc[combined["common_backend_sample"]].copy()
    comparison["paper_minus_local_taxonomy"] = (
        comparison["paper_ncloc"] - comparison["ncloc_local_cloc_paper_taxonomy"]
    )
    comparison["paper_minus_local_all_recognized"] = (
        comparison["paper_ncloc"] - comparison["ncloc_local_cloc_all_recognized"]
    )
    comparison["local_taxonomy_to_paper_ratio"] = (
        comparison["ncloc_local_cloc_paper_taxonomy"] / comparison["paper_ncloc"]
    )
    comparison["local_all_to_paper_ratio"] = (
        comparison["ncloc_local_cloc_all_recognized"] / comparison["paper_ncloc"]
    )
    comparison["log1p_paper_ncloc"] = np.log1p(comparison["paper_ncloc"])
    comparison["log1p_local_taxonomy_ncloc"] = np.log1p(
        comparison["ncloc_local_cloc_paper_taxonomy"]
    )
    comparison["log1p_local_all_recognized_ncloc"] = np.log1p(
        comparison["ncloc_local_cloc_all_recognized"]
    )
    columns = [
        "repo_id",
        "repo_name",
        "repo_name_key",
        "scope_role",
        "time",
        "time_index",
        "event",
        "event_index",
        "event_time_normalized",
        "paper_ncloc",
        "ncloc_local_cloc_paper_taxonomy",
        "ncloc_local_cloc_all_recognized",
        "ncloc_local_cloc_not_in_paper_taxonomy",
        "paper_minus_local_taxonomy",
        "paper_minus_local_all_recognized",
        "local_taxonomy_to_paper_ratio",
        "local_all_to_paper_ratio",
        "log1p_paper_ncloc",
        "log1p_local_taxonomy_ncloc",
        "log1p_local_all_recognized_ncloc",
        "paper_taxonomy_code_share",
        "repo_snapshot_key",
    ]
    return comparison[columns].sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)


def sample_row(
    name: str,
    panel: pd.DataFrame,
    note: str,
) -> dict[str, Any]:
    treatment = panel[panel["treatment_group"].eq(1)]
    control = panel[panel["treatment_group"].eq(0)]
    return {
        "sample_name": name,
        "rows": len(panel),
        "repositories": panel["repo_id"].nunique(),
        "treatment_rows": len(treatment),
        "control_rows": len(control),
        "treatment_repositories": treatment["repo_id"].nunique(),
        "control_repositories": control["repo_id"].nunique(),
        "untreated_rows": int(panel["absorbing_treated"].eq(0).sum()),
        "treated_rows": int(panel["absorbing_treated"].eq(1).sum()),
        "event_zero_treatment_repositories": treatment.loc[
            treatment["event_time_normalized"].eq(0), "repo_id"
        ].nunique(),
        "note": note,
    }


def build_summary(
    combined: pd.DataFrame,
    comparison: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
    qc: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add(category: str, metric: str, value: Any, note: str = "") -> None:
        rows.append({"category": category, "metric": metric, "value": value, "note": note})

    add("definition", "implementation_version", IMPLEMENTATION_VERSION)
    add("definition", "paper_ncloc_metric", "paper_ncloc")
    add("definition", "local_primary_metric", "ncloc_local_cloc_paper_taxonomy")
    add("definition", "local_robustness_metric", "ncloc_local_cloc_all_recognized")
    add("definition", "treatment_timing", "absorbing_first_adoption")
    add(
        "definition",
        "borusyak_estimability",
        "treated repository has >=1 pre-adoption row and >=1 treated row",
    )

    add("input", "paper_scope_rows", len(combined))
    add("input", "paper_scope_repositories", combined["repo_id"].nunique())
    add("input", "paper_ncloc_missing_rows", int(combined["paper_ncloc"].isna().sum()))
    add("input", "local_ncloc_missing_rows", int(combined["ncloc_local_cloc_paper_taxonomy"].isna().sum()))
    add("sample", "paper_full_complete_rows", len(panels["paper_full_complete"]))
    add("sample", "paper_full_estimable_rows", len(panels["paper_full_estimable"]))
    add("sample", "common_complete_rows", len(panels["paper_common_complete"]))
    add("sample", "common_estimable_rows", len(panels["paper_common_estimable"]))

    if len(comparison) > 1:
        add(
            "comparison",
            "pearson_paper_vs_local_taxonomy",
            comparison["paper_ncloc"].corr(comparison["ncloc_local_cloc_paper_taxonomy"], method="pearson"),
        )
        add(
            "comparison",
            "spearman_paper_vs_local_taxonomy",
            comparison["paper_ncloc"].corr(comparison["ncloc_local_cloc_paper_taxonomy"], method="spearman"),
        )
        add(
            "comparison",
            "pearson_log1p_paper_vs_local_taxonomy",
            comparison["log1p_paper_ncloc"].corr(comparison["log1p_local_taxonomy_ncloc"], method="pearson"),
        )
        add(
            "comparison",
            "median_paper_minus_local_taxonomy",
            comparison["paper_minus_local_taxonomy"].median(),
        )
        add(
            "comparison",
            "median_local_taxonomy_to_paper_ratio",
            comparison["local_taxonomy_to_paper_ratio"].median(),
        )

    add("qc", "hard_qc_failures", int(qc["status"].eq("fail").sum()))
    return pd.DataFrame(rows)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    logging.info("Reading C03 paper panel: %s", args.paper_panel_file)
    paper_raw = read_csv_stable(
        args.paper_panel_file,
        ["scope_role", "repo_name", "repo_name_key", "time", "event", "repo_snapshot_key"],
    )
    logging.info("Reading C04b local repo-month panel: %s", args.local_repo_month_file)
    local_raw = read_csv_stable(
        args.local_repo_month_file,
        ["scope_role", "repo_name", "repo_name_key", "time", "repo_snapshot_key"],
    )

    paper, local = normalize_inputs(paper_raw, local_raw)
    qc = QcCollector()

    local_columns = [
        "scope_role",
        "repo_name_key",
        "time",
        "repo_name",
        "repo_snapshot_key",
        "cloc_available",
        "cloc_snapshot_status",
        "ncloc_local_cloc_all_recognized",
        "ncloc_local_cloc_paper_taxonomy",
        "ncloc_local_cloc_not_in_paper_taxonomy",
        "paper_taxonomy_code_share",
        "paper_taxonomy_version",
        "paper_taxonomy_count_backend",
    ]
    local_join = local[local_columns].rename(
        columns={
            "repo_name": "local_repo_name",
            "repo_snapshot_key": "local_repo_snapshot_key",
        }
    )
    combined = paper.merge(
        local_join,
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
        indicator="local_join_status",
    )

    combined["local_cloc_available"] = combined["local_join_status"].eq("both")
    joined_snapshot_mismatch = (
        combined["local_cloc_available"]
        & combined["repo_snapshot_key"].map(clean_text).ne(
            combined["local_repo_snapshot_key"].map(clean_text)
        )
    )
    local_on_unavailable = combined["local_cloc_available"] & ~combined["clone_available"]
    clone_available_without_local = combined["clone_available"] & ~combined["local_cloc_available"]

    combined = add_timing_and_transforms(combined, args.start_month, args.end_month)
    combined, estimability_audit = add_sample_flags(combined)

    legacy_timing_audit = combined.loc[
        combined["legacy_timing_mismatch_any"],
        [
            "repo_id",
            "repo_name",
            "repo_name_key",
            "scope_role",
            "time",
            "time_index",
            "event",
            "event_index",
            "event_time_normalized",
            "absorbing_treated",
            "legacy_is_treatment",
            "legacy_post_event",
            "legacy_is_treatment_mismatch",
            "legacy_post_event_mismatch",
        ],
    ].sort_values(["repo_id", "time_index"], kind="stable")

    panels: dict[str, pd.DataFrame] = {}
    panels["paper_full_complete"] = build_analysis_panel(
        combined,
        "paper_full_complete_case",
        "paper_ncloc",
        "paper_full_complete_case",
        "All paper-scope rows with complete outcomes, covariates, and paper NCLOC.",
        "paper_sonarqube",
        "Paper SonarQube NCLOC",
    )
    panels["paper_full_estimable"] = build_analysis_panel(
        combined,
        "paper_full_estimable_sample",
        "paper_ncloc",
        "paper_full_borusyak_estimable",
        "Paper complete cases after removing treated repositories without both pre-adoption and treated observations; the original complete-case control pool is retained.",
        "paper_sonarqube",
        "Paper SonarQube NCLOC",
    )
    panels["paper_common_complete"] = build_analysis_panel(
        combined,
        "common_backend_sample",
        "paper_ncloc",
        "paper_common_complete_case",
        "Exact paper/local common rows using paper NCLOC.",
        "paper_sonarqube_common",
        "Paper SonarQube NCLOC, common sample",
    )
    panels["paper_common_estimable"] = build_analysis_panel(
        combined,
        "common_estimable_sample",
        "paper_ncloc",
        "paper_common_borusyak_estimable",
        "Exact common rows after removing treated repositories without both pre-adoption and treated observations; the common-sample control pool is retained.",
        "paper_sonarqube_common",
        "Paper SonarQube NCLOC, common sample",
    )
    panels["local_taxonomy_common_complete"] = build_analysis_panel(
        combined,
        "common_backend_sample",
        "ncloc_local_cloc_paper_taxonomy",
        "local_cloc_paper_taxonomy_common_complete_case",
        "Exact paper/local common rows using local cloc paper-taxonomy NCLOC.",
        "local_cloc_paper_taxonomy_common",
        "Local cloc paper-taxonomy NCLOC, common sample",
    )
    panels["local_taxonomy_common_estimable"] = build_analysis_panel(
        combined,
        "common_estimable_sample",
        "ncloc_local_cloc_paper_taxonomy",
        "local_cloc_paper_taxonomy_common_borusyak_estimable",
        "Exact common rows after removing treated repositories without both pre-adoption and treated observations; local cloc paper-taxonomy NCLOC is used.",
        "local_cloc_paper_taxonomy_common",
        "Local cloc paper-taxonomy NCLOC, common sample",
    )
    panels["local_all_common_complete"] = build_analysis_panel(
        combined,
        "common_backend_sample",
        "ncloc_local_cloc_all_recognized",
        "local_cloc_all_recognized_common_complete_case",
        "Robustness panel on exact common rows using all cloc-recognized NCLOC.",
        "local_cloc_all_recognized_common",
        "Local cloc all-recognized NCLOC, common sample",
    )
    panels["local_all_common_estimable"] = build_analysis_panel(
        combined,
        "common_estimable_sample",
        "ncloc_local_cloc_all_recognized",
        "local_cloc_all_recognized_common_borusyak_estimable",
        "Robustness panel on exact common rows after the Borusyak treatment-support restriction.",
        "local_cloc_all_recognized_common",
        "Local cloc all-recognized NCLOC, common sample",
    )

    comparison = build_backend_comparison(combined)

    sample_summary = pd.DataFrame(
        [
            sample_row("paper_scope_candidate", combined, "All C03 paper-scope rows before NCLOC complete-case filtering."),
            sample_row("paper_full_complete_case", panels["paper_full_complete"], "Paper NCLOC complete cases."),
            sample_row("paper_full_borusyak_estimable", panels["paper_full_estimable"], "Paper complete cases with treatment-side pre/post support."),
            sample_row("paper_local_common_complete_case", panels["paper_common_complete"], "Exact common rows; paper and local panels have identical keys."),
            sample_row("paper_local_common_borusyak_estimable", panels["paper_common_estimable"], "Exact common rows with treatment-side pre/post support."),
        ]
    )

    # Core structural QC.
    qc.exact("input", "paper_panel_rows", len(paper), args.expected_paper_panel_rows)
    qc.exact("input", "paper_treatment_rows", int(paper["scope_role"].eq("treatment").sum()), args.expected_treatment_paper_rows)
    qc.exact("input", "paper_control_rows", int(paper["scope_role"].eq("control").sum()), args.expected_control_paper_rows)
    qc.exact("input", "paper_repositories", paper["repo_name_key"].nunique(), args.expected_paper_repositories)
    qc.exact("input", "paper_treatment_repositories", paper.loc[paper["scope_role"].eq("treatment"), "repo_name_key"].nunique(), args.expected_treatment_repositories)
    qc.exact("input", "paper_control_repositories", paper.loc[paper["scope_role"].eq("control"), "repo_name_key"].nunique(), args.expected_control_repositories)
    qc.exact("input", "local_repo_month_rows", len(local), args.expected_local_rows)
    qc.exact("input", "local_repositories", local["repo_name_key"].nunique(), args.expected_local_repositories)
    qc.zero("join", "joined_snapshot_key_mismatches", int(joined_snapshot_mismatch.sum()))
    qc.zero("join", "local_rows_on_clone_unavailable_scope", int(local_on_unavailable.sum()))
    qc.zero("join", "clone_available_rows_without_local_result", int(clone_available_without_local.sum()))
    qc.exact("join", "paper_ncloc_missing_rows", int(combined["paper_ncloc"].isna().sum()), args.expected_paper_ncloc_missing)
    qc.exact("calendar", "calendar_months", combined["time_index"].nunique(), args.expected_months)
    qc.zero("calendar", "duplicate_repo_month_rows", int(combined.duplicated(["repo_id", "time_index"]).sum()))
    treatment_timing_rows = combined["treatment_group"].eq(1) & combined["time_to_event"].notna()
    qc.zero(
        "calendar",
        "normalized_event_time_mismatches_source_time_to_event",
        int(
            combined.loc[treatment_timing_rows, "event_time_normalized"].ne(
                combined.loc[treatment_timing_rows, "time_to_event"]
            ).sum()
        ),
        "Sequential month-index event time must match the C03 source field for treatment rows.",
    )
    qc.zero("metric", "negative_paper_ncloc_rows", int((combined["paper_ncloc"].dropna() < 0).sum()))
    qc.zero("metric", "negative_local_taxonomy_ncloc_rows", int((combined["ncloc_local_cloc_paper_taxonomy"].dropna() < 0).sum()))
    qc.zero("metric", "negative_local_all_ncloc_rows", int((combined["ncloc_local_cloc_all_recognized"].dropna() < 0).sum()))
    qc.exact("sample", "paper_full_complete_rows", len(panels["paper_full_complete"]), args.expected_paper_full_complete_rows)
    qc.exact("sample", "common_complete_rows", len(panels["paper_common_complete"]), args.expected_common_rows)
    qc.exact("sample", "paper_full_estimable_rows", len(panels["paper_full_estimable"]), args.expected_paper_full_estimable_rows)
    qc.exact("sample", "common_estimable_rows", len(panels["paper_common_estimable"]), args.expected_common_estimable_rows)
    qc.exact(
        "sample",
        "paper_full_estimable_treatment_repositories",
        panels["paper_full_estimable"].loc[
            panels["paper_full_estimable"]["treatment_group"].eq(1), "repo_id"
        ].nunique(),
        args.expected_paper_full_estimable_treatment_repositories,
    )
    qc.exact(
        "sample",
        "common_estimable_treatment_repositories",
        panels["paper_common_estimable"].loc[
            panels["paper_common_estimable"]["treatment_group"].eq(1), "repo_id"
        ].nunique(),
        args.expected_common_estimable_treatment_repositories,
    )
    qc.true(
        "sample",
        "common_complete_paper_local_keys_identical",
        panels["paper_common_complete"][["repo_id", "time_index"]].equals(
            panels["local_taxonomy_common_complete"][["repo_id", "time_index"]]
        ),
    )
    qc.true(
        "sample",
        "common_estimable_paper_local_keys_identical",
        panels["paper_common_estimable"][["repo_id", "time_index"]].equals(
            panels["local_taxonomy_common_estimable"][["repo_id", "time_index"]]
        ),
    )
    qc.zero(
        "sample",
        "paper_common_generic_ncloc_alias_mismatches",
        int(
            panels["paper_common_estimable"]["ncloc"].ne(
                panels["paper_common_estimable"]["paper_ncloc"]
            ).sum()
        ),
    )
    qc.zero(
        "sample",
        "local_taxonomy_generic_ncloc_alias_mismatches",
        int(
            panels["local_taxonomy_common_estimable"]["ncloc"].ne(
                panels["local_taxonomy_common_estimable"]["ncloc_local_cloc_paper_taxonomy"]
            ).sum()
        ),
    )
    qc.zero(
        "sample",
        "local_all_generic_ncloc_alias_mismatches",
        int(
            panels["local_all_common_estimable"]["ncloc"].ne(
                panels["local_all_common_estimable"]["ncloc_local_cloc_all_recognized"]
            ).sum()
        ),
    )
    qc.exact(
        "timing",
        "legacy_timing_mismatch_rows",
        len(legacy_timing_audit),
        args.expected_legacy_timing_mismatch_rows,
    )
    qc.exact(
        "timing",
        "legacy_timing_mismatch_repositories",
        legacy_timing_audit["repo_id"].nunique(),
        args.expected_legacy_timing_mismatch_repositories,
    )
    qc.zero(
        "estimability",
        "paper_full_estimable_treatment_repositories_without_pre",
        int(
            (
                estimability_audit["paper_full_borusyak_estimable"]
                & ~estimability_audit["paper_full_has_pre"]
            ).sum()
        ),
    )
    qc.zero(
        "estimability",
        "common_estimable_treatment_repositories_without_pre",
        int(
            (
                estimability_audit["common_borusyak_estimable"]
                & ~estimability_audit["common_has_pre"]
            ).sum()
        ),
    )

    qc_df = qc.dataframe()
    summary = build_summary(combined, comparison, panels, qc_df)

    combined = combined.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)
    combined = combined[[column for column in combined.columns if not column.startswith("_")]]

    save_dataframe(combined, args.combined_panel_output)
    save_dataframe(panels["paper_full_complete"], args.paper_full_complete_output)
    save_dataframe(panels["paper_full_estimable"], args.paper_full_estimable_output)
    save_dataframe(panels["paper_common_complete"], args.paper_common_complete_output)
    save_dataframe(panels["paper_common_estimable"], args.paper_common_estimable_output)
    save_dataframe(panels["local_taxonomy_common_complete"], args.local_taxonomy_common_complete_output)
    save_dataframe(panels["local_taxonomy_common_estimable"], args.local_taxonomy_common_estimable_output)
    save_dataframe(panels["local_all_common_complete"], args.local_all_common_complete_output)
    save_dataframe(panels["local_all_common_estimable"], args.local_all_common_estimable_output)
    save_dataframe(comparison, args.backend_comparison_output)
    save_dataframe(estimability_audit, args.treatment_estimability_output)
    save_dataframe(legacy_timing_audit, args.legacy_timing_audit_output)
    save_dataframe(sample_summary, args.sample_summary_output)
    save_dataframe(qc_df, args.qc_output)
    save_dataframe(summary, args.summary_output)

    logging.info(
        "Completed run-x-c05-%s: paper_scope=%d; paper_complete=%d; "
        "paper_estimable=%d; common_complete=%d; common_estimable=%d; "
        "paper_estimable_treatments=%d; common_estimable_treatments=%d; "
        "legacy_timing_mismatches=%d; hard_qc_failures=%d",
        IMPLEMENTATION_VERSION,
        len(combined),
        len(panels["paper_full_complete"]),
        len(panels["paper_full_estimable"]),
        len(panels["paper_common_complete"]),
        len(panels["paper_common_estimable"]),
        panels["paper_full_estimable"].loc[
            panels["paper_full_estimable"]["treatment_group"].eq(1), "repo_id"
        ].nunique(),
        panels["paper_common_estimable"].loc[
            panels["paper_common_estimable"]["treatment_group"].eq(1), "repo_id"
        ].nunique(),
        len(legacy_timing_audit),
        qc.failure_count(),
    )

    if args.strict_expected_counts and qc.failure_count() > 0:
        logging.error("C05 produced %d hard QC failure(s)", qc.failure_count())
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
