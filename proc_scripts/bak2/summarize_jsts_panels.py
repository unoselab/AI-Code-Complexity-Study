#!/usr/bin/env python3
"""
Summarize final JS/TS matched DiD panel files.

This script creates a compact QC table for panel outputs:
- main unbalanced
- main window-completed
- strict 1:3 unbalanced
- strict 1:3 window-completed
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_PANELS = {
    "main_unbalanced": "tmp_jsts_test/data/jsts_did_final/panel_event_monthly_matched_final_clean.csv",
    "main_window_completed": "tmp_jsts_test/data/jsts_did_final/panel_event_monthly_matched_final_clean_balanced.csv",
    "strict_1to3_unbalanced": "tmp_jsts_test/data/jsts_did_final/panel_event_monthly_matched_final_clean_1to3_only.csv",
    "strict_1to3_window_completed": "tmp_jsts_test/data/jsts_did_final/panel_event_monthly_matched_final_clean_1to3_only_balanced.csv",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize JS/TS matched DiD panel outputs."
    )
    parser.add_argument(
        "--output",
        default="tmp_jsts_test/data/jsts_did_final/panel_qc_summary.csv",
        help="Output CSV path for the panel QC summary.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Allow missing panel files and mark them as missing instead of failing.",
    )
    return parser.parse_args()


def summarize_panel(panel_name: str, path: Path, allow_missing: bool) -> dict:
    if not path.exists():
        if allow_missing:
            return {
                "panel": panel_name,
                "path": str(path),
                "exists": False,
                "rows": 0,
                "repos": 0,
                "treated_repos": 0,
                "control_repos": 0,
                "min_time": None,
                "max_time": None,
                "treated_rows": 0,
                "control_rows": 0,
                "post_rows": 0,
                "control_rows_without_provenance": None,
            }
        raise SystemExit(f"ERROR: panel file not found: {path}")

    df = pd.read_csv(path)

    required = {"repo_name", "time", "ever_treated", "dataset_source", "post_event"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"ERROR: {path} missing columns: {sorted(missing)}")

    control_rows_without_provenance = None
    if "matched_as_control" in df.columns:
        controls = df[df["ever_treated"] == 0]
        control_rows_without_provenance = int(
            (controls["matched_as_control"] == 0).sum()
        )

    return {
        "panel": panel_name,
        "path": str(path),
        "exists": True,
        "rows": len(df),
        "repos": df["repo_name"].nunique(),
        "treated_repos": df.loc[df["ever_treated"] == 1, "repo_name"].nunique(),
        "control_repos": df.loc[df["ever_treated"] == 0, "repo_name"].nunique(),
        "min_time": df["time"].min(),
        "max_time": df["time"].max(),
        "treated_rows": int((df["dataset_source"] == "treatment").sum()),
        "control_rows": int((df["dataset_source"] == "control").sum()),
        "post_rows": int(df["post_event"].sum()),
        "control_rows_without_provenance": control_rows_without_provenance,
    }


def main() -> int:
    args = parse_args()

    rows = []
    for panel_name, path_text in DEFAULT_PANELS.items():
        rows.append(
            summarize_panel(
                panel_name=panel_name,
                path=Path(path_text),
                allow_missing=args.allow_missing,
            )
        )

    summary = pd.DataFrame(rows)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out, index=False)

    print(summary.to_string(index=False))
    print()
    print("Saved:", out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
