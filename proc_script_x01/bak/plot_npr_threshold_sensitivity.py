#!/usr/bin/env python3
"""Plot a publication-style NPR threshold sensitivity figure with 95% CIs.

This script creates Figure 1(a): a coefficient sensitivity plot for the
localized quality -> future velocity dynamic-panel GMM analysis. It reads a CSV
summary table, detects the threshold and coefficient columns, derives 95%
confidence intervals from either explicit CI columns or a standard-error
column, and writes PDF/PNG outputs plus lightweight QC/metadata CSV files.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter, MaxNLocator
import pandas as pd


DEFAULT_PRIMARY_THRESHOLD = 1.571637
DEFAULT_WIDTH_INCHES = 3.35
DEFAULT_HEIGHT_INCHES = 2.35
DEFAULT_DPI = 300


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot the NPR threshold sensitivity of the localized quality -> "
            "future velocity coefficient."
        )
    )
    parser.add_argument("--input-csv", required=True, help="Input primary-summary CSV file.")
    parser.add_argument("--output-dir", required=True, help="Directory for PDF/PNG outputs.")
    parser.add_argument(
        "--output-prefix",
        default="fig_npr_threshold_sensitivity-v1",
        help="Filename prefix for output figure files.",
    )
    parser.add_argument(
        "--threshold-col",
        default="",
        help="Optional explicit threshold column name. Auto-detected if omitted.",
    )
    parser.add_argument(
        "--estimate-col",
        default="",
        help="Optional explicit coefficient column name. Auto-detected if omitted.",
    )
    parser.add_argument(
        "--se-col",
        default="",
        help="Optional explicit standard-error column name.",
    )
    parser.add_argument(
        "--ci-low-col",
        default="",
        help="Optional explicit lower 95%% CI column name.",
    )
    parser.add_argument(
        "--ci-high-col",
        default="",
        help="Optional explicit upper 95%% CI column name.",
    )
    parser.add_argument(
        "--primary-threshold",
        type=float,
        default=DEFAULT_PRIMARY_THRESHOLD,
        help="Frozen primary NPR threshold to highlight.",
    )
    parser.add_argument(
        "--primary-threshold-tol",
        type=float,
        default=1e-9,
        help="Tolerance for matching the primary threshold.",
    )
    parser.add_argument(
        "--ci-z",
        type=float,
        default=1.96,
        help="Critical value used when deriving 95%% CI from a standard error.",
    )
    parser.add_argument(
        "--width-inches",
        type=float,
        default=DEFAULT_WIDTH_INCHES,
        help="Figure width in inches.",
    )
    parser.add_argument(
        "--height-inches",
        type=float,
        default=DEFAULT_HEIGHT_INCHES,
        help="Figure height in inches.",
    )
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="PNG DPI.")
    parser.add_argument(
        "--title",
        default="",
        help="Optional figure title. Recommended to leave blank for paper figures.",
    )
    parser.add_argument(
        "--x-label",
        default=r"NPR threshold ($\\tau$)",
        help="X-axis label.",
    )
    parser.add_argument(
        "--y-label",
        default=r"Estimated effect on future velocity ($\\hat{\\gamma}$)",
        help="Y-axis label.",
    )
    return parser.parse_args()


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def normalize_columns(columns: Sequence[str]) -> dict[str, str]:
    return {str(col).strip().lower(): str(col) for col in columns}


def pick_column(explicit: str, columns: Sequence[str], candidates: Iterable[str], label: str) -> str:
    if explicit:
        if explicit not in columns:
            fail(f"{label} column not found: {explicit}")
        return explicit

    lookup = normalize_columns(columns)
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]

    fail(
        f"Could not auto-detect the {label} column. "
        f"Available columns: {', '.join(map(str, columns))}"
    )


def detect_columns(df: pd.DataFrame, args: argparse.Namespace) -> Tuple[str, str, Optional[str], Optional[str], Optional[str]]:
    threshold_col = pick_column(
        args.threshold_col,
        df.columns,
        [
            "npr_threshold",
            "threshold",
            "tau",
            "threshold_value",
            "cutoff",
        ],
        "threshold",
    )
    estimate_col = pick_column(
        args.estimate_col,
        df.columns,
        [
            "gamma_hat",
            "estimate",
            "coefficient",
            "coef",
            "beta",
            "gamma",
            "att",
        ],
        "estimate",
    )

    ci_low_col = None
    ci_high_col = None
    se_col = None

    if args.ci_low_col or args.ci_high_col:
        if not (args.ci_low_col and args.ci_high_col):
            fail("Both --ci-low-col and --ci-high-col must be supplied together.")
        if args.ci_low_col not in df.columns or args.ci_high_col not in df.columns:
            fail("One or both explicit CI columns were not found in the input CSV.")
        ci_low_col = args.ci_low_col
        ci_high_col = args.ci_high_col
    else:
        ci_lookup = normalize_columns(df.columns)
        low_candidates = ["ci_low", "lower_95", "ci95_low", "conf_low", "lower_ci"]
        high_candidates = ["ci_high", "upper_95", "ci95_high", "conf_high", "upper_ci"]
        for low_name in low_candidates:
            if low_name in ci_lookup:
                ci_low_col = ci_lookup[low_name]
                break
        for high_name in high_candidates:
            if high_name in ci_lookup:
                ci_high_col = ci_lookup[high_name]
                break

    if not (ci_low_col and ci_high_col):
        se_col = pick_column(
            args.se_col,
            df.columns,
            ["standard_error", "std_error", "stderr", "se"],
            "standard error",
        )

    return threshold_col, estimate_col, se_col, ci_low_col, ci_high_col


def prepare_plot_data(df: pd.DataFrame, args: argparse.Namespace) -> Tuple[pd.DataFrame, dict[str, str]]:
    threshold_col, estimate_col, se_col, ci_low_col, ci_high_col = detect_columns(df, args)

    work = df.copy()
    work[threshold_col] = pd.to_numeric(work[threshold_col], errors="coerce")
    work[estimate_col] = pd.to_numeric(work[estimate_col], errors="coerce")

    required_cols = [threshold_col, estimate_col]
    if ci_low_col and ci_high_col:
        work[ci_low_col] = pd.to_numeric(work[ci_low_col], errors="coerce")
        work[ci_high_col] = pd.to_numeric(work[ci_high_col], errors="coerce")
        required_cols.extend([ci_low_col, ci_high_col])
    else:
        assert se_col is not None
        work[se_col] = pd.to_numeric(work[se_col], errors="coerce")
        required_cols.append(se_col)

    work = work.dropna(subset=required_cols).copy()
    if work.empty:
        fail("No valid plotting rows remain after numeric conversion and NA removal.")

    work = work.sort_values(by=threshold_col, kind="mergesort").reset_index(drop=True)
    if work[threshold_col].duplicated().any():
        dupes = work.loc[work[threshold_col].duplicated(), threshold_col].tolist()
        fail(f"Threshold column contains duplicates: {dupes}")

    if ci_low_col and ci_high_col:
        work["ci_low"] = work[ci_low_col]
        work["ci_high"] = work[ci_high_col]
    else:
        assert se_col is not None
        work["ci_low"] = work[estimate_col] - args.ci_z * work[se_col]
        work["ci_high"] = work[estimate_col] + args.ci_z * work[se_col]

    if (work["ci_low"] > work["ci_high"]).any():
        fail("Some rows have ci_low > ci_high after preparation.")

    work = work.rename(columns={threshold_col: "threshold", estimate_col: "estimate"})

    columns_used = {
        "threshold_col": threshold_col,
        "estimate_col": estimate_col,
        "se_col": se_col or "",
        "ci_low_col": ci_low_col or "",
        "ci_high_col": ci_high_col or "",
    }
    return work, columns_used


def primary_row(data: pd.DataFrame, primary_threshold: float, tol: float) -> pd.Series:
    distances = (data["threshold"] - primary_threshold).abs()
    matched = data.loc[distances <= tol]
    if len(matched) != 1:
        fail(
            "Expected exactly one row matching the primary threshold "
            f"{primary_threshold:.6f} within tolerance {tol}. Observed matches: {len(matched)}"
        )
    return matched.iloc[0]


def plot_figure(data: pd.DataFrame, args: argparse.Namespace, output_dir: Path) -> Tuple[Path, Path]:
    fig, ax = plt.subplots(figsize=(args.width_inches, args.height_inches))

    lower_err = data["estimate"] - data["ci_low"]
    upper_err = data["ci_high"] - data["estimate"]

    ax.errorbar(
        data["threshold"],
        data["estimate"],
        yerr=[lower_err, upper_err],
        fmt="o-",
        linewidth=1.1,
        markersize=3.8,
        capsize=2.2,
        elinewidth=0.9,
    )

    ax.axhline(0.0, linestyle="--", linewidth=0.9)
    ax.axvline(args.primary_threshold, linestyle="--", linewidth=0.9)

    primary = primary_row(data, args.primary_threshold, args.primary_threshold_tol)
    ax.scatter(
        [primary["threshold"]],
        [primary["estimate"]],
        marker="D",
        s=26,
        zorder=5,
    )

    ax.set_xlabel(args.x_label, fontsize=8.4)
    ax.set_ylabel(args.y_label, fontsize=8.4)
    if args.title:
        ax.set_title(args.title, fontsize=8.6, pad=5.0)

    ax.tick_params(axis="both", labelsize=7.4)
    ax.xaxis.set_major_formatter(FormatStrFormatter("%.3f"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))

    x_values = data["threshold"].tolist()
    if len(x_values) <= 12:
        ax.set_xticks(x_values)
    else:
        # Keep all thresholds but rotate labels to maintain readability.
        ax.set_xticks(x_values)
        for label in ax.get_xticklabels():
            label.set_rotation(45)
            label.set_ha("right")

    y_min = min(float(data["ci_low"].min()), 0.0)
    y_max = max(float(data["ci_high"].max()), 0.0)
    pad = 0.08 * max(0.1, y_max - y_min)
    ax.set_ylim(y_min - pad, y_max + pad)

    ax.margins(x=0.02)
    fig.tight_layout(pad=0.6)

    pdf_path = output_dir / f"{args.output_prefix}.pdf"
    png_path = output_dir / f"{args.output_prefix}.png"
    fig.savefig(pdf_path, bbox_inches="tight", pad_inches=0.01)
    fig.savefig(png_path, dpi=args.dpi, bbox_inches="tight", pad_inches=0.01)
    plt.close(fig)
    return pdf_path, png_path


def write_qc(output_path: Path, data: pd.DataFrame, primary: pd.Series, pdf_path: Path, png_path: Path) -> None:
    rows = [
        {"check": "row_count", "observed": int(len(data)), "status": "pass" if len(data) > 0 else "fail"},
        {
            "check": "threshold_unique",
            "observed": int(data["threshold"].nunique()),
            "status": "pass" if data["threshold"].nunique() == len(data) else "fail",
        },
        {
            "check": "primary_threshold_found",
            "observed": float(primary["threshold"]),
            "status": "pass",
        },
        {
            "check": "pdf_written",
            "observed": int(pdf_path.exists() and pdf_path.stat().st_size > 0),
            "status": "pass" if pdf_path.exists() and pdf_path.stat().st_size > 0 else "fail",
        },
        {
            "check": "png_written",
            "observed": int(png_path.exists() and png_path.stat().st_size > 0),
            "status": "pass" if png_path.exists() and png_path.stat().st_size > 0 else "fail",
        },
    ]
    pd.DataFrame(rows).to_csv(output_path, index=False)


def write_metadata(output_path: Path, args: argparse.Namespace, columns_used: dict[str, str], data: pd.DataFrame) -> None:
    rows = [
        ("run", "script", "plot_npr_threshold_sensitivity-v1.py"),
        ("run", "figure", "Figure 1(a)"),
        ("input", "input_csv", str(args.input_csv)),
        ("input", "threshold_col", columns_used["threshold_col"]),
        ("input", "estimate_col", columns_used["estimate_col"]),
        ("input", "se_col", columns_used["se_col"]),
        ("input", "ci_low_col", columns_used["ci_low_col"]),
        ("input", "ci_high_col", columns_used["ci_high_col"]),
        ("figure", "primary_threshold", f"{args.primary_threshold:.6f}"),
        ("figure", "ci_z", str(args.ci_z)),
        ("figure", "x_label", args.x_label),
        ("figure", "y_label", args.y_label),
        ("figure", "width_inches", str(args.width_inches)),
        ("figure", "height_inches", str(args.height_inches)),
        ("figure", "dpi", str(args.dpi)),
        ("summary", "n_rows", str(len(data))),
        ("summary", "min_threshold", f"{float(data['threshold'].min()):.6f}"),
        ("summary", "max_threshold", f"{float(data['threshold'].max()):.6f}"),
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["section", "metric", "value"])
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    if args.width_inches <= 0 or args.height_inches <= 0 or args.dpi <= 0:
        fail("Figure dimensions and DPI must be positive.")

    input_path = Path(args.input_csv)
    if not input_path.is_file():
        fail(f"Input CSV not found: {input_path}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path)
    data, columns_used = prepare_plot_data(df, args)
    pdf_path, png_path = plot_figure(data, args, output_dir)

    primary = primary_row(data, args.primary_threshold, args.primary_threshold_tol)
    qc_path = output_dir / "fig_npr_threshold_sensitivity_qc.csv"
    metadata_path = output_dir / "fig_npr_threshold_sensitivity_metadata.csv"
    plot_data_path = output_dir / "fig_npr_threshold_sensitivity_plot_data.csv"

    write_qc(qc_path, data, primary, pdf_path, png_path)
    write_metadata(metadata_path, args, columns_used, data)
    data.to_csv(plot_data_path, index=False)

    qc = pd.read_csv(qc_path)
    if (qc["status"].astype(str).str.lower() == "fail").any():
        fail("Plot QC failed.")

    print("plot_npr_threshold_sensitivity-v1: PASS")
    print(f"Input CSV: {input_path}")
    print(f"Rows plotted: {len(data)}")
    print(f"Primary threshold: {args.primary_threshold:.6f}")
    print(f"PDF: {pdf_path}")
    print(f"PNG: {png_path}")
    print(f"QC: {qc_path}")
    print(f"Metadata: {metadata_path}")
    print(f"Plot data: {plot_data_path}")


if __name__ == "__main__":
    main()
