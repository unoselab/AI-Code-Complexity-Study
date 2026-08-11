#!/usr/bin/env python3
"""Create the weekly Python-velocity DiD figure for Adjusted and FE-only models.

Input
-----
velocity_python_added_lines_weekly_v4_dynamic_effects.csv

Output
------
fig_did_velocity_python_weekly-v4.pdf
fig_did_velocity_python_weekly-v4.png

The input must contain exactly one calendar. The v4 experiment uses Chicago for
its manuscript figure; the previously completed New York/Chicago timing audit
is reported separately in the paper text.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt

IMPLEMENTATION_VERSION = "v4"
PRIMARY_OUTCOME = "log_lines_added_py_source"
EXPECTED_CALENDAR = "chicago"
EXPECTED_TIMEZONE = "America/Chicago"
EXPECTED_EVENTS = list(range(-12, -1)) + list(range(0, 13))
EXPECTED_SPECS = {
    "adjusted": {
        "label": "Adjusted",
        "formula": "~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index",
    },
    "fe_only": {
        "label": "FE-only",
        "formula": "~ 1 | repo_id + time_index",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the weekly Adjusted-vs-FE-only Python velocity event-study figure."
    )
    parser.add_argument(
        "input_csv",
        type=Path,
        help="Path to velocity_python_added_lines_weekly_v4_dynamic_effects.csv",
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=Path("fig_did_velocity_python_weekly-v4"),
        help="Output prefix for PDF and PNG files.",
    )
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "spec_key",
            "spec_label",
            "outcome",
            "event_time",
            "estimate",
            "conf.low",
            "conf.high",
            "calendar_key",
            "analysis_timezone",
            "first_stage_formula",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Input CSV is missing required columns: {sorted(missing)}")

        for row in reader:
            if row["outcome"] != PRIMARY_OUTCOME:
                continue
            if row["spec_key"] not in EXPECTED_SPECS:
                continue
            rows.append(
                {
                    "spec_key": row["spec_key"],
                    "spec_label": row["spec_label"],
                    "event_time": int(row["event_time"]),
                    "estimate": float(row["estimate"]),
                    "conf_low": float(row["conf.low"]),
                    "conf_high": float(row["conf.high"]),
                    "calendar_key": row["calendar_key"],
                    "analysis_timezone": row["analysis_timezone"],
                    "first_stage_formula": row["first_stage_formula"],
                }
            )
    return rows


def validate_rows(rows: list[dict[str, object]]) -> None:
    expected_total = len(EXPECTED_EVENTS) * len(EXPECTED_SPECS)
    if len(rows) != expected_total:
        raise ValueError(f"Expected {expected_total} primary rows, found {len(rows)}")

    seen: set[tuple[str, int]] = set()
    for spec_key, spec_info in EXPECTED_SPECS.items():
        spec_rows = sorted(
            (row for row in rows if row["spec_key"] == spec_key),
            key=lambda row: int(row["event_time"]),
        )
        observed_events = [int(row["event_time"]) for row in spec_rows]
        if observed_events != EXPECTED_EVENTS:
            raise ValueError(
                f"Unexpected event-time support for {spec_key}: {observed_events}"
            )

        for row in spec_rows:
            event_time = int(row["event_time"])
            key = (spec_key, event_time)
            if key in seen:
                raise ValueError(f"Duplicate specification/event row: {key}")
            seen.add(key)

            if row["spec_label"] != spec_info["label"]:
                raise ValueError(
                    f"Specification label mismatch for {spec_key}: {row['spec_label']}"
                )
            if row["calendar_key"] != EXPECTED_CALENDAR:
                raise ValueError(
                    f"Expected calendar {EXPECTED_CALENDAR}, observed {row['calendar_key']}"
                )
            if row["analysis_timezone"] != EXPECTED_TIMEZONE:
                raise ValueError(
                    f"Expected timezone {EXPECTED_TIMEZONE}, observed {row['analysis_timezone']}"
                )
            if row["first_stage_formula"] != spec_info["formula"]:
                raise ValueError(
                    f"First-stage formula mismatch for {spec_key}: {row['first_stage_formula']}"
                )

            numeric_values = (
                float(row["estimate"]),
                float(row["conf_low"]),
                float(row["conf_high"]),
            )
            if not all(math.isfinite(value) for value in numeric_values):
                raise ValueError(
                    f"Non-finite result for {spec_key} at event {event_time}"
                )
            if not (
                float(row["conf_low"])
                <= float(row["estimate"])
                <= float(row["conf_high"])
            ):
                raise ValueError(
                    f"Invalid confidence interval for {spec_key} at event {event_time}"
                )


def rows_for(
    rows: list[dict[str, object]], spec_key: str
) -> list[dict[str, object]]:
    return sorted(
        [row for row in rows if row["spec_key"] == spec_key],
        key=lambda row: int(row["event_time"]),
    )


def plot_series(
    ax: plt.Axes,
    rows: list[dict[str, object]],
    marker: str,
    linestyle: str,
    offset: float,
    label: str,
) -> None:
    x = [int(row["event_time"]) + offset for row in rows]
    y = [float(row["estimate"]) for row in rows]
    lower = [float(row["estimate"]) - float(row["conf_low"]) for row in rows]
    upper = [float(row["conf_high"]) - float(row["estimate"]) for row in rows]

    ax.errorbar(
        x,
        y,
        yerr=[lower, upper],
        marker=marker,
        linestyle=linestyle,
        linewidth=1.2,
        markersize=4.5,
        capsize=2.5,
        label=label,
    )


def main() -> None:
    args = parse_args()
    if not args.input_csv.is_file():
        raise FileNotFoundError(f"Input CSV not found: {args.input_csv}")

    print(f"Implementation: {IMPLEMENTATION_VERSION}")
    print(f"Step 1: Reading weekly dynamic effects: {args.input_csv}")
    rows = read_rows(args.input_csv)
    print(f"  Selected {len(rows)} primary rows.")

    print("Step 2: Validating one calendar, two specifications, and event support.")
    validate_rows(rows)
    print("  Validation PASS: Chicago, Adjusted + FE-only, 24 event terms each.")

    print("Step 3: Creating weekly event-study figure.")
    fig, ax = plt.subplots(figsize=(7.4, 3.15))
    ax.axhline(0, linewidth=0.8, linestyle="-", color="0.35")
    ax.axvline(-0.5, linewidth=0.8, linestyle=":", color="0.35")

    plot_series(
        ax,
        rows_for(rows, "adjusted"),
        marker="o",
        linestyle="-",
        offset=-0.07,
        label="Adjusted",
    )
    plot_series(
        ax,
        rows_for(rows, "fe_only"),
        marker="s",
        linestyle="--",
        offset=0.07,
        label="FE-only",
    )

    # Event week -1 is the omitted reference period in did_imputation.
    ax.scatter([-1], [0], marker="x", s=28, color="0.2", zorder=5)

    tick_values = [-12, -10, -8, -6, -4, -2, -1, 0, 2, 4, 6, 8, 10, 12]
    ax.set_xticks(tick_values)
    ax.set_xlim(-12.7, 12.7)
    ax.set_xlabel("Event week", fontsize=9)
    ax.set_ylabel("ATT", fontsize=9)
    ax.tick_params(axis="both", labelsize=8)
    ax.grid(axis="y", linewidth=0.4, alpha=0.35)
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper right")

    fig.tight_layout()

    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    pdf_path = args.output_prefix.with_suffix(".pdf")
    png_path = args.output_prefix.with_suffix(".png")
    fig.savefig(pdf_path, bbox_inches="tight", facecolor="white")
    fig.savefig(png_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    print(f"Step 4: Wrote {pdf_path}")
    print(f"Step 5: Wrote {png_path}")
    print("Done.")


if __name__ == "__main__":
    main()
