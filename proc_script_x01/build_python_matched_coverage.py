#!/usr/bin/env python3
"""
Build matched-control Python coverage for the Python-only replication.

This stage preserves the original treatment-to-control assignments from the
replication package. It does not rematch repositories and it does not build the
final DiD panel. Instead, it determines whether each original matched control
slot can provide a Python-eligible code state for each Python-eligible treatment
repo-month.

A control code state is selected with a prior-only as-of lookup:
- use the same calendar-month eligibility row when available;
- otherwise use the latest eligibility row before the treatment month;
- never use a future snapshot.

The selected historical snapshot is used only to determine code state, such as
Python eligibility and snapshot age. This script does not copy historical
activity measures such as commits or lines added into later months.

Primary analysis candidates:
- treatment rows in the enriched panel;
- a valid event month;
- Python eligibility equal to 1.

Outputs:
- treatment-month-control slot details;
- treatment-month coverage counts;
- unique matched-control repo-month history;
- control reuse summary;
- event-window stable-control diagnostics;
- excluded treatment-month rows;
- anomaly details;
- compact summary metrics.
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
    "control_clone_found",
    "pair_status",
}
ELIGIBILITY_REQUIRED_COLUMNS = {
    "dataset_source",
    "repo_name",
    "month",
    "latest_commit_effective",
    "commit_resolution",
    "months_since_observed_commit",
    "python_eligible",
    "scan_status",
}
PANEL_REQUIRED_COLUMNS = {
    "dataset_source",
    "repo_name",
    "time",
    "event",
    "time_to_event",
    "python_eligible",
    "scan_status",
}

SUCCESS_STATUSES = {"success_python", "success_no_python"}
UNAVAILABLE_STATUSES = {
    "missing_monthly_history",
    "missing_clone",
    "no_prior_snapshot",
    "snapshot_unknown",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preserve the original 1:3 matching assignments and calculate "
            "Python-eligible matched-control coverage for each treatment repo-month."
        )
    )
    parser.add_argument("--matching-pairs-file", required=True, type=Path)
    parser.add_argument("--eligibility-file", required=True, type=Path)
    parser.add_argument("--panel-file", required=True, type=Path)
    parser.add_argument("--slot-details-output", required=True, type=Path)
    parser.add_argument("--coverage-output", required=True, type=Path)
    parser.add_argument("--matched-control-months-output", required=True, type=Path)
    parser.add_argument("--control-reuse-output", required=True, type=Path)
    parser.add_argument("--stable-coverage-output", required=True, type=Path)
    parser.add_argument("--excluded-treatment-output", required=True, type=Path)
    parser.add_argument("--anomaly-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument("--event-window-min", type=int, default=-6)
    parser.add_argument("--event-window-max", type=int, default=6)
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


def repo_key(value: object) -> str:
    return clean_text(value).casefold()


def parse_bool(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    text = clean_text(value).casefold()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n", ""}:
        return False
    raise ValueError(f"Cannot parse boolean value: {value!r}")


def require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(sorted(missing))}")


def read_csv_stable(path: Path, string_columns: Iterable[str]) -> pd.DataFrame:
    dtype = {column: "string" for column in string_columns}
    return pd.read_csv(path, dtype=dtype, low_memory=False)


def validate_args(args: argparse.Namespace) -> None:
    for path in [args.matching_pairs_file, args.eligibility_file, args.panel_file]:
        if not path.is_file():
            raise FileNotFoundError(f"Required input file not found: {path}")
    if args.event_window_min > args.event_window_max:
        raise ValueError("event-window-min cannot be greater than event-window-max")


def read_inputs(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pairs = read_csv_stable(
        args.matching_pairs_file,
        ["treatment_repo", "control_repo", "pair_status"],
    )
    eligibility = read_csv_stable(
        args.eligibility_file,
        [
            "dataset_source",
            "repo_name",
            "month",
            "latest_commit_original",
            "latest_commit_effective",
            "commit_resolution",
            "scan_status",
            "error_message",
        ],
    )
    panel = read_csv_stable(
        args.panel_file,
        ["dataset_source", "repo_name", "time", "event", "scan_status"],
    )

    require_columns(pairs, PAIR_REQUIRED_COLUMNS, "matching-pairs CSV")
    require_columns(eligibility, ELIGIBILITY_REQUIRED_COLUMNS, "eligibility CSV")
    require_columns(panel, PANEL_REQUIRED_COLUMNS, "enriched panel CSV")
    return pairs, eligibility, panel


def period_series(values: pd.Series, label: str) -> pd.Series:
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


def month_delta(later: pd.Period, earlier: pd.Period) -> int:
    return int(later.ordinal - earlier.ordinal)


def subtract_months(period: pd.Period, count: int) -> pd.Period:
    return pd.Period(ordinal=period.ordinal - count, freq="M")


def normalize_pairs(pairs: pd.DataFrame) -> pd.DataFrame:
    data = pairs.copy()
    data["treatment_repo"] = data["treatment_repo"].map(clean_text)
    data["control_repo"] = data["control_repo"].map(clean_text)
    data["treatment_key"] = data["treatment_repo"].map(repo_key)
    data["control_key"] = data["control_repo"].map(repo_key)
    data["control_rank"] = pd.to_numeric(data["control_rank"], errors="raise").astype(int)
    data["control_clone_found"] = data["control_clone_found"].map(parse_bool)
    data["pair_status"] = data["pair_status"].map(clean_text)

    if data[["treatment_key", "control_key"]].eq("").any().any():
        raise ValueError("Matching pairs contain blank treatment or control repository names")

    duplicated = data.duplicated(["treatment_key", "control_rank"], keep=False)
    if duplicated.any():
        sample = data.loc[
            duplicated, ["treatment_repo", "control_rank", "control_repo"]
        ].head(20)
        raise ValueError(
            "Matching pairs contain duplicate treatment/control-rank rows: "
            + repr(sample.to_dict(orient="records"))
        )

    pair_counts = data.groupby("treatment_key")["control_rank"].agg(
        count="size", ranks=lambda values: tuple(sorted(set(values)))
    )
    invalid = pair_counts[(pair_counts["count"] != 3) | (pair_counts["ranks"] != (1, 2, 3))]
    if not invalid.empty:
        raise ValueError(
            "Each treatment must have exactly control ranks 1, 2, and 3. Invalid rows: "
            + repr(invalid.head(20).reset_index().to_dict(orient="records"))
        )

    return data.sort_values(["treatment_repo", "control_rank"]).reset_index(drop=True)


def normalize_eligibility(eligibility: pd.DataFrame) -> pd.DataFrame:
    data = eligibility.copy()
    data["dataset_source"] = data["dataset_source"].map(lambda value: clean_text(value).casefold())
    data["repo_name"] = data["repo_name"].map(clean_text)
    data["repo_key"] = data["repo_name"].map(repo_key)
    data["month"] = data["month"].map(clean_text)
    data["month_period"] = period_series(data["month"], "eligibility.month")
    data["scan_status"] = data["scan_status"].map(clean_text)
    data["commit_resolution"] = data["commit_resolution"].map(clean_text)
    data["python_eligible"] = pd.to_numeric(data["python_eligible"], errors="coerce").astype("Int64")
    data["months_since_observed_commit"] = pd.to_numeric(
        data["months_since_observed_commit"], errors="coerce"
    ).astype("Int64")

    control = data[data["dataset_source"].eq("control")].copy()
    duplicated = control.duplicated(["repo_key", "month"], keep=False)
    if duplicated.any():
        sample = control.loc[duplicated, ["repo_name", "month"]].head(20)
        raise ValueError(
            "Control eligibility contains duplicate repository-month rows: "
            + repr(sample.to_dict(orient="records"))
        )
    return data


def normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    data = panel.copy()
    data["dataset_source"] = data["dataset_source"].map(lambda value: clean_text(value).casefold())
    data["repo_name"] = data["repo_name"].map(clean_text)
    data["repo_key"] = data["repo_name"].map(repo_key)
    data["time"] = data["time"].map(clean_text)
    data["time_period"] = period_series(data["time"], "panel.time")
    data["event"] = data["event"].map(clean_text)
    data["event_period"] = period_series(data["event"], "panel.event")
    data["time_to_event"] = pd.to_numeric(data["time_to_event"], errors="coerce")
    data["python_eligible"] = pd.to_numeric(data["python_eligible"], errors="coerce").astype("Int64")
    data["scan_status"] = data["scan_status"].map(clean_text)

    treatment = data[data["dataset_source"].eq("treatment")]
    duplicated = treatment.duplicated(["repo_key", "time"], keep=False)
    if duplicated.any():
        sample = treatment.loc[duplicated, ["repo_name", "time"]].head(20)
        raise ValueError(
            "Treatment panel contains duplicate repository-month rows: "
            + repr(sample.to_dict(orient="records"))
        )
    return data


def classify_treatment_rows(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    treatment = panel[panel["dataset_source"].eq("treatment")].copy()
    treatment["exclusion_reason"] = ""
    treatment.loc[treatment["event_period"].isna(), "exclusion_reason"] = "missing_valid_event"

    valid_event = treatment["event_period"].notna()
    treatment.loc[
        valid_event & treatment["python_eligible"].eq(0), "exclusion_reason"
    ] = "treatment_no_python"
    treatment.loc[
        valid_event & treatment["python_eligible"].isna(), "exclusion_reason"
    ] = "treatment_python_unknown"

    candidate_mask = valid_event & treatment["python_eligible"].eq(1)
    candidates = treatment.loc[candidate_mask].copy()
    candidates["in_event_window"] = candidates["time_to_event"].between(
        -10**9, 10**9, inclusive="both"
    )

    excluded = treatment.loc[~candidate_mask].copy()
    excluded_columns = [
        "repo_name",
        "time",
        "event",
        "time_to_event",
        "python_eligible",
        "scan_status",
        "exclusion_reason",
    ]
    excluded = excluded[excluded_columns].sort_values(["exclusion_reason", "repo_name", "time"])
    return treatment, candidates, excluded


def build_history_map(eligibility: pd.DataFrame) -> dict[str, pd.DataFrame]:
    control = eligibility[eligibility["dataset_source"].eq("control")].copy()
    return {
        key: group.sort_values("month_period").reset_index(drop=True)
        for key, group in control.groupby("repo_key", sort=True)
    }


def select_control_state(
    *,
    pair: pd.Series,
    target_period: pd.Period,
    history: pd.DataFrame | None,
) -> dict[str, object]:
    base: dict[str, object] = {
        "control_slot_status": "",
        "control_slot_usable": 0,
        "eligibility_lookup": "",
        "selected_eligibility_month": "",
        "selected_snapshot_observed_month": "",
        "selected_snapshot_commit": "",
        "selected_commit_resolution": "",
        "selected_scan_status": "",
        "selected_python_eligible": pd.NA,
        "asof_row_gap_months": pd.NA,
        "snapshot_age_months": pd.NA,
        "selected_months_since_observed_commit": pd.NA,
        "selected_error_message": "",
        "pair_status_overridden_by_history": 0,
    }

    if history is None or history.empty:
        base["control_slot_status"] = "missing_monthly_history"
        return base

    history_missing_clone = history["scan_status"].eq("missing_clone").all()
    if history_missing_clone:
        base["control_slot_status"] = "missing_clone"
        first = history.iloc[0]
        base["selected_scan_status"] = clean_text(first.get("scan_status"))
        base["selected_error_message"] = clean_text(first.get("error_message"))
        return base

    pair_reports_missing = (not bool(pair["control_clone_found"])) or (
        clean_text(pair["pair_status"]) != "aligned"
    )
    if pair_reports_missing:
        base["pair_status_overridden_by_history"] = 1

    prior = history[history["month_period"].le(target_period)]
    if prior.empty:
        base["control_slot_status"] = "no_prior_snapshot"
        return base

    selected = prior.iloc[-1]
    selected_period = selected["month_period"]
    row_gap = month_delta(target_period, selected_period)
    since_observed_raw = selected.get("months_since_observed_commit")
    since_observed = int(since_observed_raw) if pd.notna(since_observed_raw) else 0
    observed_period = subtract_months(selected_period, since_observed)
    snapshot_age = row_gap + since_observed

    base.update(
        {
            "eligibility_lookup": "exact_month" if row_gap == 0 else "prior_asof",
            "selected_eligibility_month": selected_period.strftime("%Y-%m"),
            "selected_snapshot_observed_month": observed_period.strftime("%Y-%m"),
            "selected_snapshot_commit": clean_text(selected.get("latest_commit_effective")),
            "selected_commit_resolution": clean_text(selected.get("commit_resolution")),
            "selected_scan_status": clean_text(selected.get("scan_status")),
            "selected_python_eligible": selected.get("python_eligible"),
            "asof_row_gap_months": row_gap,
            "snapshot_age_months": snapshot_age,
            "selected_months_since_observed_commit": since_observed,
            "selected_error_message": clean_text(selected.get("error_message")),
        }
    )

    python_value = selected.get("python_eligible")
    scan_status = clean_text(selected.get("scan_status"))
    if pd.isna(python_value) or scan_status not in SUCCESS_STATUSES:
        base["control_slot_status"] = "snapshot_unknown"
    elif int(python_value) == 1:
        base["control_slot_status"] = "python_eligible"
        base["control_slot_usable"] = 1
    else:
        base["control_slot_status"] = "no_python"
    return base


def build_slot_details(
    candidates: pd.DataFrame,
    pairs: pd.DataFrame,
    eligibility: pd.DataFrame,
    event_window_min: int,
    event_window_max: int,
) -> pd.DataFrame:
    pair_map = {
        key: group.sort_values("control_rank").reset_index(drop=True)
        for key, group in pairs.groupby("treatment_key", sort=True)
    }
    histories = build_history_map(eligibility)
    records: list[dict[str, object]] = []

    for treatment in candidates.sort_values(["repo_name", "time"]).itertuples(index=False):
        treatment_pairs = pair_map.get(treatment.repo_key)
        if treatment_pairs is None or len(treatment_pairs) != 3:
            raise ValueError(
                f"Candidate treatment does not have exactly three matching rows: {treatment.repo_name}"
            )

        for _, pair in treatment_pairs.iterrows():
            state = select_control_state(
                pair=pair,
                target_period=treatment.time_period,
                history=histories.get(pair["control_key"]),
            )
            record = {
                "treatment_repo": treatment.repo_name,
                "treatment_month": treatment.time,
                "event_month": treatment.event,
                "time_to_event": treatment.time_to_event,
                "in_event_window": int(
                    pd.notna(treatment.time_to_event)
                    and event_window_min <= treatment.time_to_event <= event_window_max
                ),
                "treatment_python_eligible": int(treatment.python_eligible),
                "treatment_scan_status": treatment.scan_status,
                "control_rank": int(pair["control_rank"]),
                "control_repo": pair["control_repo"],
                "pair_status": pair["pair_status"],
                "control_clone_found": int(bool(pair["control_clone_found"])),
            }
            record.update(state)
            records.append(record)

    columns = [
        "treatment_repo",
        "treatment_month",
        "event_month",
        "time_to_event",
        "in_event_window",
        "treatment_python_eligible",
        "treatment_scan_status",
        "control_rank",
        "control_repo",
        "pair_status",
        "control_clone_found",
        "control_slot_status",
        "control_slot_usable",
        "eligibility_lookup",
        "selected_eligibility_month",
        "selected_snapshot_observed_month",
        "selected_snapshot_commit",
        "selected_commit_resolution",
        "selected_scan_status",
        "selected_python_eligible",
        "asof_row_gap_months",
        "snapshot_age_months",
        "selected_months_since_observed_commit",
        "selected_error_message",
        "pair_status_overridden_by_history",
    ]
    result = pd.DataFrame.from_records(records, columns=columns)
    for column in [
        "selected_python_eligible",
        "asof_row_gap_months",
        "snapshot_age_months",
        "selected_months_since_observed_commit",
    ]:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")
    return result.sort_values(
        ["treatment_repo", "treatment_month", "control_rank"]
    ).reset_index(drop=True)


def join_names(group: pd.DataFrame, status: str) -> str:
    names = sorted(group.loc[group["control_slot_status"].eq(status), "control_repo"].unique())
    return " | ".join(names)


def build_stable_coverage(
    slots: pd.DataFrame,
    event_window_min: int,
    event_window_max: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    window = slots[slots["in_event_window"].eq(1)].copy()
    pair_rows: list[dict[str, object]] = []
    for (treatment_repo, control_rank, control_repo), group in window.groupby(
        ["treatment_repo", "control_rank", "control_repo"], sort=True
    ):
        eligible = int(group["control_slot_status"].eq("python_eligible").sum())
        total = len(group)
        ages = pd.to_numeric(
            group.loc[group["control_slot_status"].eq("python_eligible"), "snapshot_age_months"],
            errors="coerce",
        ).dropna()
        pair_rows.append(
            {
                "treatment_repo": treatment_repo,
                "control_rank": int(control_rank),
                "control_repo": control_repo,
                "event_window_min": event_window_min,
                "event_window_max": event_window_max,
                "treatment_python_months_observed_in_window": total,
                "control_python_eligible_months": eligible,
                "control_no_python_months": int(group["control_slot_status"].eq("no_python").sum()),
                "control_unknown_or_unavailable_months": int(
                    group["control_slot_status"].isin(UNAVAILABLE_STATUSES).sum()
                ),
                "stable_python_for_observed_treatment_months": int(total > 0 and eligible == total),
                "eligible_snapshot_age_max_months": int(ages.max()) if not ages.empty else pd.NA,
            }
        )

    pair_detail = pd.DataFrame.from_records(pair_rows)
    if pair_detail.empty:
        treatment_summary = pd.DataFrame(
            columns=["treatment_repo", "stable_python_control_count_event_window"]
        )
    else:
        pair_detail["eligible_snapshot_age_max_months"] = pd.to_numeric(
            pair_detail["eligible_snapshot_age_max_months"], errors="coerce"
        ).astype("Int64")
        treatment_summary = (
            pair_detail.groupby("treatment_repo", as_index=False)[
                "stable_python_for_observed_treatment_months"
            ]
            .sum()
            .rename(
                columns={
                    "stable_python_for_observed_treatment_months": "stable_python_control_count_event_window"
                }
            )
        )
    return pair_detail, treatment_summary


def build_coverage(slots: pd.DataFrame, stable_summary: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    group_columns = [
        "treatment_repo",
        "treatment_month",
        "event_month",
        "time_to_event",
        "in_event_window",
    ]
    for keys, group in slots.groupby(group_columns, sort=True, dropna=False):
        ages = pd.to_numeric(
            group.loc[group["control_slot_status"].eq("python_eligible"), "snapshot_age_months"],
            errors="coerce",
        ).dropna()
        python_count = int(group["control_slot_status"].eq("python_eligible").sum())
        record = dict(zip(group_columns, keys, strict=True))
        record.update(
            {
                "original_control_slots": len(group),
                "python_eligible_controls": python_count,
                "no_python_controls": int(group["control_slot_status"].eq("no_python").sum()),
                "snapshot_unknown_controls": int(
                    group["control_slot_status"].eq("snapshot_unknown").sum()
                ),
                "missing_clone_controls": int(
                    group["control_slot_status"].eq("missing_clone").sum()
                ),
                "missing_monthly_history_controls": int(
                    group["control_slot_status"].eq("missing_monthly_history").sum()
                ),
                "no_prior_snapshot_controls": int(
                    group["control_slot_status"].eq("no_prior_snapshot").sum()
                ),
                "exact_month_python_controls": int(
                    (
                        group["control_slot_status"].eq("python_eligible")
                        & group["eligibility_lookup"].eq("exact_month")
                    ).sum()
                ),
                "prior_asof_python_controls": int(
                    (
                        group["control_slot_status"].eq("python_eligible")
                        & group["eligibility_lookup"].eq("prior_asof")
                    ).sum()
                ),
                "has_any_python_control": int(python_count >= 1),
                "has_all_three_python_controls": int(python_count == 3),
                "coverage_class": f"{python_count}_of_3",
                "eligible_snapshot_age_min_months": int(ages.min()) if not ages.empty else pd.NA,
                "eligible_snapshot_age_median_months": float(ages.median()) if not ages.empty else np.nan,
                "eligible_snapshot_age_max_months": int(ages.max()) if not ages.empty else pd.NA,
                "python_eligible_control_repos": join_names(group, "python_eligible"),
                "no_python_control_repos": join_names(group, "no_python"),
                "unavailable_or_unknown_control_repos": " | ".join(
                    sorted(
                        group.loc[
                            group["control_slot_status"].isin(UNAVAILABLE_STATUSES),
                            "control_repo",
                        ].unique()
                    )
                ),
            }
        )
        records.append(record)

    coverage = pd.DataFrame.from_records(records)
    coverage = coverage.merge(
        stable_summary,
        on="treatment_repo",
        how="left",
        validate="many_to_one",
    )
    coverage["stable_python_control_count_event_window"] = pd.to_numeric(
        coverage["stable_python_control_count_event_window"], errors="coerce"
    ).fillna(0).astype(int)
    for column in ["eligible_snapshot_age_min_months", "eligible_snapshot_age_max_months"]:
        coverage[column] = pd.to_numeric(coverage[column], errors="coerce").astype("Int64")
    return coverage.sort_values(["treatment_repo", "treatment_month"]).reset_index(drop=True)


def build_control_reuse(
    pairs: pd.DataFrame,
    candidates: pd.DataFrame,
    eligibility: pd.DataFrame,
    slots: pd.DataFrame,
) -> pd.DataFrame:
    candidate_treatment_keys = set(candidates["repo_key"])
    candidate_pairs = pairs[pairs["treatment_key"].isin(candidate_treatment_keys)]
    control_history = eligibility[eligibility["dataset_source"].eq("control")]

    rows: list[dict[str, object]] = []
    for (control_key, control_repo), group in pairs.groupby(
        ["control_key", "control_repo"], sort=True
    ):
        history = control_history[control_history["repo_key"].eq(control_key)]
        candidate_group = candidate_pairs[candidate_pairs["control_key"].eq(control_key)]
        slot_group = slots[slots["control_repo"].map(repo_key).eq(control_key)]
        rows.append(
            {
                "control_repo": control_repo,
                "matched_treatment_count_all": group["treatment_key"].nunique(),
                "matched_treatment_count_candidates": candidate_group["treatment_key"].nunique(),
                "candidate_treatment_month_slots": len(slot_group),
                "candidate_python_eligible_slots": int(
                    slot_group["control_slot_status"].eq("python_eligible").sum()
                ),
                "control_clone_found": int(group["control_clone_found"].all()),
                "pair_statuses": " | ".join(sorted(group["pair_status"].unique())),
                "monthly_history_rows": len(history),
                "monthly_python_rows": int(history["python_eligible"].eq(1).sum()),
                "monthly_no_python_rows": int(history["python_eligible"].eq(0).sum()),
                "monthly_unknown_rows": int(history["python_eligible"].isna().sum()),
                "first_month": history["month"].min() if not history.empty else "",
                "last_month": history["month"].max() if not history.empty else "",
            }
        )
    return pd.DataFrame.from_records(rows).sort_values(
        ["matched_treatment_count_all", "control_repo"], ascending=[False, True]
    ).reset_index(drop=True)


def build_matched_control_months(
    pairs: pd.DataFrame,
    eligibility: pd.DataFrame,
    reuse: pd.DataFrame,
) -> pd.DataFrame:
    control_keys = set(pairs["control_key"])
    control = eligibility[
        eligibility["dataset_source"].eq("control")
        & eligibility["repo_key"].isin(control_keys)
    ].copy()
    reuse_columns = [
        "control_repo",
        "matched_treatment_count_all",
        "matched_treatment_count_candidates",
    ]
    reuse_copy = reuse[reuse_columns].copy()
    reuse_copy["control_key"] = reuse_copy["control_repo"].map(repo_key)
    control = control.merge(
        reuse_copy.drop(columns=["control_repo"]),
        left_on="repo_key",
        right_on="control_key",
        how="left",
        validate="many_to_one",
    )
    return control.drop(columns=["repo_key", "control_key", "month_period"]).sort_values(
        ["repo_name", "month"]
    ).reset_index(drop=True)


def build_anomalies(slots: pd.DataFrame) -> pd.DataFrame:
    anomalies = slots[slots["control_slot_status"].isin(UNAVAILABLE_STATUSES)].copy()
    columns = [
        "treatment_repo",
        "treatment_month",
        "event_month",
        "time_to_event",
        "control_rank",
        "control_repo",
        "control_slot_status",
        "pair_status",
        "control_clone_found",
        "selected_eligibility_month",
        "selected_snapshot_commit",
        "selected_scan_status",
        "selected_error_message",
    ]
    return anomalies[columns].sort_values(
        ["control_slot_status", "control_repo", "treatment_repo", "treatment_month"]
    ).reset_index(drop=True)


def add_summary_row(
    rows: list[dict[str, object]],
    section: str,
    metric: str,
    value: object,
    note: str = "",
) -> None:
    rows.append({"section": section, "metric": metric, "value": value, "note": note})


def build_summary(
    *,
    pairs: pd.DataFrame,
    eligibility: pd.DataFrame,
    treatment_all: pd.DataFrame,
    candidates: pd.DataFrame,
    excluded: pd.DataFrame,
    slots: pd.DataFrame,
    coverage: pd.DataFrame,
    reuse: pd.DataFrame,
    stable: pd.DataFrame,
    anomalies: pd.DataFrame,
    event_window_min: int,
    event_window_max: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    add_summary_row(rows, "implementation", "version", "v1")
    add_summary_row(
        rows,
        "definition",
        "primary_treatment_candidate",
        "valid_event_and_python_eligible_repo_month",
    )
    add_summary_row(
        rows,
        "definition",
        "control_snapshot_lookup",
        "latest_control_eligibility_row_at_or_before_treatment_month",
        "Future snapshots are never used.",
    )
    add_summary_row(
        rows,
        "definition",
        "control_activity_handling",
        "not_performed_in_run_x_a04",
        "Historical activity values are not copied; run-x-a05 constructs velocity rows.",
    )
    add_summary_row(
        rows,
        "definition",
        "event_window",
        f"{event_window_min}:{event_window_max}",
        "Used only for stable-control diagnostics, not as a main-sample requirement.",
    )

    add_summary_row(rows, "input", "matching_pair_rows", len(pairs))
    add_summary_row(rows, "input", "matching_treatments", pairs["treatment_key"].nunique())
    add_summary_row(rows, "input", "unique_matched_controls", pairs["control_key"].nunique())
    add_summary_row(
        rows,
        "input",
        "control_repo_month_rows",
        int(eligibility["dataset_source"].eq("control").sum()),
    )
    add_summary_row(rows, "treatment", "all_panel_rows", len(treatment_all))
    add_summary_row(
        rows,
        "treatment",
        "valid_event_rows",
        int(treatment_all["event_period"].notna().sum()),
    )
    add_summary_row(rows, "treatment", "python_candidate_rows", len(candidates))
    add_summary_row(rows, "treatment", "candidate_repositories", candidates["repo_key"].nunique())
    for reason, count in excluded["exclusion_reason"].value_counts().sort_index().items():
        add_summary_row(rows, "treatment_exclusion", reason, int(count))

    add_summary_row(rows, "slot", "candidate_control_slots", len(slots))
    add_summary_row(
        rows,
        "slot",
        "pair_status_rows_overridden_by_successful_history",
        int(slots["pair_status_overridden_by_history"].sum()),
        "A later eligibility scan is treated as authoritative when an older pair audit still reports a missing clone.",
    )
    for status, count in slots["control_slot_status"].value_counts().sort_index().items():
        add_summary_row(rows, "slot_status", status, int(count))
    for method, count in slots["eligibility_lookup"].replace("", pd.NA).dropna().value_counts().sort_index().items():
        add_summary_row(rows, "lookup", method, int(count))

    for control_count, count in (
        coverage["python_eligible_controls"].value_counts().sort_index().items()
    ):
        add_summary_row(rows, "coverage", f"treatment_months_with_{control_count}_python_controls", int(count))
    add_summary_row(
        rows,
        "coverage",
        "treatment_months_with_any_python_control",
        int(coverage["has_any_python_control"].sum()),
    )
    add_summary_row(
        rows,
        "coverage",
        "treatment_months_with_all_three_python_controls",
        int(coverage["has_all_three_python_controls"].sum()),
    )

    eligible_ages = pd.to_numeric(
        slots.loc[slots["control_slot_status"].eq("python_eligible"), "snapshot_age_months"],
        errors="coerce",
    ).dropna()
    if not eligible_ages.empty:
        add_summary_row(rows, "snapshot_age", "eligible_median_months", float(eligible_ages.median()))
        add_summary_row(rows, "snapshot_age", "eligible_max_months", int(eligible_ages.max()))
        for threshold in [12, 24, 60]:
            add_summary_row(
                rows,
                "snapshot_age",
                f"eligible_slots_gt_{threshold}_months",
                int((eligible_ages > threshold).sum()),
            )

    add_summary_row(rows, "reuse", "controls_reused_by_multiple_treatments", int((reuse["matched_treatment_count_all"] > 1).sum()))
    add_summary_row(rows, "reuse", "maximum_treatment_reuse_count", int(reuse["matched_treatment_count_all"].max()))
    add_summary_row(rows, "stable_diagnostic", "pair_rows", len(stable))
    add_summary_row(
        rows,
        "stable_diagnostic",
        "stable_python_pairs",
        int(stable["stable_python_for_observed_treatment_months"].sum()) if not stable.empty else 0,
    )
    add_summary_row(rows, "anomaly", "rows", len(anomalies))
    return pd.DataFrame.from_records(rows, columns=["section", "metric", "value", "note"])


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    logging.info("Wrote %s rows to %s", len(frame), path)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    validate_args(args)

    pairs_raw, eligibility_raw, panel_raw = read_inputs(args)
    pairs = normalize_pairs(pairs_raw)
    eligibility = normalize_eligibility(eligibility_raw)
    panel = normalize_panel(panel_raw)

    treatment_all, candidates, excluded = classify_treatment_rows(panel)
    candidate_keys = set(candidates["repo_key"])
    missing_pair_treatments = sorted(candidate_keys - set(pairs["treatment_key"]))
    if missing_pair_treatments:
        raise ValueError(
            "Candidate treatments missing from matching pairs: " + ", ".join(missing_pair_treatments)
        )

    slots = build_slot_details(
        candidates,
        pairs,
        eligibility,
        args.event_window_min,
        args.event_window_max,
    )
    stable, stable_summary = build_stable_coverage(
        slots,
        args.event_window_min,
        args.event_window_max,
    )
    coverage = build_coverage(slots, stable_summary)
    reuse = build_control_reuse(pairs, candidates, eligibility, slots)
    matched_control_months = build_matched_control_months(pairs, eligibility, reuse)
    anomalies = build_anomalies(slots)
    summary = build_summary(
        pairs=pairs,
        eligibility=eligibility,
        treatment_all=treatment_all,
        candidates=candidates,
        excluded=excluded,
        slots=slots,
        coverage=coverage,
        reuse=reuse,
        stable=stable,
        anomalies=anomalies,
        event_window_min=args.event_window_min,
        event_window_max=args.event_window_max,
    )

    write_csv(slots, args.slot_details_output)
    write_csv(coverage, args.coverage_output)
    write_csv(matched_control_months, args.matched_control_months_output)
    write_csv(reuse, args.control_reuse_output)
    write_csv(stable, args.stable_coverage_output)
    write_csv(excluded, args.excluded_treatment_output)
    write_csv(anomalies, args.anomaly_output)
    write_csv(summary, args.summary_output)

    logging.info(
        "Completed run-x-a04 coverage: %d treatment-months, %d slots, %d usable Python slots",
        len(coverage),
        len(slots),
        int(slots["control_slot_usable"].sum()),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - command-line safety boundary
        logging.exception("run-x-a04 failed: %s", exc)
        raise SystemExit(1) from exc
