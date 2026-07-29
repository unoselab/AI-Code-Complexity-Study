#!/usr/bin/env python3
"""Audit matched-pair calendar alignment for two influential control repositories.

This script complements the run-py-8b fixed-sample month-ablation DiD.
It does not estimate a causal effect. It answers a narrower diagnostic question:

  For each class-method spike month in pieces-app/cli-agent and
  HelpingAI/Webscout, which treatment repositories were matched to that control,
  what is the spike month's relative event time for each matched treatment, and
  do the treatment and control repository-month rows coexist in the zero-inclusive
  panel and in the original positive-outcome fixed sample?

Important design note:
  The Borusyak static model used in run-py-7h/run-py-7p does not load pair IDs.
  Matching selects the control repository set, while estimation uses repositories
  and calendar-month fixed effects. Therefore, this script reports pair-calendar
  alignment as a diagnostic rather than claiming that the estimator performs a
  literal one-treatment-to-one-control row comparison.
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

TARGET_REPOSITORIES = (
    "pieces-app/cli-agent",
    "HelpingAI/Webscout",
)

DEFAULT_SPIKE_MONTHS = {
    "pieces-app/cli-agent": ("2025-06", "2025-07"),
    "HelpingAI/Webscout": ("2025-01", "2025-04", "2025-06"),
}

EXPECTED_SPIKE_INCREMENTS = {
    ("pieces-app/cli-agent", "2025-06"): 24,
    ("pieces-app/cli-agent", "2025-07"): 22,
    ("HelpingAI/Webscout", "2025-01"): 10,
    ("HelpingAI/Webscout", "2025-04"): 18,
    ("HelpingAI/Webscout", "2025-06"): 30,
}

OUTPUT_PREFIX = "cliagent_webscout_pair_alignment"


@dataclass(frozen=True)
class Paths:
    fixed_panel: Path
    zero_panel: Path
    month_audit: Path
    matched_pairs: Path
    treatment_meta: Path
    output_dir: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit treatment-control pair calendar alignment for cli-agent and "
            "Webscout class-method spike months."
        )
    )
    parser.add_argument("--fixed-panel", type=Path)
    parser.add_argument("--zero-panel", type=Path)
    parser.add_argument("--month-audit", type=Path)
    parser.add_argument("--matched-pairs", type=Path)
    parser.add_argument("--treatment-meta", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--target-repositories",
        default="|".join(TARGET_REPOSITORIES),
        help="Pipe-delimited control repository names.",
    )
    parser.add_argument(
        "--minimum-event-time",
        type=int,
        default=-6,
        help="Minimum relative event month used by the project dynamic window.",
    )
    parser.add_argument(
        "--maximum-event-time",
        type=int,
        default=6,
        help="Maximum relative event month used by the project dynamic window.",
    )
    parser.add_argument(
        "--skip-frozen-count-checks",
        action="store_true",
        help="Skip expected spike-month increment checks.",
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


def month_difference(later: str, earlier: str) -> int:
    later_period = pd.Period(later, freq="M")
    earlier_period = pd.Period(earlier, freq="M")
    return int(later_period.ordinal - earlier_period.ordinal)


def parse_targets(value: str) -> tuple[str, ...]:
    targets = tuple(item.strip() for item in value.split("|") if item.strip())
    if not targets:
        raise ValueError("At least one target repository is required")
    if len(set(targets)) != len(targets):
        raise ValueError("Target repository list contains duplicates")
    return targets


def detect_pair_columns(df: pd.DataFrame) -> tuple[str, str | None, list[str]]:
    treatment_candidates = [
        "treatment_repo",
        "treated_repo",
        "treatment_repo_name",
        "repo_name",
    ]
    control_candidates = [
        "control_repo",
        "matched_control",
        "matched_control_repo",
        "control_repo_name",
    ]
    treatment_col = next((c for c in treatment_candidates if c in df.columns), None)
    control_col = next((c for c in control_candidates if c in df.columns), None)
    wide_controls = [c for c in df.columns if c.startswith("matched_control_")]
    if treatment_col is None:
        raise ValueError("Could not identify a treatment repository column in pair file")
    if control_col is None and not wide_controls:
        raise ValueError("Could not identify control repository columns in pair file")
    return treatment_col, control_col, wide_controls


def normalize_pairs(raw: pd.DataFrame) -> pd.DataFrame:
    treatment_col, control_col, wide_controls = detect_pair_columns(raw)
    data = raw.copy()

    if control_col is None:
        id_cols = [c for c in data.columns if c not in wide_controls]
        data = data.melt(
            id_vars=id_cols,
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
    data = data.sort_values(["control_repo", "treatment_repo"], kind="stable")
    data.insert(0, "pair_id", np.arange(1, len(data) + 1, dtype="int64"))
    return data[["pair_id", "treatment_repo", "control_repo", "control_rank"]]


def detect_treatment_meta_columns(df: pd.DataFrame) -> tuple[str, str]:
    repo_candidates = ["repo_name", "treatment_repo", "repository"]
    event_candidates = ["event_month", "event", "adoption_month"]
    repo_col = next((c for c in repo_candidates if c in df.columns), None)
    event_col = next((c for c in event_candidates if c in df.columns), None)
    if repo_col is None or event_col is None:
        raise ValueError(
            "Treatment metadata must contain repository and event-month columns"
        )
    return repo_col, event_col


def normalize_treatment_meta(raw: pd.DataFrame) -> pd.DataFrame:
    repo_col, event_col = detect_treatment_meta_columns(raw)
    data = raw[[repo_col, event_col]].rename(
        columns={repo_col: "treatment_repo", event_col: "treatment_event_month"}
    )
    data["treatment_repo"] = normalize_repo(data["treatment_repo"])
    data["treatment_event_month"] = normalize_month(
        data["treatment_event_month"], "Treatment metadata event month"
    )
    data = data.dropna(subset=["treatment_repo", "treatment_event_month"])
    data = data[
        data["treatment_repo"].ne("") & data["treatment_event_month"].ne("")
    ].copy()
    conflicts = data.groupby("treatment_repo")["treatment_event_month"].nunique()
    if (conflicts > 1).any():
        examples = conflicts[conflicts > 1].index[:20].tolist()
        raise ValueError(f"Conflicting treatment event months: {examples}")
    return data.drop_duplicates("treatment_repo")


def prepare_panel(raw: pd.DataFrame, label: str) -> pd.DataFrame:
    require_columns(
        raw,
        [
            "dataset_source",
            "repo_name",
            "time",
            "event",
            "npr_agc_regular_module_function_unique_bodies",
        ],
        label,
    )
    data = raw.copy()
    data["repo_name"] = normalize_repo(data["repo_name"])
    data["time"] = normalize_month(data["time"], f"{label} time")
    if data.duplicated(["dataset_source", "repo_name", "time"]).any():
        raise ValueError(f"{label} contains duplicate repository-month keys")
    return data


def prepare_month_audit(raw: pd.DataFrame) -> pd.DataFrame:
    require_columns(
        raw,
        [
            "dataset_source",
            "repo_name",
            "time",
            "baseline_outcome",
            "method_increment",
            "one_repo_outcome",
        ],
        "run-py-7p month audit",
    )
    data = raw.copy()
    data["repo_name"] = normalize_repo(data["repo_name"])
    data["time"] = normalize_month(data["time"], "Month audit time")
    for column in ["baseline_outcome", "method_increment", "one_repo_outcome"]:
        data[column] = pd.to_numeric(data[column], errors="raise")
    if data.duplicated(["repo_name", "time"]).any():
        raise ValueError("Month audit contains duplicate repository-month keys")
    return data


def build_spike_table(
    audit: pd.DataFrame,
    targets: tuple[str, ...],
    skip_frozen_count_checks: bool,
) -> pd.DataFrame:
    rows: list[pd.Series] = []
    for repo in targets:
        months = DEFAULT_SPIKE_MONTHS.get(repo)
        if months is None:
            raise ValueError(f"No default spike-month definition for {repo}")
        for month in months:
            subset = audit[(audit["repo_name"] == repo) & (audit["time"] == month)]
            if len(subset) != 1:
                raise ValueError(
                    f"Expected exactly one month-audit row for {repo} {month}; got {len(subset)}"
                )
            row = subset.iloc[0].copy()
            row["spike_rank_within_repository"] = months.index(month) + 1
            rows.append(row)

    spikes = pd.DataFrame(rows).reset_index(drop=True)
    if not (spikes["dataset_source"].astype(str) == "control").all():
        raise ValueError("Target spike rows must all be control observations")

    if not skip_frozen_count_checks:
        for _, row in spikes.iterrows():
            key = (str(row["repo_name"]), str(row["time"]))
            expected = EXPECTED_SPIKE_INCREMENTS[key]
            actual = int(row["method_increment"])
            if actual != expected:
                raise ValueError(
                    f"Unexpected method increment for {key[0]} {key[1]}: "
                    f"expected {expected}, got {actual}"
                )
    return spikes


def lookup_panel_row(panel: pd.DataFrame, repo: str, month: str) -> pd.Series | None:
    subset = panel[(panel["repo_name"] == repo) & (panel["time"] == month)]
    if len(subset) == 0:
        return None
    if len(subset) > 1:
        raise ValueError(f"Multiple panel rows for {repo} {month}")
    return subset.iloc[0]


def build_alignment(
    spikes: pd.DataFrame,
    pairs: pd.DataFrame,
    treatment_meta: pd.DataFrame,
    zero_panel: pd.DataFrame,
    fixed_panel: pd.DataFrame,
    minimum_event_time: int,
    maximum_event_time: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    target_pairs = pairs[pairs["control_repo"].isin(spikes["repo_name"].unique())].copy()
    missing_controls = sorted(set(spikes["repo_name"]) - set(target_pairs["control_repo"]))
    if missing_controls:
        raise ValueError(
            "Target controls are missing from matched-pair manifest: "
            + ", ".join(missing_controls)
        )

    target_pairs = target_pairs.merge(
        treatment_meta,
        on="treatment_repo",
        how="left",
        validate="many_to_one",
    )
    if target_pairs["treatment_event_month"].isna().any():
        examples = target_pairs.loc[
            target_pairs["treatment_event_month"].isna(), "treatment_repo"
        ].head(20).tolist()
        raise ValueError(f"Matched treatments missing event metadata: {examples}")

    panel_event_map = (
        zero_panel[zero_panel["dataset_source"] == "treatment"]
        .dropna(subset=["event"])
        .assign(panel_event=lambda d: normalize_month(d["event"], "Treatment panel event"))
        .groupby("repo_name", as_index=False)["panel_event"]
        .agg(lambda x: "|".join(sorted(set(x.dropna().astype(str)))))
    )
    target_pairs = target_pairs.merge(
        panel_event_map,
        left_on="treatment_repo",
        right_on="repo_name",
        how="left",
        validate="many_to_one",
    ).drop(columns=["repo_name"], errors="ignore")
    target_pairs["treatment_meta_matches_panel_event"] = (
        target_pairs["panel_event"].fillna("")
        == target_pairs["treatment_event_month"].fillna("")
    )

    records: list[dict[str, object]] = []
    for _, pair in target_pairs.iterrows():
        control_repo = str(pair["control_repo"])
        repo_spikes = spikes[spikes["repo_name"] == control_repo]
        for _, spike in repo_spikes.iterrows():
            spike_month = str(spike["time"])
            treatment_repo = str(pair["treatment_repo"])
            event_month = str(pair["treatment_event_month"])
            aligned_event_time = month_difference(spike_month, event_month)

            treatment_zero = lookup_panel_row(zero_panel, treatment_repo, spike_month)
            treatment_fixed = lookup_panel_row(fixed_panel, treatment_repo, spike_month)
            control_zero = lookup_panel_row(zero_panel, control_repo, spike_month)
            control_fixed = lookup_panel_row(fixed_panel, control_repo, spike_month)

            treatment_zero_present = treatment_zero is not None
            treatment_fixed_present = treatment_fixed is not None
            control_zero_present = control_zero is not None
            control_fixed_present = control_fixed is not None

            treatment_zero_outcome = (
                float(treatment_zero["npr_agc_regular_module_function_unique_bodies"])
                if treatment_zero_present
                else np.nan
            )
            treatment_fixed_outcome = (
                float(treatment_fixed["npr_agc_regular_module_function_unique_bodies"])
                if treatment_fixed_present
                else np.nan
            )

            if treatment_fixed_present and control_fixed_present:
                status = "both_rows_in_original_positive_fixed_sample"
            elif treatment_zero_present and control_zero_present:
                if treatment_zero_outcome <= 0:
                    status = "treatment_zero_outcome_excluded_from_fixed_sample"
                else:
                    status = "both_zero_inclusive_but_not_both_in_fixed_sample"
            elif not treatment_zero_present:
                status = "treatment_calendar_month_missing_from_zero_panel"
            elif not control_zero_present:
                status = "control_calendar_month_missing_from_zero_panel"
            else:
                status = "other_alignment_gap"

            records.append(
                {
                    "pair_id": int(pair["pair_id"]),
                    "control_rank": pair["control_rank"],
                    "treatment_repo": treatment_repo,
                    "control_repo": control_repo,
                    "treatment_event_month": event_month,
                    "control_spike_month": spike_month,
                    "aligned_event_time": aligned_event_time,
                    "within_dynamic_window": minimum_event_time
                    <= aligned_event_time
                    <= maximum_event_time,
                    "treatment_meta_matches_panel_event": bool(
                        pair["treatment_meta_matches_panel_event"]
                    ),
                    "control_baseline_outcome": float(spike["baseline_outcome"]),
                    "control_method_increment": float(spike["method_increment"]),
                    "control_hybrid_outcome": float(spike["one_repo_outcome"]),
                    "control_zero_panel_row_present": control_zero_present,
                    "control_fixed_sample_row_present": control_fixed_present,
                    "treatment_zero_panel_row_present_same_calendar_month": treatment_zero_present,
                    "treatment_fixed_sample_row_present_same_calendar_month": treatment_fixed_present,
                    "treatment_zero_panel_baseline_outcome": treatment_zero_outcome,
                    "treatment_fixed_sample_baseline_outcome": treatment_fixed_outcome,
                    "both_rows_zero_inclusive_same_calendar_month": treatment_zero_present
                    and control_zero_present,
                    "both_rows_fixed_sample_same_calendar_month": treatment_fixed_present
                    and control_fixed_present,
                    "pair_calendar_alignment_status": status,
                    "estimator_uses_pair_id_directly": False,
                    "diagnostic_only": True,
                }
            )

    alignment = pd.DataFrame(records).sort_values(
        ["control_repo", "control_spike_month", "treatment_repo"], kind="stable"
    )

    spike_summary = (
        alignment.groupby(["control_repo", "control_spike_month"], as_index=False)
        .agg(
            matched_treatment_pairs=("pair_id", "nunique"),
            unique_treatment_repositories=("treatment_repo", "nunique"),
            unique_treatment_event_months=("treatment_event_month", "nunique"),
            minimum_aligned_event_time=("aligned_event_time", "min"),
            maximum_aligned_event_time=("aligned_event_time", "max"),
            pairs_within_dynamic_window=("within_dynamic_window", "sum"),
            pairs_with_both_zero_panel_rows=(
                "both_rows_zero_inclusive_same_calendar_month",
                "sum",
            ),
            pairs_with_both_fixed_sample_rows=(
                "both_rows_fixed_sample_same_calendar_month",
                "sum",
            ),
            control_method_increment=("control_method_increment", "first"),
            control_baseline_outcome=("control_baseline_outcome", "first"),
        )
    )
    spike_summary["fixed_sample_pair_alignment_share"] = (
        spike_summary["pairs_with_both_fixed_sample_rows"]
        / spike_summary["matched_treatment_pairs"]
    )
    spike_summary["zero_panel_pair_alignment_share"] = (
        spike_summary["pairs_with_both_zero_panel_rows"]
        / spike_summary["matched_treatment_pairs"]
    )

    control_summary = (
        target_pairs.groupby("control_repo", as_index=False)
        .agg(
            matched_pair_count=("pair_id", "nunique"),
            matched_treatment_repositories=("treatment_repo", "nunique"),
            unique_treatment_event_months=("treatment_event_month", "nunique"),
            earliest_treatment_event_month=("treatment_event_month", "min"),
            latest_treatment_event_month=("treatment_event_month", "max"),
            treatment_event_metadata_consistent=(
                "treatment_meta_matches_panel_event",
                "all",
            ),
        )
    )
    control_summary["control_reused_across_multiple_treatment_cohorts"] = (
        control_summary["unique_treatment_event_months"] > 1
    )
    control_summary["estimator_uses_pair_id_directly"] = False
    control_summary["pair_manifest_role"] = (
        "control-sample selection and diagnostic provenance"
    )

    coverage = (
        alignment.groupby(
            [
                "control_repo",
                "treatment_repo",
                "treatment_event_month",
                "aligned_event_time",
                "pair_calendar_alignment_status",
            ],
            as_index=False,
        )
        .agg(
            spike_month_rows=("control_spike_month", "nunique"),
            method_increment_across_spike_months=("control_method_increment", "sum"),
        )
        .sort_values(["control_repo", "treatment_repo", "aligned_event_time"])
    )

    return target_pairs, alignment, spike_summary, control_summary, coverage


def build_findings(
    alignment: pd.DataFrame,
    spike_summary: pd.DataFrame,
    control_summary: pd.DataFrame,
) -> pd.DataFrame:
    findings: list[dict[str, object]] = []
    for _, row in control_summary.iterrows():
        repo = str(row["control_repo"])
        if bool(row["control_reused_across_multiple_treatment_cohorts"]):
            findings.append(
                {
                    "finding_type": "control_reused_across_cohorts",
                    "repo_name": repo,
                    "severity": "diagnostic",
                    "value": int(row["unique_treatment_event_months"]),
                    "interpretation": (
                        "The same control is matched to treatments with multiple adoption "
                        "months, so one control calendar month maps to different relative "
                        "event times across pairs."
                    ),
                }
            )

    for _, row in spike_summary.iterrows():
        findings.append(
            {
                "finding_type": "spike_month_fixed_sample_alignment_share",
                "repo_name": row["control_repo"],
                "severity": "diagnostic",
                "value": float(row["fixed_sample_pair_alignment_share"]),
                "interpretation": (
                    f"For control spike month {row['control_spike_month']}, this is the "
                    "share of matched treatments that also have a row in the original "
                    "positive-outcome fixed sample in the same calendar month."
                ),
            }
        )

    outside = alignment[~alignment["within_dynamic_window"]]
    if not outside.empty:
        for repo, group in outside.groupby("control_repo"):
            findings.append(
                {
                    "finding_type": "pair_spike_outside_dynamic_window",
                    "repo_name": repo,
                    "severity": "diagnostic",
                    "value": int(len(group)),
                    "interpretation": (
                        "Some control spike-month pair mappings fall outside event time "
                        "-6 to +6 for their matched treatments. Static estimation can "
                        "still use calendar-time control observations in first-stage "
                        "imputation, but the pair is not an in-window event-time match."
                    ),
                }
            )

    findings.append(
        {
            "finding_type": "estimator_pair_mapping",
            "repo_name": "ALL",
            "severity": "design_note",
            "value": 0,
            "interpretation": (
                "The current static Borusyak script does not pass pair_id to the "
                "estimator. Pair matching selects controls; the model uses repository "
                "and calendar-month fixed effects rather than literal pair-row contrasts."
            ),
        }
    )
    return pd.DataFrame(findings)


def write_outputs(
    output_dir: Path,
    target_pairs: pd.DataFrame,
    alignment: pd.DataFrame,
    spike_summary: pd.DataFrame,
    control_summary: pd.DataFrame,
    coverage: pd.DataFrame,
    findings: pd.DataFrame,
    validation: pd.DataFrame,
    metadata: dict[str, object],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_pairs.to_csv(output_dir / f"{OUTPUT_PREFIX}_target_pair_manifest.csv", index=False)
    alignment.to_csv(output_dir / f"{OUTPUT_PREFIX}_spike_month_alignment.csv", index=False)
    spike_summary.to_csv(
        output_dir / f"{OUTPUT_PREFIX}_spike_month_alignment_summary.csv", index=False
    )
    control_summary.to_csv(
        output_dir / f"{OUTPUT_PREFIX}_control_pair_summary.csv", index=False
    )
    coverage.to_csv(
        output_dir / f"{OUTPUT_PREFIX}_treatment_calendar_coverage.csv", index=False
    )
    findings.to_csv(output_dir / f"{OUTPUT_PREFIX}_diagnostic_findings.csv", index=False)
    validation.to_csv(output_dir / f"{OUTPUT_PREFIX}_validation.csv", index=False)
    (output_dir / f"{OUTPUT_PREFIX}_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / f"{OUTPUT_PREFIX}_status.txt").write_text(
        "PASS\nPair alignment is diagnostic only; repository removal is not justified.\n",
        encoding="utf-8",
    )


def run_analysis(paths: Paths, args: argparse.Namespace) -> dict[str, pd.DataFrame]:
    targets = parse_targets(args.target_repositories)
    for path in [
        paths.fixed_panel,
        paths.zero_panel,
        paths.month_audit,
        paths.matched_pairs,
        paths.treatment_meta,
    ]:
        if not path.exists():
            raise FileNotFoundError(f"Required input not found: {path}")

    fixed_panel = prepare_panel(pd.read_csv(paths.fixed_panel), "Fixed sample panel")
    zero_panel = prepare_panel(pd.read_csv(paths.zero_panel), "Zero-inclusive panel")
    month_audit = prepare_month_audit(pd.read_csv(paths.month_audit))
    pairs = normalize_pairs(pd.read_csv(paths.matched_pairs))
    treatment_meta = normalize_treatment_meta(pd.read_csv(paths.treatment_meta))
    spikes = build_spike_table(
        month_audit,
        targets,
        args.skip_frozen_count_checks,
    )

    (
        target_pairs,
        alignment,
        spike_summary,
        control_summary,
        coverage,
    ) = build_alignment(
        spikes,
        pairs,
        treatment_meta,
        zero_panel,
        fixed_panel,
        args.minimum_event_time,
        args.maximum_event_time,
    )
    findings = build_findings(alignment, spike_summary, control_summary)

    validation_rows = [
        {
            "check_name": "target_repository_count",
            "value": len(targets),
            "passed": len(targets) == 2,
        },
        {
            "check_name": "target_controls_present_in_pair_manifest",
            "value": target_pairs["control_repo"].nunique(),
            "passed": target_pairs["control_repo"].nunique() == len(targets),
        },
        {
            "check_name": "target_pair_manifest_has_no_duplicate_pairs",
            "value": int(target_pairs.duplicated(["treatment_repo", "control_repo"]).sum()),
            "passed": not target_pairs.duplicated(["treatment_repo", "control_repo"]).any(),
        },
        {
            "check_name": "treatment_event_metadata_matches_panel",
            "value": int((~target_pairs["treatment_meta_matches_panel_event"]).sum()),
            "passed": bool(target_pairs["treatment_meta_matches_panel_event"].all()),
        },
        {
            "check_name": "expected_spike_month_rows",
            "value": len(spikes),
            "passed": len(spikes) == 5,
        },
        {
            "check_name": "alignment_rows_nonzero",
            "value": len(alignment),
            "passed": len(alignment) > 0,
        },
        {
            "check_name": "all_control_spike_rows_present_in_fixed_sample",
            "value": int((~alignment["control_fixed_sample_row_present"]).sum()),
            "passed": bool(alignment["control_fixed_sample_row_present"].all()),
        },
        {
            "check_name": "analysis_labeled_diagnostic_only",
            "value": int((~alignment["diagnostic_only"]).sum()),
            "passed": bool(alignment["diagnostic_only"].all()),
        },
        {
            "check_name": "estimator_pair_mapping_not_claimed",
            "value": int(alignment["estimator_uses_pair_id_directly"].sum()),
            "passed": not bool(alignment["estimator_uses_pair_id_directly"].any()),
        },
    ]
    validation = pd.DataFrame(validation_rows)
    failed = validation[~validation["passed"]]
    if not failed.empty:
        raise ValueError(
            "Pair-alignment validation failed: "
            + ", ".join(failed["check_name"].tolist())
        )

    metadata = {
        "analysis": "treatment-control pair calendar alignment diagnostic",
        "target_repositories": list(targets),
        "spike_months": {repo: list(DEFAULT_SPIKE_MONTHS[repo]) for repo in targets},
        "minimum_event_time": args.minimum_event_time,
        "maximum_event_time": args.maximum_event_time,
        "fixed_panel": str(paths.fixed_panel),
        "zero_panel": str(paths.zero_panel),
        "month_audit": str(paths.month_audit),
        "matched_pairs": str(paths.matched_pairs),
        "treatment_meta": str(paths.treatment_meta),
        "pair_id_used_directly_in_static_estimator": False,
        "causal_interpretation_allowed": False,
        "repository_removal_justified": False,
        "target_pair_count": int(target_pairs["pair_id"].nunique()),
        "alignment_rows": int(len(alignment)),
    }

    write_outputs(
        paths.output_dir,
        target_pairs,
        alignment,
        spike_summary,
        control_summary,
        coverage,
        findings,
        validation,
        metadata,
    )

    print("=" * 80)
    print("run-py-8b: treatment-control pair calendar alignment audit")
    print("=" * 80)
    print("Status: PASS")
    print(f"Target controls: {len(targets)}")
    print(f"Matched pairs: {target_pairs['pair_id'].nunique()}")
    print(f"Pair-spike alignment rows: {len(alignment)}")
    print("Static estimator uses pair IDs directly: NO")
    print("\nControl pair summary:")
    print(control_summary.to_string(index=False))
    print("\nSpike-month alignment summary:")
    print(spike_summary.to_string(index=False))
    print(f"\nOutput directory: {paths.output_dir}")
    print("=" * 80)

    return {
        "target_pairs": target_pairs,
        "alignment": alignment,
        "spike_summary": spike_summary,
        "control_summary": control_summary,
        "coverage": coverage,
        "findings": findings,
        "validation": validation,
    }


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="run-py-8b-pair-self-test-") as tmp:
        root = Path(tmp)
        fixed_path = root / "fixed.csv"
        zero_path = root / "zero.csv"
        audit_path = root / "audit.csv"
        pairs_path = root / "pairs.csv"
        meta_path = root / "meta.csv"
        out_dir = root / "out"

        treatments = ["org/treat-a", "org/treat-b"]
        zero_rows: list[dict[str, object]] = []
        fixed_rows: list[dict[str, object]] = []
        for treatment, event in zip(treatments, ["2025-03", "2025-05"]):
            for month, outcome in [("2025-01", 1), ("2025-04", 0), ("2025-06", 2), ("2025-07", 1)]:
                row = {
                    "dataset_source": "treatment",
                    "repo_name": treatment,
                    "time": month,
                    "event": event,
                    "npr_agc_regular_module_function_unique_bodies": outcome,
                }
                zero_rows.append(row)
                if outcome > 0:
                    fixed_rows.append(row)

        for control in TARGET_REPOSITORIES:
            for month, outcome in [("2025-01", 1), ("2025-04", 3), ("2025-06", 6), ("2025-07", 1)]:
                row = {
                    "dataset_source": "control",
                    "repo_name": control,
                    "time": month,
                    "event": "",
                    "npr_agc_regular_module_function_unique_bodies": outcome,
                }
                zero_rows.append(row)
                fixed_rows.append(row)

        pd.DataFrame(zero_rows).to_csv(zero_path, index=False)
        pd.DataFrame(fixed_rows).to_csv(fixed_path, index=False)
        pd.DataFrame(
            [
                {
                    "dataset_source": "control",
                    "repo_name": repo,
                    "time": month,
                    "baseline_outcome": 1,
                    "method_increment": EXPECTED_SPIKE_INCREMENTS[(repo, month)],
                    "one_repo_outcome": 1 + EXPECTED_SPIKE_INCREMENTS[(repo, month)],
                }
                for repo, months in DEFAULT_SPIKE_MONTHS.items()
                for month in months
            ]
        ).to_csv(audit_path, index=False)
        pd.DataFrame(
            [
                {
                    "treatment_repo": treatment,
                    "control_repo": control,
                    "control_rank": rank,
                }
                for rank, treatment in enumerate(treatments, start=1)
                for control in TARGET_REPOSITORIES
            ]
        ).to_csv(pairs_path, index=False)
        pd.DataFrame(
            {
                "repo_name": treatments,
                "event_month": ["2025-03", "2025-05"],
            }
        ).to_csv(meta_path, index=False)

        args = argparse.Namespace(
            target_repositories="|".join(TARGET_REPOSITORIES),
            minimum_event_time=-6,
            maximum_event_time=6,
            skip_frozen_count_checks=False,
        )
        results = run_analysis(
            Paths(
                fixed_panel=fixed_path,
                zero_panel=zero_path,
                month_audit=audit_path,
                matched_pairs=pairs_path,
                treatment_meta=meta_path,
                output_dir=out_dir,
            ),
            args,
        )
        assert len(results["alignment"]) == 10
        assert (out_dir / f"{OUTPUT_PREFIX}_validation.csv").exists()
        shutil.rmtree(out_dir)
    print("Self-test: PASS")


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return 0

    required = {
        "fixed_panel": args.fixed_panel,
        "zero_panel": args.zero_panel,
        "month_audit": args.month_audit,
        "matched_pairs": args.matched_pairs,
        "treatment_meta": args.treatment_meta,
        "output_dir": args.output_dir,
    }
    missing_args = [name for name, value in required.items() if value is None]
    if missing_args:
        raise ValueError("Missing required arguments: " + ", ".join(missing_args))

    run_analysis(
        Paths(
            fixed_panel=args.fixed_panel,
            zero_panel=args.zero_panel,
            month_audit=args.month_audit,
            matched_pairs=args.matched_pairs,
            treatment_meta=args.treatment_meta,
            output_dir=args.output_dir,
        ),
        args,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
