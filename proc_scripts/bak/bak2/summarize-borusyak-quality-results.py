#!/usr/bin/env python3
"""Summarize Borusyak quality DiD outputs for reporting."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize Borusyak quality DiD outputs."
    )
    parser.add_argument("--static-effects", required=True)
    parser.add_argument("--dynamic-effects", required=True)
    parser.add_argument("--panel-checks", required=True)
    parser.add_argument("--output-summary", required=True)
    parser.add_argument("--output-static", required=True)
    parser.add_argument("--output-dynamic-summary", required=True)
    return parser.parse_args()


def pct_change(beta: float) -> float:
    return (np.exp(beta) - 1.0) * 100.0


def main() -> None:
    args = parse_args()

    static_df = pd.read_csv(args.static_effects)
    dynamic_df = pd.read_csv(args.dynamic_effects)
    panel_checks = pd.read_csv(args.panel_checks)

    static_df["percent_change"] = pct_change(static_df["estimate"])
    static_df["percent_change_ci_low"] = pct_change(static_df["conf_low"])
    static_df["percent_change_ci_high"] = pct_change(static_df["conf_high"])
    static_df["static_significant"] = (
        (static_df["conf_low"] > 0) | (static_df["conf_high"] < 0)
    )

    dynamic_rows = []
    for (outcome, label), g in dynamic_df.groupby(["outcome", "outcome_label"]):
        pre = g[g["time"].between(-6, -2)]
        post = g[g["time"].between(0, 6)]

        dynamic_rows.append(
            {
                "outcome": outcome,
                "outcome_label": label,
                "pre_period_rows": len(pre),
                "pre_significant_count": int(pre["significant"].sum()),
                "post_period_rows": len(post),
                "post_significant_count": int(post["significant"].sum()),
                "post_mean_estimate": post["estimate"].mean(),
                "post_mean_percent_change": pct_change(post["estimate"].mean()),
                "pretrend_warning": int(pre["significant"].sum() > 0),
            }
        )

    dynamic_summary = pd.DataFrame(dynamic_rows)

    summary_rows = []

    def get_check(name: str):
        row = panel_checks[panel_checks["check"] == name]
        return row["value"].iloc[0] if len(row) else None

    summary_rows.append({"check": "rows", "value": get_check("rows")})
    summary_rows.append({"check": "treated_repos", "value": get_check("treated_repos")})
    summary_rows.append({"check": "control_repos", "value": get_check("control_repos")})
    summary_rows.append({"check": "source_less_commit_rows", "value": get_check("source_less_commit_rows")})
    summary_rows.append({"check": "raw_metric_missing_rows", "value": get_check("raw_metric_missing_rows")})
    summary_rows.append({"check": "static_outcomes", "value": len(static_df)})
    summary_rows.append({"check": "dynamic_outcomes", "value": dynamic_df["outcome"].nunique()})
    summary_rows.append({"check": "outcomes_with_pretrend_warning", "value": int(dynamic_summary["pretrend_warning"].sum())})

    report_summary = pd.DataFrame(summary_rows)

    Path(args.output_summary).parent.mkdir(parents=True, exist_ok=True)
    report_summary.to_csv(args.output_summary, index=False)
    static_df.to_csv(args.output_static, index=False)
    dynamic_summary.to_csv(args.output_dynamic_summary, index=False)

    print("Panel/report summary")
    print(report_summary.to_string(index=False))
    print()
    print("Static effects with percent changes")
    print(static_df.to_string(index=False))
    print()
    print("Dynamic/pretrend summary")
    print(dynamic_summary.to_string(index=False))


if __name__ == "__main__":
    main()
