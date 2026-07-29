#!/usr/bin/env python3
"""Analyze repository-month class-method additions for two influential controls.

This script reads the fixed-sample repository-month audit produced by run-py-7p
and focuses on:
  - pieces-app/cli-agent
  - HelpingAI/Webscout

It quantifies monthly spikes, concentration, method-to-baseline ratios, and the
associated one-repository-at-a-time static DiD changes from run-py-7p.

The analysis is diagnostic only. It does not remove repositories or estimate a
new causal effect.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

DEFAULT_TARGET_REPOSITORIES = (
    "pieces-app/cli-agent",
    "HelpingAI/Webscout",
)

EXPECTED_METHOD_TOTALS = {
    "pieces-app/cli-agent": 60,
    "HelpingAI/Webscout": 80,
}

EXPECTED_MODEL_ROWS = {
    "pieces-app/cli-agent": 8,
    "HelpingAI/Webscout": 9,
}

REQUIRED_AUDIT_COLUMNS = {
    "dataset_source",
    "repo_name",
    "time",
    "event",
    "time_to_event",
    "baseline_outcome",
    "method_increment",
    "one_repo_outcome",
    "ncloc",
}

REQUIRED_COMPARISON_COLUMNS = {
    "added_repo_name",
    "estimate",
    "std_error",
    "conf_low",
    "conf_high",
    "delta_estimate",
    "delta_std_error",
    "lower_bound_drop",
    "lower_bound_drop_estimate_component",
    "lower_bound_drop_se_component",
    "changes_positive_baseline_ci_to_include_zero",
    "influence_channel",
}

OUTPUT_PREFIX = "cliagent_webscout_classmethod_months"


@dataclass(frozen=True)
class Paths:
    audit_csv: Path
    comparison_csv: Path
    output_dir: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze monthly class-method additions for pieces-app/cli-agent "
            "and HelpingAI/Webscout using run-py-7p outputs."
        )
    )
    parser.add_argument("--audit-csv", type=Path)
    parser.add_argument("--comparison-csv", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--target-repositories",
        default="|".join(DEFAULT_TARGET_REPOSITORIES),
        help="Pipe-delimited repository names.",
    )
    parser.add_argument(
        "--skip-frozen-count-checks",
        action="store_true",
        help="Skip expected row and method-total checks.",
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


def normalize_bool(value: object) -> bool:
    text = str(value).strip().lower()
    if text in {"true", "t", "1", "1.0"}:
        return True
    if text in {"false", "f", "0", "0.0", "nan", "none", ""}:
        return False
    raise ValueError(f"Cannot interpret value as boolean: {value!r}")


def parse_targets(raw: str) -> list[str]:
    targets = [item.strip() for item in raw.split("|") if item.strip()]
    if not targets:
        raise ValueError("At least one target repository is required.")
    if len(set(targets)) != len(targets):
        raise ValueError("Target repository list contains duplicates.")
    return targets


def months_needed_for_share(values: pd.Series, threshold: float) -> int:
    positive = values[values > 0].sort_values(ascending=False)
    total = float(positive.sum())
    if total <= 0:
        return 0
    cumulative = positive.cumsum() / total
    return int(np.searchsorted(cumulative.to_numpy(), threshold, side="left") + 1)


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = pd.Series(np.nan, index=numerator.index, dtype="float64")
    valid = denominator > 0
    result.loc[valid] = numerator.loc[valid] / denominator.loc[valid]
    return result


def build_month_audit(audit: pd.DataFrame, targets: list[str]) -> pd.DataFrame:
    filtered = audit[audit["repo_name"].isin(targets)].copy()
    if filtered.empty:
        raise ValueError("No target repository rows were found in the audit input.")

    for column in ["baseline_outcome", "method_increment", "one_repo_outcome", "ncloc"]:
        filtered[column] = pd.to_numeric(filtered[column], errors="raise")

    filtered["time"] = filtered["time"].astype(str)
    filtered["repo_order"] = filtered["repo_name"].map(
        {repo: index + 1 for index, repo in enumerate(targets)}
    )
    filtered["method_to_baseline_ratio"] = safe_ratio(
        filtered["method_increment"], filtered["baseline_outcome"]
    )
    filtered["method_share_of_one_repo_outcome"] = safe_ratio(
        filtered["method_increment"], filtered["one_repo_outcome"]
    )
    filtered["method_increment_positive"] = filtered["method_increment"] > 0
    filtered["calendar_month_in_treatment_cohort_window"] = filtered["time"].between(
        "2024-08", "2025-03"
    )
    filtered["method_rank_within_repo"] = (
        filtered.groupby("repo_name")["method_increment"]
        .rank(method="min", ascending=False)
        .astype(int)
    )
    filtered["method_share_within_repo"] = filtered["method_increment"] / filtered.groupby(
        "repo_name"
    )["method_increment"].transform("sum")

    sorted_for_cumulative = filtered.sort_values(
        ["repo_name", "method_increment", "time"],
        ascending=[True, False, True],
    ).copy()
    sorted_for_cumulative["method_cumulative_share_rank_order"] = sorted_for_cumulative.groupby(
        "repo_name"
    )["method_share_within_repo"].cumsum()
    filtered = filtered.merge(
        sorted_for_cumulative[
            ["repo_name", "time", "method_cumulative_share_rank_order"]
        ],
        on=["repo_name", "time"],
        how="left",
        validate="one_to_one",
    )

    filtered = filtered.sort_values(["repo_order", "time"]).reset_index(drop=True)
    return filtered


def build_repo_summary(
    month_audit: pd.DataFrame,
    comparison: pd.DataFrame,
    targets: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    comparison_target = comparison[comparison["added_repo_name"].isin(targets)].copy()
    comparison_target = comparison_target.set_index("added_repo_name", drop=False)

    for repo in targets:
        repo_df = month_audit[month_audit["repo_name"] == repo].copy()
        if repo_df.empty:
            raise ValueError(f"Target repository is missing from month audit: {repo}")
        if repo not in comparison_target.index:
            raise ValueError(f"Target repository is missing from comparison input: {repo}")

        positive = repo_df[repo_df["method_increment"] > 0].copy()
        ranked = repo_df.sort_values(
            ["method_increment", "time"], ascending=[False, True]
        )
        total_method = float(repo_df["method_increment"].sum())
        total_baseline = float(repo_df["baseline_outcome"].sum())
        top_values = ranked["method_increment"].to_numpy(dtype=float)
        cmp_row = comparison_target.loc[repo]
        if isinstance(cmp_row, pd.DataFrame):
            raise ValueError(f"Comparison input has duplicate rows for repository: {repo}")

        rows.append(
            {
                "repo_name": repo,
                "dataset_source": repo_df["dataset_source"].iloc[0],
                "model_rows": len(repo_df),
                "positive_method_months": len(positive),
                "zero_method_months": int((repo_df["method_increment"] == 0).sum()),
                "baseline_outcome_total": total_baseline,
                "method_increment_total": total_method,
                "one_repo_outcome_total": float(repo_df["one_repo_outcome"].sum()),
                "method_to_baseline_total_ratio": (
                    total_method / total_baseline if total_baseline > 0 else math.nan
                ),
                "method_increment_mean": float(repo_df["method_increment"].mean()),
                "method_increment_median": float(repo_df["method_increment"].median()),
                "method_increment_std_population": float(
                    repo_df["method_increment"].std(ddof=0)
                ),
                "maximum_method_increment": float(ranked.iloc[0]["method_increment"]),
                "maximum_method_increment_time": ranked.iloc[0]["time"],
                "maximum_method_to_baseline_ratio": float(
                    repo_df["method_to_baseline_ratio"].max()
                ),
                "maximum_method_to_baseline_ratio_time": repo_df.loc[
                    repo_df["method_to_baseline_ratio"].idxmax(), "time"
                ],
                "top1_method_share": (
                    float(top_values[:1].sum() / total_method) if total_method > 0 else 0.0
                ),
                "top2_method_share": (
                    float(top_values[:2].sum() / total_method) if total_method > 0 else 0.0
                ),
                "top3_method_share": (
                    float(top_values[:3].sum() / total_method) if total_method > 0 else 0.0
                ),
                "months_needed_for_50pct": months_needed_for_share(
                    repo_df["method_increment"], 0.50
                ),
                "months_needed_for_80pct": months_needed_for_share(
                    repo_df["method_increment"], 0.80
                ),
                "months_in_treatment_cohort_window": int(
                    repo_df["calendar_month_in_treatment_cohort_window"].sum()
                ),
                "method_bodies_in_treatment_cohort_window": float(
                    repo_df.loc[
                        repo_df["calendar_month_in_treatment_cohort_window"],
                        "method_increment",
                    ].sum()
                ),
                "did_estimate": float(cmp_row["estimate"]),
                "did_std_error": float(cmp_row["std_error"]),
                "did_conf_low": float(cmp_row["conf_low"]),
                "did_conf_high": float(cmp_row["conf_high"]),
                "did_delta_estimate": float(cmp_row["delta_estimate"]),
                "did_delta_std_error": float(cmp_row["delta_std_error"]),
                "did_lower_bound_drop": float(cmp_row["lower_bound_drop"]),
                "did_lower_bound_drop_estimate_component": float(
                    cmp_row["lower_bound_drop_estimate_component"]
                ),
                "did_lower_bound_drop_se_component": float(
                    cmp_row["lower_bound_drop_se_component"]
                ),
                "did_changes_positive_ci_to_include_zero": normalize_bool(
                    cmp_row["changes_positive_baseline_ci_to_include_zero"]
                ),
                "did_influence_channel": cmp_row["influence_channel"],
            }
        )

    summary = pd.DataFrame(rows)
    summary["impact_rank_lower_bound_drop"] = summary["did_lower_bound_drop"].rank(
        method="min", ascending=False
    ).astype(int)
    summary = summary.sort_values("impact_rank_lower_bound_drop").reset_index(drop=True)
    return summary


def build_spike_ranking(month_audit: pd.DataFrame) -> pd.DataFrame:
    ranking = month_audit.copy()
    ranking["global_method_spike_rank"] = ranking["method_increment"].rank(
        method="min", ascending=False
    ).astype(int)
    ranking = ranking.sort_values(
        ["method_increment", "repo_name", "time"],
        ascending=[False, True, True],
    ).reset_index(drop=True)
    return ranking


def build_calendar_comparison(month_audit: pd.DataFrame, targets: list[str]) -> pd.DataFrame:
    fields = ["baseline_outcome", "method_increment", "one_repo_outcome"]
    pieces: list[pd.DataFrame] = []
    for repo in targets:
        repo_short = "cli_agent" if repo == "pieces-app/cli-agent" else "webscout"
        repo_df = month_audit[month_audit["repo_name"] == repo][["time", *fields]].copy()
        repo_df = repo_df.rename(
            columns={field: f"{repo_short}_{field}" for field in fields}
        )
        pieces.append(repo_df)

    calendar = pieces[0]
    for piece in pieces[1:]:
        calendar = calendar.merge(piece, on="time", how="outer", validate="one_to_one")
    calendar = calendar.sort_values("time").reset_index(drop=True)
    return calendar


def build_findings(summary: pd.DataFrame, spikes: pd.DataFrame) -> pd.DataFrame:
    largest_impact = summary.sort_values("did_lower_bound_drop", ascending=False).iloc[0]
    largest_spike = spikes.iloc[0]
    most_concentrated = summary.sort_values("top1_method_share", ascending=False).iloc[0]
    findings = [
        {
            "finding": "largest_did_lower_bound_drop_repository",
            "repo_name": largest_impact["repo_name"],
            "value": largest_impact["did_lower_bound_drop"],
            "detail": "Largest static 95% CI lower-bound decrease versus baseline.",
        },
        {
            "finding": "largest_single_month_method_spike_repository",
            "repo_name": largest_spike["repo_name"],
            "value": largest_spike["method_increment"],
            "detail": f"Calendar month {largest_spike['time']}.",
        },
        {
            "finding": "highest_top1_month_concentration_repository",
            "repo_name": most_concentrated["repo_name"],
            "value": most_concentrated["top1_method_share"],
            "detail": "Share of repository method additions in its largest month.",
        },
    ]
    return pd.DataFrame(findings)


def build_validation(
    month_audit: pd.DataFrame,
    summary: pd.DataFrame,
    targets: list[str],
    skip_frozen_count_checks: bool,
) -> pd.DataFrame:
    duplicate_repo_months = int(month_audit.duplicated(["repo_name", "time"]).sum())
    arithmetic_error = float(
        (
            month_audit["one_repo_outcome"]
            - month_audit["baseline_outcome"]
            - month_audit["method_increment"]
        )
        .abs()
        .max()
    )

    observed_totals = summary.set_index("repo_name")["method_increment_total"].to_dict()
    observed_rows = summary.set_index("repo_name")["model_rows"].to_dict()
    frozen_totals_match = all(
        math.isclose(
            float(observed_totals.get(repo, math.nan)),
            float(EXPECTED_METHOD_TOTALS[repo]),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for repo in targets
    )
    frozen_rows_match = all(
        int(observed_rows.get(repo, -1)) == EXPECTED_MODEL_ROWS[repo]
        for repo in targets
    )

    checks = [
        ("target_repository_count", len(summary), len(summary) == len(targets)),
        (
            "target_repositories_all_present",
            len(set(targets) - set(month_audit["repo_name"])),
            set(targets).issubset(set(month_audit["repo_name"])),
        ),
        (
            "target_repositories_are_controls",
            int((month_audit["dataset_source"] != "control").sum()),
            bool((month_audit["dataset_source"] == "control").all()),
        ),
        ("duplicate_repo_month_rows", duplicate_repo_months, duplicate_repo_months == 0),
        (
            "baseline_outcome_strictly_positive",
            int((month_audit["baseline_outcome"] <= 0).sum()),
            bool((month_audit["baseline_outcome"] > 0).all()),
        ),
        (
            "method_increment_nonnegative",
            int((month_audit["method_increment"] < 0).sum()),
            bool((month_audit["method_increment"] >= 0).all()),
        ),
        (
            "one_repo_outcome_arithmetic_max_abs_error",
            arithmetic_error,
            arithmetic_error <= 1e-12,
        ),
        (
            "comparison_ci_flip_present_for_both",
            int(summary["did_changes_positive_ci_to_include_zero"].sum()),
            bool(summary["did_changes_positive_ci_to_include_zero"].all()),
        ),
        (
            "frozen_method_totals_match",
            int(frozen_totals_match),
            skip_frozen_count_checks or frozen_totals_match,
        ),
        (
            "frozen_model_rows_match",
            int(frozen_rows_match),
            skip_frozen_count_checks or frozen_rows_match,
        ),
    ]
    return pd.DataFrame(checks, columns=["check", "value", "passed"])


def write_outputs(
    paths: Paths,
    month_audit: pd.DataFrame,
    summary: pd.DataFrame,
    spikes: pd.DataFrame,
    calendar: pd.DataFrame,
    findings: pd.DataFrame,
    validation: pd.DataFrame,
    targets: list[str],
) -> None:
    paths.output_dir.mkdir(parents=True, exist_ok=True)

    output_files = {
        "repo_month_audit": paths.output_dir / f"{OUTPUT_PREFIX}_repo_month_audit.csv",
        "repo_summary": paths.output_dir / f"{OUTPUT_PREFIX}_repo_summary.csv",
        "month_spike_ranking": paths.output_dir / f"{OUTPUT_PREFIX}_month_spike_ranking.csv",
        "calendar_month_comparison": paths.output_dir
        / f"{OUTPUT_PREFIX}_calendar_month_comparison.csv",
        "diagnostic_findings": paths.output_dir / f"{OUTPUT_PREFIX}_diagnostic_findings.csv",
        "validation": paths.output_dir / f"{OUTPUT_PREFIX}_validation.csv",
        "metadata": paths.output_dir / f"{OUTPUT_PREFIX}_metadata.json",
        "status": paths.output_dir / f"{OUTPUT_PREFIX}_status.txt",
    }

    month_audit.to_csv(output_files["repo_month_audit"], index=False)
    summary.to_csv(output_files["repo_summary"], index=False)
    spikes.to_csv(output_files["month_spike_ranking"], index=False)
    calendar.to_csv(output_files["calendar_month_comparison"], index=False)
    findings.to_csv(output_files["diagnostic_findings"], index=False)
    validation.to_csv(output_files["validation"], index=False)

    metadata = {
        "analysis": "run-py-8a repository-month class-method spike diagnosis",
        "target_repositories": targets,
        "audit_csv": str(paths.audit_csv),
        "comparison_csv": str(paths.comparison_csv),
        "output_dir": str(paths.output_dir),
        "interpretation": "supplementary fixed-sample influence debugging",
        "causal_interpretation_allowed": False,
        "repository_removal_justified": False,
    }
    output_files["metadata"].write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    failed = validation.loc[~validation["passed"].astype(bool)]
    status_lines = [
        f"status={'PASS' if failed.empty else 'FAIL'}",
        f"target_repository_count={len(targets)}",
        f"repo_month_rows={len(month_audit)}",
        f"failed_checks={len(failed)}",
        "causal_interpretation_allowed=FALSE",
        "repository_removal_justified=FALSE",
    ]
    output_files["status"].write_text("\n".join(status_lines) + "\n", encoding="utf-8")

    if not failed.empty:
        raise RuntimeError(
            "Validation failed: " + ", ".join(failed["check"].astype(str).tolist())
        )


def run_analysis(
    paths: Paths,
    targets: list[str],
    skip_frozen_count_checks: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    for path in (paths.audit_csv, paths.comparison_csv):
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"Required input is missing or empty: {path}")

    audit = pd.read_csv(paths.audit_csv)
    comparison = pd.read_csv(paths.comparison_csv)
    require_columns(audit, REQUIRED_AUDIT_COLUMNS, "Target repository-month audit")
    require_columns(comparison, REQUIRED_COMPARISON_COLUMNS, "Comparison-to-baseline input")

    month_audit = build_month_audit(audit, targets)
    summary = build_repo_summary(month_audit, comparison, targets)
    spikes = build_spike_ranking(month_audit)
    calendar = build_calendar_comparison(month_audit, targets)
    findings = build_findings(summary, spikes)
    validation = build_validation(
        month_audit,
        summary,
        targets,
        skip_frozen_count_checks,
    )
    write_outputs(
        paths,
        month_audit,
        summary,
        spikes,
        calendar,
        findings,
        validation,
        targets,
    )
    return summary, spikes, validation


def synthetic_inputs(root: Path) -> Paths:
    audit_rows: list[dict[str, object]] = []
    synthetic = {
        "pieces-app/cli-agent": [0, 5, 10, 20, 15, 5, 5, 0],
        "HelpingAI/Webscout": [0, 0, 5, 10, 15, 20, 20, 10, 0],
    }
    for repo, increments in synthetic.items():
        for index, increment in enumerate(increments):
            month = pd.Period("2024-07", freq="M") + index
            baseline = index % 5 + 1
            audit_rows.append(
                {
                    "requested_order": 1,
                    "dataset_source": "control",
                    "repo_name": repo,
                    "time": str(month),
                    "event": "",
                    "time_to_event": np.nan,
                    "baseline_outcome": baseline,
                    "method_increment": increment,
                    "one_repo_outcome": baseline + increment,
                    "ncloc": 1000 + index,
                }
            )
    audit = pd.DataFrame(audit_rows)
    comparison = pd.DataFrame(
        [
            {
                "added_repo_name": "pieces-app/cli-agent",
                "estimate": 0.98,
                "std_error": 1.64,
                "conf_low": -2.23,
                "conf_high": 4.20,
                "delta_estimate": -1.63,
                "delta_std_error": 0.51,
                "lower_bound_drop": 2.63,
                "lower_bound_drop_estimate_component": 1.63,
                "lower_bound_drop_se_component": 1.00,
                "changes_positive_baseline_ci_to_include_zero": True,
                "influence_channel": "estimate_drop_and_se_increase",
            },
            {
                "added_repo_name": "HelpingAI/Webscout",
                "estimate": 1.42,
                "std_error": 1.66,
                "conf_low": -1.84,
                "conf_high": 4.67,
                "delta_estimate": -1.19,
                "delta_std_error": 0.53,
                "lower_bound_drop": 2.24,
                "lower_bound_drop_estimate_component": 1.19,
                "lower_bound_drop_se_component": 1.05,
                "changes_positive_baseline_ci_to_include_zero": True,
                "influence_channel": "estimate_drop_and_se_increase",
            },
        ]
    )

    audit_path = root / "audit.csv"
    comparison_path = root / "comparison.csv"
    output_dir = root / "output"
    audit.to_csv(audit_path, index=False)
    comparison.to_csv(comparison_path, index=False)
    return Paths(audit_path, comparison_path, output_dir)


def run_self_test() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="run-py-8a-self-test-"))
    try:
        paths = synthetic_inputs(temp_root)
        summary, spikes, validation = run_analysis(
            paths,
            list(DEFAULT_TARGET_REPOSITORIES),
            skip_frozen_count_checks=False,
        )
        assert len(summary) == 2
        assert len(spikes) == 17
        assert validation["passed"].astype(bool).all()
        assert (paths.output_dir / f"{OUTPUT_PREFIX}_status.txt").is_file()
        print("Self-test: PASS")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return 0

    if args.audit_csv is None or args.comparison_csv is None or args.output_dir is None:
        raise ValueError(
            "--audit-csv, --comparison-csv, and --output-dir are required "
            "unless --self-test is used."
        )

    targets = parse_targets(args.target_repositories)
    paths = Paths(
        audit_csv=args.audit_csv.resolve(),
        comparison_csv=args.comparison_csv.resolve(),
        output_dir=args.output_dir.resolve(),
    )
    summary, spikes, validation = run_analysis(
        paths,
        targets,
        args.skip_frozen_count_checks,
    )

    print("=" * 80)
    print("run-py-8a: cli-agent and Webscout class-method month diagnosis")
    print("=" * 80)
    print("Status: PASS")
    print(f"Target repositories: {len(summary)}")
    print(f"Repository-month rows: {len(spikes)}")
    print(f"Failed checks: {(~validation['passed'].astype(bool)).sum()}")
    print()
    print("Repository summary:")
    display_columns = [
        "repo_name",
        "model_rows",
        "method_increment_total",
        "maximum_method_increment",
        "maximum_method_increment_time",
        "top1_method_share",
        "top3_method_share",
        "did_lower_bound_drop",
    ]
    print(summary[display_columns].to_string(index=False))
    print()
    print("Top five month spikes:")
    print(
        spikes[
            [
                "repo_name",
                "time",
                "baseline_outcome",
                "method_increment",
                "one_repo_outcome",
                "method_to_baseline_ratio",
            ]
        ]
        .head(5)
        .to_string(index=False)
    )
    print(f"Output directory: {paths.output_dir}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
