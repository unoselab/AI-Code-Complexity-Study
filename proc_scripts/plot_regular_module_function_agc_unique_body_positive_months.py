#!/usr/bin/env python3
"""Create a paper-style Borusyak event-study plot from a dynamic-effects CSV.

The default use case is the run-py-7h positive-outcome-month sensitivity
analysis. The plot mirrors the visual grammar used by the MSR paper and the
project R Markdown analyses:

- event time on the x-axis;
- treatment-effect estimate on the y-axis;
- 95% confidence intervals;
- filled markers when the confidence interval excludes zero;
- hollow markers when the confidence interval includes zero;
- a horizontal zero-effect line;
- a vertical adoption boundary at event time -0.5.

This script only visualizes model output. It does not estimate the DiD model.
"""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


SCRIPT_VERSION = "run-py-7i"

REQUIRED_COLUMNS = [
    "time",
    "estimate",
    "conf_low",
    "conf_high",
]

EXPECTED_EVENT_TIMES = [-6, -5, -4, -3, -2, 0, 1, 2, 3, 4, 5, 6]

DEFAULT_TITLE = "AGC-Like Regular-Function Unique Bodies"
DEFAULT_SUBTITLE = "Positive-outcome repository-months only"
DEFAULT_CAPTION = (
    "Filled dots: 95% CI excludes 0 (significant). "
    "Hollow dots: 95% CI includes 0 (non-significant). "
    "Supplementary selected-sample sensitivity analysis."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot paper-style dynamic Borusyak treatment effects."
    )
    parser.add_argument(
        "--input-file",
        default=None,
        help="Dynamic-effects CSV produced by run-py-7h.",
    )
    parser.add_argument(
        "--output-pdf",
        default=None,
        help="Output PDF path.",
    )
    parser.add_argument(
        "--output-png",
        default=None,
        help="Output PNG path.",
    )
    parser.add_argument(
        "--title",
        default=DEFAULT_TITLE,
        help="Figure title.",
    )
    parser.add_argument(
        "--subtitle",
        default=DEFAULT_SUBTITLE,
        help="Figure subtitle shown below the title.",
    )
    parser.add_argument(
        "--caption",
        default=DEFAULT_CAPTION,
        help="Figure caption shown below the x-axis label.",
    )
    parser.add_argument(
        "--x-label",
        default="Months Relative to Cursor Adoption",
        help="X-axis label.",
    )
    parser.add_argument(
        "--y-label",
        default="Treatment Effect",
        help="Y-axis label.",
    )
    parser.add_argument(
        "--width",
        type=float,
        default=6.8,
        help="Figure width in inches.",
    )
    parser.add_argument(
        "--height",
        type=float,
        default=3.8,
        help="Figure height in inches.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="PNG resolution in dots per inch.",
    )
    parser.add_argument(
        "--strict-event-times",
        action="store_true",
        help="Require exactly event times -6:-2 and 0:6, with -1 omitted.",
    )
    parser.add_argument(
        "--overwrite-output",
        action="store_true",
        help="Overwrite existing output files.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run an internal synthetic-data test and exit.",
    )
    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(f"{label} not found or empty: {path}")


def require_output_target(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Output exists and --overwrite-output was not provided: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)


def parse_bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)

    normalized = series.astype(str).str.strip().str.lower()
    mapping = {
        "true": True,
        "t": True,
        "1": True,
        "yes": True,
        "y": True,
        "false": False,
        "f": False,
        "0": False,
        "no": False,
        "n": False,
    }
    unexpected = sorted(set(normalized.dropna()) - set(mapping))
    if unexpected:
        raise ValueError(
            "significant contains unsupported values: " + ", ".join(unexpected)
        )
    return normalized.map(mapping).astype(bool)


def load_dynamic_effects(path: Path, strict_event_times: bool) -> pd.DataFrame:
    require_file(path, "Dynamic-effects CSV")
    data = pd.read_csv(path, low_memory=False)

    missing = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"Dynamic-effects CSV is missing columns: {missing}")
    if data.empty:
        raise ValueError("Dynamic-effects CSV has no rows.")

    data = data.copy()
    for column in REQUIRED_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    if data[REQUIRED_COLUMNS].isna().any().any():
        bad_rows = data.loc[data[REQUIRED_COLUMNS].isna().any(axis=1), REQUIRED_COLUMNS]
        raise ValueError(
            "Dynamic-effects CSV contains missing or nonnumeric required values:\n"
            + bad_rows.to_string(index=False)
        )

    if not (data["time"] % 1 == 0).all():
        raise ValueError("time must contain integer event months.")
    data["time"] = data["time"].astype(int)

    if data["time"].duplicated().any():
        duplicated = sorted(data.loc[data["time"].duplicated(False), "time"].unique())
        raise ValueError(f"Duplicate event times found: {duplicated}")

    if (data["conf_low"] > data["estimate"]).any():
        raise ValueError("At least one conf_low value exceeds estimate.")
    if (data["conf_high"] < data["estimate"]).any():
        raise ValueError("At least one conf_high value is below estimate.")
    if (data["conf_low"] > data["conf_high"]).any():
        raise ValueError("At least one confidence interval is reversed.")

    data["significant_from_ci"] = (
        (data["conf_low"] > 0) | (data["conf_high"] < 0)
    )

    if "significant" in data.columns:
        reported = parse_bool_series(data["significant"])
        mismatch = reported.ne(data["significant_from_ci"])
        if mismatch.any():
            mismatch_rows = data.loc[
                mismatch,
                ["time", "estimate", "conf_low", "conf_high", "significant"],
            ]
            raise ValueError(
                "Reported significant values disagree with confidence intervals:\n"
                + mismatch_rows.to_string(index=False)
            )

    data["significant"] = data["significant_from_ci"]
    data = data.sort_values("time").reset_index(drop=True)

    if strict_event_times:
        observed = data["time"].tolist()
        if observed != EXPECTED_EVENT_TIMES:
            raise ValueError(
                "Unexpected event-time sequence. "
                f"Expected {EXPECTED_EVENT_TIMES}, observed {observed}."
            )

    if -1 in set(data["time"]):
        raise ValueError(
            "Event time -1 should be the omitted reference period and must not be plotted."
        )

    return data


def compute_y_limits(data: pd.DataFrame) -> tuple[float, float]:
    lower = float(min(data["conf_low"].min(), 0.0))
    upper = float(max(data["conf_high"].max(), 0.0))
    span = upper - lower
    if not math.isfinite(span) or span <= 0:
        span = 1.0
    padding = span * 0.08
    return lower - padding, upper + padding


def draw_error_bar(
    ax: plt.Axes,
    x: float,
    estimate: float,
    conf_low: float,
    conf_high: float,
    significant: bool,
) -> None:
    line_style = "-" if significant else ":"
    marker_face = "black" if significant else "white"

    ax.vlines(
        x,
        conf_low,
        conf_high,
        color="black",
        linewidth=1.1,
        linestyles=line_style,
        zorder=2,
    )
    cap_width = 0.18
    ax.hlines(
        [conf_low, conf_high],
        x - cap_width,
        x + cap_width,
        color="black",
        linewidth=1.0,
        linestyles=line_style,
        zorder=2,
    )
    ax.scatter(
        [x],
        [estimate],
        marker="o",
        s=35,
        facecolors=marker_face,
        edgecolors="black",
        linewidths=1.0,
        zorder=3,
    )


def create_plot(
    data: pd.DataFrame,
    output_pdf: Path,
    output_png: Path,
    title: str,
    subtitle: str,
    caption: str,
    x_label: str,
    y_label: str,
    width: float,
    height: float,
    dpi: int,
    overwrite: bool,
) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("Figure width and height must be positive.")
    if dpi <= 0:
        raise ValueError("DPI must be positive.")

    require_output_target(output_pdf, overwrite)
    require_output_target(output_png, overwrite)

    fig, ax = plt.subplots(figsize=(width, height))

    for row in data.itertuples(index=False):
        draw_error_bar(
            ax=ax,
            x=float(row.time),
            estimate=float(row.estimate),
            conf_low=float(row.conf_low),
            conf_high=float(row.conf_high),
            significant=bool(row.significant),
        )

    ax.axhline(0, color="black", linestyle="--", linewidth=1.0, zorder=1)
    ax.axvline(-0.5, color="black", linestyle="--", linewidth=1.0, zorder=1)

    ax.set_xlim(-6.5, 6.5)
    ax.set_xticks(range(-6, 7))
    ax.set_ylim(*compute_y_limits(data))
    ax.set_xlabel(x_label, fontsize=10)
    ax.set_ylabel(y_label, fontsize=10)

    title_text = title.strip()
    if subtitle.strip():
        title_text += "\n" + subtitle.strip()
    ax.set_title(title_text, fontsize=11, pad=10)

    ax.grid(axis="y", color="0.87", linewidth=0.7)
    ax.grid(axis="x", color="0.93", linewidth=0.6)
    ax.set_axisbelow(True)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=9)

    fig.text(
        0.5,
        0.012,
        caption,
        ha="center",
        va="bottom",
        fontsize=8,
        wrap=True,
    )
    fig.tight_layout(rect=(0.02, 0.095, 0.99, 0.98))

    fig.savefig(output_pdf, bbox_inches="tight")
    fig.savefig(output_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def run_self_test() -> None:
    synthetic = pd.DataFrame(
        {
            "time": EXPECTED_EVENT_TIMES,
            "estimate": [
                0.70,
                -1.81,
                -2.58,
                3.92,
                -0.43,
                4.76,
                3.69,
                -0.10,
                1.93,
                2.89,
                1.74,
                1.60,
            ],
            "conf_low": [
                -2.73,
                -4.30,
                -5.68,
                -1.80,
                -2.46,
                1.79,
                1.11,
                -2.61,
                -4.95,
                -0.84,
                -1.66,
                -0.47,
            ],
            "conf_high": [
                4.13,
                0.68,
                0.52,
                9.65,
                1.61,
                7.72,
                6.26,
                2.41,
                8.81,
                6.62,
                5.14,
                3.66,
            ],
            "significant": [
                False,
                False,
                False,
                False,
                False,
                True,
                True,
                False,
                False,
                False,
                False,
                False,
            ],
        }
    )

    with tempfile.TemporaryDirectory(prefix="run-py-7i-self-test-") as tmp_dir:
        tmp = Path(tmp_dir)
        input_path = tmp / "dynamic.csv"
        pdf_path = tmp / "plot.pdf"
        png_path = tmp / "plot.png"
        synthetic.to_csv(input_path, index=False)

        loaded = load_dynamic_effects(input_path, strict_event_times=True)
        create_plot(
            data=loaded,
            output_pdf=pdf_path,
            output_png=png_path,
            title=DEFAULT_TITLE,
            subtitle=DEFAULT_SUBTITLE,
            caption=DEFAULT_CAPTION,
            x_label="Months Relative to Cursor Adoption",
            y_label="Treatment Effect",
            width=6.8,
            height=3.8,
            dpi=150,
            overwrite=False,
        )

        require_file(pdf_path, "Self-test PDF")
        require_file(png_path, "Self-test PNG")

    print("Self-test: PASS")


def main() -> int:
    args = parse_args()

    if args.self_test:
        run_self_test()
        return 0

    missing_args = [
        name
        for name, value in (
            ("--input-file", args.input_file),
            ("--output-pdf", args.output_pdf),
            ("--output-png", args.output_png),
        )
        if not value
    ]
    if missing_args:
        raise ValueError(
            "Required arguments are missing: " + ", ".join(missing_args)
        )

    input_path = Path(args.input_file)
    output_pdf = Path(args.output_pdf)
    output_png = Path(args.output_png)

    data = load_dynamic_effects(
        input_path,
        strict_event_times=args.strict_event_times,
    )
    create_plot(
        data=data,
        output_pdf=output_pdf,
        output_png=output_png,
        title=args.title,
        subtitle=args.subtitle,
        caption=args.caption,
        x_label=args.x_label,
        y_label=args.y_label,
        width=args.width,
        height=args.height,
        dpi=args.dpi,
        overwrite=args.overwrite_output,
    )

    significant_times = data.loc[data["significant"], "time"].tolist()
    print("=" * 80)
    print("run-py-7i: paper-style dynamic-effects plot")
    print("=" * 80)
    print(f"Script version:       {SCRIPT_VERSION}")
    print(f"Input rows:           {len(data)}")
    print(f"Event times:          {data['time'].tolist()}")
    print(f"Significant times:    {significant_times}")
    print(f"Output PDF:           {output_pdf}")
    print(f"Output PNG:           {output_png}")
    print("Status:               PASS")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
