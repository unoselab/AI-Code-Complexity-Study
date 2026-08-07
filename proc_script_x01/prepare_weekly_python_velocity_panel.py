#!/usr/bin/env python3
"""Prepare weekly Python added-lines panels from the validated run-x-b02-v4 commit output.

This experiment is a timing-resolution robustness analysis. It does not rescan Git
history for Python line changes. Instead, it re-aggregates the already validated
commit-level run-x-b02-v4 outcomes to Monday-start calendar weeks using exact Git
committer epochs. Treatment timing comes from the run-x-b03-c frozen-history audit,
which independently recovered the first observable Cursor-related commit for all
63 treated repositories.

Inputs
------
1. Final run-x-b02-v4 common monthly panel. It supplies the fixed 167-repository
   Python-primary roster, repository IDs, treatment/control roles, and each
   repository's observed monthly support range.
2. Final run-x-b02-v4 commit-level Python added-lines file. It supplies exact
   commit epochs and four validated Python added-lines outcome definitions.
3. Final run-x-b03-c repository treatment-history summary. It supplies the exact
   first observable Cursor-related commit timestamp for each treated repository.

Outputs
-------
- One weekly DiD panel under America/New_York calendar time.
- One weekly DiD panel under America/Chicago calendar time.
- A treatment-week timezone audit.
- A monthly-support-gap audit.
- Cross-calendar outcome/timing comparisons, QC, and a compact long-form summary.

The weekly panels deliberately use no weekly NCLOC or other contemporaneous
covariates. The downstream DiD is therefore a FE-only timing diagnostic, not a
replacement for the monthly primary adjusted model.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd

IMPLEMENTATION_VERSION = "v1"
SOURCE_METRIC_VERSION = "run-x-b02-v4"
WEEK_DEFINITION = "monday_start"
SUPPORT_POLICY = "continuous_min_to_max_months_from_b02_common_sample"
PRIMARY_OUTCOME = "log_lines_added_py_source"
RAW_OUTCOMES = [
    "lines_added_py_all",
    "lines_added_py_no_merge",
    "lines_added_py_source",
    "lines_added_py_source_no_tests",
]
LOG_OUTCOMES = [f"log_{name}" for name in RAW_OUTCOMES]
CALENDARS = {
    "new_york": "America/New_York",
    "chicago": "America/Chicago",
}

MONTHLY_REQUIRED = {
    "repo_id",
    "repo_name",
    "dataset_source",
    "treatment_group",
    "time",
    *RAW_OUTCOMES,
}
COMMIT_REQUIRED = {
    "repo_name",
    "dataset_source",
    "commit_sha",
    "commit_time_epoch",
    "python_metric_complete",
    *RAW_OUTCOMES,
}
TREATMENT_REQUIRED = {
    "repo_name",
    "recorded_event_month",
    "current_first_cursor_datetime",
    "current_first_cursor_month",
    "current_first_month_matches_recorded",
    "recommended_action",
}

PANEL_COLUMNS = [
    "repo_id",
    "repo_name",
    "dataset_source",
    "scope_role",
    "treatment_group",
    "calendar_key",
    "analysis_timezone",
    "week_start",
    "week_key",
    "time_index",
    "event_week_start",
    "event_week_key",
    "event_index",
    "time_to_event",
    "post_event",
    "absorbing_treated",
    "support_start_month",
    "support_end_month",
    "support_days",
    "partial_support_week",
    "commits_recomputed",
    "python_metric_complete_commits",
    *RAW_OUTCOMES,
    *LOG_OUTCOMES,
    "primary_outcome",
    "python_velocity_metric_version",
    "source_metric_version",
    "week_definition",
    "support_policy",
]


class StageError(RuntimeError):
    """Raise a user-facing experiment validation error."""


def require_columns(frame: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise StageError(f"{label} is missing required columns: {', '.join(missing)}")


def clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def parse_bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    text = clean_text(value).casefold()
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "no", "n", ""}:
        return False
    try:
        return float(text) != 0.0
    except ValueError as exc:
        raise StageError(f"Cannot parse boolean value: {value!r}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def month_period(value: str) -> pd.Period:
    text = clean_text(value)
    try:
        period = pd.Period(text, freq="M")
    except Exception as exc:
        raise StageError(f"Invalid YYYY-MM month value: {value!r}") from exc
    if str(period) != text:
        raise StageError(f"Month value is not canonical YYYY-MM: {value!r}")
    return period


def week_start_for_date(day: date) -> date:
    return day - timedelta(days=day.weekday())


def time_index_for_week(week_start: date, origin: date) -> int:
    delta = (week_start - origin).days
    if delta % 7 != 0:
        raise StageError(f"Week start {week_start} is not aligned to origin {origin}")
    return 1 + delta // 7


def week_key(week_start: date) -> str:
    return week_start.strftime("%Y-W%W")


def normalize_monthly_panel(frame: pd.DataFrame) -> pd.DataFrame:
    require_columns(frame, MONTHLY_REQUIRED, "Monthly common panel")
    panel = frame.copy()
    panel["repo_name"] = panel["repo_name"].map(clean_text)
    panel["dataset_source"] = panel["dataset_source"].map(clean_text).str.casefold()
    panel["time"] = panel["time"].map(clean_text)
    panel["repo_id"] = pd.to_numeric(panel["repo_id"], errors="raise").astype(int)
    panel["treatment_group"] = pd.to_numeric(panel["treatment_group"], errors="raise").astype(int)
    for outcome in RAW_OUTCOMES:
        panel[outcome] = pd.to_numeric(panel[outcome], errors="raise").fillna(0.0)
    if not panel["time"].str.fullmatch(r"\d{4}-\d{2}").all():
        raise StageError("Monthly panel contains non-YYYY-MM time values")
    if set(panel["dataset_source"].unique()) - {"treatment", "control"}:
        raise StageError("Monthly panel contains unexpected dataset_source values")
    role_check = (
        ((panel["dataset_source"] == "treatment") & (panel["treatment_group"] != 1))
        | ((panel["dataset_source"] == "control") & (panel["treatment_group"] != 0))
    )
    if role_check.any():
        raise StageError(f"Monthly panel has {int(role_check.sum())} role/treatment_group mismatches")
    if panel.duplicated(["repo_id", "time"]).any():
        raise StageError("Monthly panel contains duplicate repo_id-month rows")
    repo_meta_counts = panel.groupby("repo_name").agg(
        repo_ids=("repo_id", "nunique"),
        sources=("dataset_source", "nunique"),
        treatment_groups=("treatment_group", "nunique"),
    )
    if (repo_meta_counts != 1).any(axis=None):
        raise StageError("At least one repository has inconsistent metadata across months")
    return panel.sort_values(["repo_id", "time"], kind="stable").reset_index(drop=True)


def normalize_commit_file(frame: pd.DataFrame) -> pd.DataFrame:
    require_columns(frame, COMMIT_REQUIRED, "run-x-b02-v4 commit file")
    commits = frame.copy()
    commits["repo_name"] = commits["repo_name"].map(clean_text)
    commits["dataset_source"] = commits["dataset_source"].map(clean_text).str.casefold()
    commits["commit_time_epoch"] = pd.to_numeric(commits["commit_time_epoch"], errors="raise").astype("int64")
    commits["python_metric_complete"] = commits["python_metric_complete"].map(parse_bool)
    for outcome in RAW_OUTCOMES:
        commits[outcome] = pd.to_numeric(commits[outcome], errors="raise").fillna(0.0)
        if (commits[outcome] < 0).any():
            raise StageError(f"Commit file contains negative {outcome}")
    if commits.duplicated(["repo_name", "commit_sha"]).any():
        raise StageError("Commit file contains duplicate repository/commit rows")
    return commits


def normalize_treatment_history(frame: pd.DataFrame) -> pd.DataFrame:
    require_columns(frame, TREATMENT_REQUIRED, "run-x-b03-c treatment-history summary")
    history = frame.copy()
    history["repo_name"] = history["repo_name"].map(clean_text)
    history["recorded_event_month"] = history["recorded_event_month"].map(clean_text)
    history["current_first_cursor_month"] = history["current_first_cursor_month"].map(clean_text)
    history["current_first_cursor_datetime"] = history["current_first_cursor_datetime"].map(clean_text)
    history["current_first_month_matches_recorded"] = history["current_first_month_matches_recorded"].map(parse_bool)
    history["recommended_action"] = history["recommended_action"].map(clean_text)
    if history["repo_name"].duplicated().any():
        raise StageError("Treatment-history summary contains duplicate repositories")
    if (~history["current_first_month_matches_recorded"]).any():
        bad = history.loc[~history["current_first_month_matches_recorded"], "repo_name"].tolist()
        raise StageError("Treatment-history summary contains month mismatches: " + ", ".join(bad))
    if (history["current_first_cursor_datetime"] == "").any():
        bad = history.loc[history["current_first_cursor_datetime"] == "", "repo_name"].tolist()
        raise StageError("Treatment-history summary lacks exact first Cursor timestamps: " + ", ".join(bad))
    parsed = pd.to_datetime(history["current_first_cursor_datetime"], errors="coerce", utc=True)
    if parsed.isna().any():
        bad = history.loc[parsed.isna(), "repo_name"].tolist()
        raise StageError("Cannot parse exact first Cursor timestamps: " + ", ".join(bad))
    history["current_first_cursor_instant_utc"] = parsed
    return history


@dataclass(frozen=True)
class RepoSupport:
    repo_id: int
    repo_name: str
    dataset_source: str
    treatment_group: int
    start_month: pd.Period
    end_month: pd.Period


def build_repo_support(panel: pd.DataFrame) -> tuple[list[RepoSupport], pd.DataFrame]:
    supports: list[RepoSupport] = []
    gap_rows: list[dict[str, Any]] = []
    for repo_name, group in panel.groupby("repo_name", sort=True):
        periods = pd.PeriodIndex(group["time"], freq="M").sort_values().unique()
        start_month = periods.min()
        end_month = periods.max()
        full = pd.period_range(start_month, end_month, freq="M")
        missing = sorted(set(full) - set(periods))
        for period in missing:
            gap_rows.append(
                {
                    "repo_name": repo_name,
                    "missing_month": str(period),
                    "support_start_month": str(start_month),
                    "support_end_month": str(end_month),
                    "weekly_policy": "filled_internal_month_gap_for_fe_only_timing_analysis",
                }
            )
        first = group.iloc[0]
        supports.append(
            RepoSupport(
                repo_id=int(first["repo_id"]),
                repo_name=repo_name,
                dataset_source=str(first["dataset_source"]),
                treatment_group=int(first["treatment_group"]),
                start_month=start_month,
                end_month=end_month,
            )
        )
    return supports, pd.DataFrame(gap_rows)


def build_week_grid(supports: list[RepoSupport], origin: date) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for support in supports:
        support_start = support.start_month.start_time.date()
        support_end = support.end_month.end_time.date()
        days = pd.date_range(support_start, support_end, freq="D")
        by_week: dict[date, int] = {}
        for ts in days:
            start = week_start_for_date(ts.date())
            by_week[start] = by_week.get(start, 0) + 1
        for start in sorted(by_week):
            rows.append(
                {
                    "repo_id": support.repo_id,
                    "repo_name": support.repo_name,
                    "dataset_source": support.dataset_source,
                    "scope_role": support.dataset_source,
                    "treatment_group": support.treatment_group,
                    "week_start": start,
                    "week_key": week_key(start),
                    "time_index": time_index_for_week(start, origin),
                    "support_start_month": str(support.start_month),
                    "support_end_month": str(support.end_month),
                    "support_days": by_week[start],
                    "partial_support_week": int(by_week[start] < 7),
                }
            )
    grid = pd.DataFrame(rows)
    if grid.duplicated(["repo_id", "time_index"]).any():
        raise StageError("Generated weekly grid contains duplicate repo_id/time_index rows")
    return grid.sort_values(["repo_id", "time_index"], kind="stable").reset_index(drop=True)


def localize_commits(commits: pd.DataFrame, timezone_name: str) -> pd.DataFrame:
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise StageError(f"Unknown timezone: {timezone_name}") from exc
    localized = commits.copy()
    instants = pd.to_datetime(localized["commit_time_epoch"], unit="s", utc=True)
    local = instants.dt.tz_convert(timezone)
    localized["local_date"] = local.dt.date
    localized["local_month"] = local.dt.strftime("%Y-%m")
    localized["week_start"] = localized["local_date"].map(week_start_for_date)
    localized["week_key"] = localized["week_start"].map(week_key)
    return localized


def aggregate_calendar(
    grid: pd.DataFrame,
    commits: pd.DataFrame,
    treatment_history: pd.DataFrame,
    calendar_key: str,
    timezone_name: str,
    origin: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    localized = localize_commits(commits, timezone_name)
    support_bounds = grid.groupby("repo_name", as_index=False).agg(
        support_start_month=("support_start_month", "first"),
        support_end_month=("support_end_month", "first"),
    )
    localized = localized.merge(support_bounds, on="repo_name", how="left", validate="many_to_one")
    if localized["support_start_month"].isna().any():
        unknown = sorted(localized.loc[localized["support_start_month"].isna(), "repo_name"].unique())
        raise StageError("Commit file contains repositories outside weekly roster: " + ", ".join(unknown))
    localized["inside_support"] = (
        (localized["local_month"] >= localized["support_start_month"])
        & (localized["local_month"] <= localized["support_end_month"])
    )
    included = localized.loc[localized["inside_support"]].copy()

    agg_map: dict[str, tuple[str, str]] = {
        "commits_recomputed": ("commit_sha", "size"),
        "python_metric_complete_commits": ("python_metric_complete", "sum"),
    }
    for outcome in RAW_OUTCOMES:
        agg_map[outcome] = (outcome, "sum")
    weekly = (
        included.groupby(["repo_name", "week_start"], as_index=False)
        .agg(**agg_map)
    )
    panel = grid.merge(weekly, on=["repo_name", "week_start"], how="left", validate="one_to_one")
    fill_zero = ["commits_recomputed", "python_metric_complete_commits", *RAW_OUTCOMES]
    panel[fill_zero] = panel[fill_zero].fillna(0)
    panel["commits_recomputed"] = panel["commits_recomputed"].astype(int)
    panel["python_metric_complete_commits"] = panel["python_metric_complete_commits"].astype(int)
    for outcome in RAW_OUTCOMES:
        panel[outcome] = pd.to_numeric(panel[outcome], errors="raise")
        panel[f"log_{outcome}"] = np.log1p(panel[outcome].astype(float))

    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise StageError(f"Unknown timezone: {timezone_name}") from exc
    treatment = treatment_history.copy()
    local_event = treatment["current_first_cursor_instant_utc"].dt.tz_convert(timezone)
    treatment["event_local_datetime"] = local_event.map(lambda x: x.isoformat())
    treatment["event_local_date"] = local_event.dt.date
    treatment["event_week_start"] = treatment["event_local_date"].map(week_start_for_date)
    treatment["event_week_key"] = treatment["event_week_start"].map(week_key)
    treatment["event_index"] = treatment["event_week_start"].map(lambda x: time_index_for_week(x, origin))
    event_lookup = treatment.set_index("repo_name")[[
        "event_local_datetime",
        "event_week_start",
        "event_week_key",
        "event_index",
    ]]

    panel = panel.merge(event_lookup, left_on="repo_name", right_index=True, how="left", validate="many_to_one")
    control_mask = panel["treatment_group"].eq(0)
    panel.loc[control_mask, "event_week_start"] = pd.NaT
    panel.loc[control_mask, "event_week_key"] = ""
    panel.loc[control_mask, "event_index"] = 0
    panel.loc[control_mask, "event_local_datetime"] = ""
    panel["event_index"] = pd.to_numeric(panel["event_index"], errors="raise").astype(int)
    treatment_mask = panel["treatment_group"].eq(1)
    if (panel.loc[treatment_mask, "event_index"] <= 0).any():
        raise StageError(f"{calendar_key}: at least one treatment repository has nonpositive event_index")
    panel["time_to_event"] = np.where(
        treatment_mask,
        panel["time_index"] - panel["event_index"],
        np.nan,
    )
    panel["post_event"] = np.where(
        treatment_mask & (panel["time_index"] >= panel["event_index"]), 1, 0
    ).astype(int)
    panel["absorbing_treated"] = panel["post_event"]
    panel["calendar_key"] = calendar_key
    panel["analysis_timezone"] = timezone_name
    panel["primary_outcome"] = PRIMARY_OUTCOME
    panel["python_velocity_metric_version"] = "weekly-v1-from-b02-v4-commit-metrics"
    panel["source_metric_version"] = SOURCE_METRIC_VERSION
    panel["week_definition"] = WEEK_DEFINITION
    panel["support_policy"] = SUPPORT_POLICY
    panel["week_start"] = panel["week_start"].map(str)
    panel["event_week_start"] = panel["event_week_start"].map(
        lambda x: "" if pd.isna(x) else str(x)
    )

    event_audit = treatment[[
        "repo_name",
        "recorded_event_month",
        "current_first_cursor_month",
        "current_first_cursor_datetime",
        "event_local_datetime",
        "event_week_start",
        "event_week_key",
        "event_index",
        "recommended_action",
    ]].copy()
    event_audit.insert(1, "calendar_key", calendar_key)
    event_audit.insert(2, "analysis_timezone", timezone_name)
    event_audit["event_week_start"] = event_audit["event_week_start"].map(str)

    return panel[PANEL_COLUMNS], event_audit


def build_qc(
    args: argparse.Namespace,
    monthly: pd.DataFrame,
    commits: pd.DataFrame,
    treatment: pd.DataFrame,
    gaps: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
    event_audits: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    records: list[dict[str, Any]] = []

    def add_check(name: str, observed: Any, expected: Any, *, policy: str = "strict", note: str = "") -> None:
        passed = observed == expected
        status = "pass" if passed else ("warn" if policy == "warn" else "fail")
        records.append(
            {
                "check_name": name,
                "status": status,
                "observed": observed,
                "expected": expected,
                "note": note,
            }
        )

    repo_meta = monthly.groupby("repo_name", as_index=False).first()
    add_check("monthly_input_rows", len(monthly), args.expected_monthly_rows)
    add_check("repository_count", repo_meta["repo_name"].nunique(), args.expected_repositories)
    add_check(
        "treatment_repository_count",
        int(repo_meta.loc[repo_meta["treatment_group"].eq(1), "repo_name"].nunique()),
        args.expected_treatment_repositories,
    )
    add_check(
        "control_repository_count",
        int(repo_meta.loc[repo_meta["treatment_group"].eq(0), "repo_name"].nunique()),
        args.expected_control_repositories,
    )
    add_check("treatment_history_rows", len(treatment), args.expected_treatment_repositories)
    add_check("internal_month_gap_rows", len(gaps), args.expected_internal_gap_months)
    add_check("incomplete_commit_metric_rows", int((~commits["python_metric_complete"]).sum()), 0)

    monthly_repos = set(repo_meta["repo_name"])
    commit_repos = set(commits["repo_name"])
    history_repos = set(treatment["repo_name"])
    treatment_repos = set(repo_meta.loc[repo_meta["treatment_group"].eq(1), "repo_name"])
    add_check("commit_roster_missing_repositories", len(monthly_repos - commit_repos), args.expected_repositories_without_commit_rows, note="Repositories with no commit-level rows in the retained support range are represented as zero-activity weekly panels.")
    add_check("treatment_history_roster_mismatch", len(history_repos ^ treatment_repos), 0)

    monthly_totals = {outcome: float(monthly[outcome].sum()) for outcome in RAW_OUTCOMES}
    chicago_panel = panels["chicago"]
    new_york_panel = panels["new_york"]
    for outcome in RAW_OUTCOMES:
        chicago_total = float(chicago_panel[outcome].sum())
        add_check(
            f"chicago_weekly_vs_b02_monthly_total_{outcome}",
            chicago_total,
            monthly_totals[outcome],
            note="Chicago is the run-x-b02-v4 outcome timezone, so weekly reaggregation should conserve the monthly total."
        )
        new_york_delta = float(new_york_panel[outcome].sum()) - monthly_totals[outcome]
        add_check(
            f"new_york_total_delta_vs_b02_monthly_{outcome}",
            new_york_delta,
            new_york_delta,
            policy="warn",
            note="Informational: timezone conversion can move commits across the outer support-month boundaries."
        )

    for key, panel in panels.items():
        add_check(f"{key}_weekly_rows", len(panel), args.expected_weekly_rows)
        add_check(f"{key}_duplicate_repo_week_rows", int(panel.duplicated(["repo_id", "time_index"]).sum()), 0)
        add_check(f"{key}_treatment_repositories", int(panel.loc[panel["treatment_group"].eq(1), "repo_name"].nunique()), args.expected_treatment_repositories)
        add_check(f"{key}_control_repositories", int(panel.loc[panel["treatment_group"].eq(0), "repo_name"].nunique()), args.expected_control_repositories)
        add_check(f"{key}_treatment_repos_without_event_week", int(panel.loc[panel["treatment_group"].eq(1)].groupby("repo_name")["time_to_event"].apply(lambda s: not (s == 0).any()).sum()), 0)
        pre_counts = panel.loc[panel["treatment_group"].eq(1)].groupby("repo_name")["time_to_event"].apply(lambda s: int((s < 0).sum()))
        add_check(f"{key}_treatment_repos_with_fewer_than_4_pre_weeks", int((pre_counts < 4).sum()), 0)
        for outcome in RAW_OUTCOMES:
            values = pd.to_numeric(panel[outcome], errors="coerce")
            add_check(f"{key}_{outcome}_missing_values", int(values.isna().sum()), 0)
            nested_log = np.log1p(values.astype(float))
            mismatch = ~np.isclose(nested_log, panel[f"log_{outcome}"], rtol=0, atol=1e-12)
            add_check(f"{key}_{outcome}_log_transform_mismatches", int(mismatch.sum()), 0)
        nesting = (
            (panel["lines_added_py_source_no_tests"] <= panel["lines_added_py_source"])
            & (panel["lines_added_py_source"] <= panel["lines_added_py_no_merge"])
            & (panel["lines_added_py_no_merge"] <= panel["lines_added_py_all"])
        )
        add_check(f"{key}_outcome_nesting_violations", int((~nesting).sum()), 0)

    ny = panels["new_york"]
    chi = panels["chicago"]
    key_cols = ["repo_id", "time_index"]
    add_check("calendar_panel_key_mismatch_rows", len(set(map(tuple, ny[key_cols].to_numpy())) ^ set(map(tuple, chi[key_cols].to_numpy()))), 0)
    ny_events = event_audits["new_york"].set_index("repo_name")
    chi_events = event_audits["chicago"].set_index("repo_name")
    event_diff = ny_events[["event_week_start", "event_week_key", "event_index"]].join(
        chi_events[["event_week_start", "event_week_key", "event_index"]],
        lsuffix="_new_york",
        rsuffix="_chicago",
    ).reset_index()
    event_diff["event_week_differs"] = event_diff["event_index_new_york"] != event_diff["event_index_chicago"]
    add_check("treatment_event_week_timezone_mismatch_repositories", int(event_diff["event_week_differs"].sum()), args.expected_event_week_timezone_mismatches)

    comparison = ny[["repo_id", "repo_name", "time_index", "week_start", *RAW_OUTCOMES]].merge(
        chi[["repo_id", "time_index", *RAW_OUTCOMES]],
        on=["repo_id", "time_index"],
        suffixes=("_new_york", "_chicago"),
        validate="one_to_one",
    )
    for outcome in RAW_OUTCOMES:
        comparison[f"{outcome}_difference_new_york_minus_chicago"] = (
            comparison[f"{outcome}_new_york"] - comparison[f"{outcome}_chicago"]
        )
    comparison["any_outcome_difference"] = comparison[
        [f"{outcome}_difference_new_york_minus_chicago" for outcome in RAW_OUTCOMES]
    ].ne(0).any(axis=1)
    add_check("calendar_week_cells_with_any_outcome_difference", int(comparison["any_outcome_difference"].sum()), int(comparison["any_outcome_difference"].sum()), policy="warn", note="Informational: commits near Monday boundaries can move between adjacent weeks across timezones.")

    qc = pd.DataFrame(records)
    summary_rows: list[dict[str, Any]] = []

    def summary(section: str, metric: str, value: Any, note: str = "") -> None:
        summary_rows.append({"section": section, "metric": metric, "value": value, "note": note})

    summary("definition", "implementation_version", IMPLEMENTATION_VERSION)
    summary("definition", "source_metric_version", SOURCE_METRIC_VERSION)
    summary("definition", "week_definition", WEEK_DEFINITION)
    summary("definition", "support_policy", SUPPORT_POLICY)
    summary("definition", "primary_outcome", PRIMARY_OUTCOME)
    summary("input", "monthly_panel_rows", len(monthly))
    summary("input", "commit_rows", len(commits))
    summary("input", "treatment_history_rows", len(treatment))
    summary("sample", "repositories", repo_meta["repo_name"].nunique())
    summary("sample", "treatment_repositories", len(treatment_repos))
    summary("sample", "control_repositories", int((repo_meta["treatment_group"] == 0).sum()))
    summary("sample", "filled_internal_month_gaps", len(gaps), "FE-only weekly timing analysis uses continuous support from each repo's first to last retained b02 month.")
    summary("timing", "event_week_timezone_mismatch_repositories", int(event_diff["event_week_differs"].sum()))
    for key, panel in panels.items():
        summary("panel", f"{key}_rows", len(panel))
        summary("panel", f"{key}_zero_primary_weeks", int(panel["lines_added_py_source"].eq(0).sum()))
        summary("panel", f"{key}_partial_support_weeks", int(panel["partial_support_week"].sum()))
        for outcome in RAW_OUTCOMES:
            summary("outcome", f"{key}_{outcome}_total", float(panel[outcome].sum()))
    summary("calendar_comparison", "week_cells_with_any_outcome_difference", int(comparison["any_outcome_difference"].sum()))

    return qc, pd.DataFrame(summary_rows), event_diff


def save_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    logging.info("Wrote %d rows to %s", len(frame), path)


def run_self_test() -> None:
    origin = date(2024, 1, 1)
    assert week_start_for_date(date(2024, 1, 1)) == date(2024, 1, 1)
    assert week_start_for_date(date(2024, 1, 7)) == date(2024, 1, 1)
    assert week_start_for_date(date(2024, 1, 8)) == date(2024, 1, 8)
    assert time_index_for_week(date(2024, 1, 1), origin) == 1
    assert time_index_for_week(date(2024, 1, 15), origin) == 3
    # Monday-boundary timezone behavior: 2024-12-02 00:24 New York is still
    # Sunday 2024-12-01 in Chicago, so the week assignment differs by one week.
    instant = pd.Timestamp("2024-12-02T00:24:05-05:00").tz_convert("UTC")
    ny_day = instant.tz_convert("America/New_York").date()
    chi_day = instant.tz_convert("America/Chicago").date()
    assert week_start_for_date(ny_day) == date(2024, 12, 2)
    assert week_start_for_date(chi_day) == date(2024, 11, 25)
    logging.info("Self-test PASS: Monday week indexing and timezone boundary behavior")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare weekly Python velocity timing panels.")
    parser.add_argument("--monthly-panel-file", type=Path)
    parser.add_argument("--commit-file", type=Path)
    parser.add_argument("--treatment-history-file", type=Path)
    parser.add_argument("--new-york-panel-output", type=Path)
    parser.add_argument("--chicago-panel-output", type=Path)
    parser.add_argument("--event-timezone-audit-output", type=Path)
    parser.add_argument("--internal-gap-audit-output", type=Path)
    parser.add_argument("--calendar-outcome-comparison-output", type=Path)
    parser.add_argument("--qc-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--origin-week-start", default="2024-01-01")
    parser.add_argument("--strict-expected-counts", type=int, default=1)
    parser.add_argument("--expected-monthly-rows", type=int, default=1954)
    parser.add_argument("--expected-repositories", type=int, default=167)
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument("--expected-weekly-rows", type=int, default=8599)
    parser.add_argument("--expected-internal-gap-months", type=int, default=1)
    parser.add_argument("--expected-event-week-timezone-mismatches", type=int, default=1)
    parser.add_argument("--expected-repositories-without-commit-rows", type=int, default=1)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    if args.self_test:
        run_self_test()
        return 0

    required_paths = [
        args.monthly_panel_file,
        args.commit_file,
        args.treatment_history_file,
        args.new_york_panel_output,
        args.chicago_panel_output,
        args.event_timezone_audit_output,
        args.internal_gap_audit_output,
        args.calendar_outcome_comparison_output,
        args.qc_output,
        args.summary_output,
    ]
    if any(path is None for path in required_paths):
        raise StageError("All input and output paths are required unless --self-test is used")
    input_paths = [args.monthly_panel_file, args.commit_file, args.treatment_history_file]
    for path in input_paths:
        if not path.exists():
            raise StageError(f"Input file does not exist: {path}")
        logging.info("Input SHA256 %s  %s", sha256_file(path), path)

    try:
        origin = datetime.strptime(args.origin_week_start, "%Y-%m-%d").date()
    except ValueError as exc:
        raise StageError("--origin-week-start must be YYYY-MM-DD") from exc
    if origin.weekday() != 0:
        raise StageError("--origin-week-start must be a Monday")

    logging.info("Reading monthly b02 common panel: %s", args.monthly_panel_file)
    monthly = normalize_monthly_panel(pd.read_csv(args.monthly_panel_file, low_memory=False))
    logging.info("Reading b02-v4 commit-level outcomes: %s", args.commit_file)
    commits = normalize_commit_file(pd.read_csv(args.commit_file, low_memory=False))
    logging.info("Reading b03-c treatment history: %s", args.treatment_history_file)
    treatment = normalize_treatment_history(pd.read_csv(args.treatment_history_file, low_memory=False))

    monthly_repos = set(monthly["repo_name"])
    commits = commits.loc[commits["repo_name"].isin(monthly_repos)].copy()
    supports, gaps = build_repo_support(monthly)
    grid = build_week_grid(supports, origin)
    logging.info(
        "Weekly roster: %d repositories, %d rows; internal monthly gaps filled=%d",
        grid["repo_name"].nunique(), len(grid), len(gaps),
    )

    panels: dict[str, pd.DataFrame] = {}
    event_audits: dict[str, pd.DataFrame] = {}
    for key, timezone_name in CALENDARS.items():
        logging.info("Building %s weekly panel using timezone %s", key, timezone_name)
        panel, event_audit = aggregate_calendar(grid, commits, treatment, key, timezone_name, origin)
        panels[key] = panel
        event_audits[key] = event_audit

    qc, summary, event_diff = build_qc(args, monthly, commits, treatment, gaps, panels, event_audits)
    strict_failures = qc[qc["status"].eq("fail")]
    if int(args.strict_expected_counts) and not strict_failures.empty:
        details = "; ".join(
            f"{row.check_name}: observed={row.observed} expected={row.expected}"
            for row in strict_failures.itertuples(index=False)
        )
        raise StageError("Strict QC failure: " + details)

    ny = panels["new_york"]
    chi = panels["chicago"]
    comparison = ny[["repo_id", "repo_name", "time_index", "week_start", *RAW_OUTCOMES]].merge(
        chi[["repo_id", "time_index", *RAW_OUTCOMES]],
        on=["repo_id", "time_index"],
        suffixes=("_new_york", "_chicago"),
        validate="one_to_one",
    )
    for outcome in RAW_OUTCOMES:
        comparison[f"{outcome}_difference_new_york_minus_chicago"] = (
            comparison[f"{outcome}_new_york"] - comparison[f"{outcome}_chicago"]
        )
    comparison["any_outcome_difference"] = comparison[
        [f"{outcome}_difference_new_york_minus_chicago" for outcome in RAW_OUTCOMES]
    ].ne(0).any(axis=1)

    save_csv(panels["new_york"], args.new_york_panel_output)
    save_csv(panels["chicago"], args.chicago_panel_output)
    save_csv(event_diff, args.event_timezone_audit_output)
    save_csv(gaps, args.internal_gap_audit_output)
    save_csv(comparison, args.calendar_outcome_comparison_output)
    save_csv(qc, args.qc_output)
    save_csv(summary, args.summary_output)

    logging.info(
        "Completed run-x-b03-d weekly panel preparation: rows=%d/calendar; treatment=%d; control=%d; event-week timezone mismatches=%d",
        len(panels["new_york"]),
        panels["new_york"].loc[panels["new_york"]["treatment_group"].eq(1), "repo_name"].nunique(),
        panels["new_york"].loc[panels["new_york"]["treatment_group"].eq(0), "repo_name"].nunique(),
        int(event_diff["event_week_differs"].sum()),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StageError as exc:
        logging.error("%s", exc)
        raise SystemExit(2)
