#!/usr/bin/env python3
"""Plot NPR-threshold sensitivity of the quality-to-future-velocity GMM.

Inputs
------
G06 primary summary CSV:
    One row per NPR threshold with the estimated GMM coefficient and 95% CI.
G06 QC CSV and metadata CSV:
    Used only to verify that the upstream G06 run completed without hard failures.

Outputs
-------
PDF and PNG figures:
    Point estimates connected in threshold order, 95% confidence intervals,
    a horizontal zero-effect reference line, the primary NPR threshold, and an
    emphasized primary point.
Plot data/QC/metadata CSVs:
    Preserve exactly the values used to render the figure and record provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


IMPLEMENTATION_VERSION = "v1"
DEFAULT_PRIMARY_THRESHOLD = 1.571637
EXPECTED_MAIN_THRESHOLDS = 21
EXPECTED_THRESHOLD_MIN = 1.071637
EXPECTED_THRESHOLD_MAX = 2.071637
EXPECTED_THRESHOLD_STEP = 0.05


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot G06 NPR-threshold sensitivity for future velocity."
    )
    parser.add_argument("--summary-file", required=True)
    parser.add_argument("--qc-file", required=True)
    parser.add_argument("--metadata-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--primary-threshold", type=float, default=DEFAULT_PRIMARY_THRESHOLD
    )
    parser.add_argument(
        "--implementation-version", default=IMPLEMENTATION_VERSION
    )
    parser.add_argument("--expected-thresholds", type=int, default=EXPECTED_MAIN_THRESHOLDS)
    parser.add_argument("--dpi", type=int, default=300)
    return parser.parse_args()


def abort(message: str) -> None:
    raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_columns(data: pd.DataFrame, required: list[str], label: str) -> None:
    missing = [column for column in required if column not in data.columns]
    if missing:
        abort(f"{label} is missing required columns: {', '.join(missing)}")


def coerce_numeric(data: pd.DataFrame, columns: list[str], label: str) -> None:
    for column in columns:
        converted = pd.to_numeric(data[column], errors="coerce")
        if converted.isna().any():
            bad = int(converted.isna().sum())
            abort(f"{label}.{column} contains {bad} non-numeric or missing values")
        if not np.isfinite(converted.to_numpy(dtype=float)).all():
            abort(f"{label}.{column} contains non-finite values")
        data[column] = converted


def expected_grid(primary_threshold: float) -> np.ndarray:
    offsets = np.arange(-10, 11, dtype=float) * EXPECTED_THRESHOLD_STEP
    return primary_threshold + offsets


def validate_g06_inputs(
    summary: pd.DataFrame,
    qc: pd.DataFrame,
    metadata: pd.DataFrame,
    primary_threshold: float,
    expected_thresholds: int,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    required_summary = [
        "threshold_id",
        "threshold",
        "threshold_role",
        "primary_analysis",
        "fit_status",
        "estimate",
        "std_error",
        "conf_low",
        "conf_high",
        "p_value",
        "selected_file_rows",
        "selected_issue_total",
        "zero_issue_share_active",
        "repositories_with_within_quality_variation_active",
    ]
    validate_columns(summary, required_summary, "G06 summary")
    validate_columns(qc, ["status"], "G06 QC")
    validate_columns(metadata, ["metric", "value"], "G06 metadata")

    numeric_columns = [
        "threshold",
        "primary_analysis",
        "estimate",
        "std_error",
        "conf_low",
        "conf_high",
        "p_value",
        "selected_file_rows",
        "selected_issue_total",
        "zero_issue_share_active",
        "repositories_with_within_quality_variation_active",
    ]
    coerce_numeric(summary, numeric_columns, "G06 summary")

    checks: list[dict[str, object]] = []

    def add_check(name: str, observed: object, expected: object, passed: bool) -> None:
        checks.append(
            {
                "check": name,
                "observed": observed,
                "expected": expected,
                "status": "pass" if passed else "fail",
            }
        )

    add_check(
        "summary_rows",
        len(summary),
        expected_thresholds,
        len(summary) == expected_thresholds,
    )
    add_check(
        "unique_thresholds",
        int(summary["threshold"].nunique()),
        expected_thresholds,
        int(summary["threshold"].nunique()) == expected_thresholds,
    )
    add_check(
        "all_models_success",
        int((summary["fit_status"].astype(str) == "success").sum()),
        expected_thresholds,
        (summary["fit_status"].astype(str) == "success").all(),
    )

    hard_fail_count = int((qc["status"].astype(str).str.lower() == "fail").sum())
    add_check("g06_hard_failures", hard_fail_count, 0, hard_fail_count == 0)

    primary_mask = np.isclose(
        summary["threshold"].to_numpy(dtype=float),
        primary_threshold,
        rtol=0.0,
        atol=1e-10,
    )
    add_check(
        "primary_threshold_rows",
        int(primary_mask.sum()),
        1,
        int(primary_mask.sum()) == 1,
    )

    primary_flag_count = int((summary["primary_analysis"] == 1).sum())
    add_check("primary_flag_rows", primary_flag_count, 1, primary_flag_count == 1)
    if int(primary_mask.sum()) == 1:
        primary_flag_value = int(summary.loc[primary_mask, "primary_analysis"].iloc[0])
        add_check(
            "primary_threshold_flag",
            primary_flag_value,
            1,
            primary_flag_value == 1,
        )

    ordered = summary.sort_values("threshold", kind="stable").reset_index(drop=True)
    expected = expected_grid(primary_threshold)
    observed = ordered["threshold"].to_numpy(dtype=float)
    grid_ok = len(observed) == len(expected) and np.allclose(
        observed, expected, rtol=0.0, atol=1e-10
    )
    add_check(
        "primary_centered_21_point_grid",
        "|".join(f"{value:.6f}" for value in observed),
        "|".join(f"{value:.6f}" for value in expected),
        grid_ok,
    )
    if len(observed):
        add_check(
            "threshold_min",
            f"{observed.min():.6f}",
            f"{EXPECTED_THRESHOLD_MIN:.6f}",
            math.isclose(observed.min(), EXPECTED_THRESHOLD_MIN, abs_tol=1e-10),
        )
        add_check(
            "threshold_max",
            f"{observed.max():.6f}",
            f"{EXPECTED_THRESHOLD_MAX:.6f}",
            math.isclose(observed.max(), EXPECTED_THRESHOLD_MAX, abs_tol=1e-10),
        )

    ci_contains = (
        (ordered["conf_low"] <= ordered["estimate"])
        & (ordered["estimate"] <= ordered["conf_high"])
        & (ordered["conf_low"] <= ordered["conf_high"])
    )
    add_check(
        "valid_confidence_intervals",
        int(ci_contains.sum()),
        expected_thresholds,
        bool(ci_contains.all()),
    )

    se_positive = ordered["std_error"] > 0
    add_check(
        "positive_standard_errors",
        int(se_positive.sum()),
        expected_thresholds,
        bool(se_positive.all()),
    )

    failed = [item["check"] for item in checks if item["status"] == "fail"]
    if failed:
        abort("G07 input/QC validation failed: " + ", ".join(failed))

    return ordered, checks


def configure_matplotlib() -> None:
    plt.rcParams.update(
        {
            "font.size": 7.5,
            "axes.labelsize": 8.0,
            "xtick.labelsize": 7.0,
            "ytick.labelsize": 7.0,
            "axes.linewidth": 0.8,
            "lines.linewidth": 1.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def plot_sensitivity(
    data: pd.DataFrame,
    primary_threshold: float,
    pdf_path: Path,
    png_path: Path,
    dpi: int,
) -> None:
    configure_matplotlib()

    x = data["threshold"].to_numpy(dtype=float)
    y = data["estimate"].to_numpy(dtype=float)
    lower = data["conf_low"].to_numpy(dtype=float)
    upper = data["conf_high"].to_numpy(dtype=float)
    yerr = np.vstack((y - lower, upper - y))

    primary_mask = np.isclose(x, primary_threshold, rtol=0.0, atol=1e-10)
    non_primary_mask = ~primary_mask

    fig, ax = plt.subplots(figsize=(3.45, 2.55))

    # Connect all coefficient estimates in threshold order.
    ax.plot(x, y, color="0.45", linewidth=1.0, zorder=2)

    # Plot all non-primary estimates with open markers and 95% confidence intervals.
    ax.errorbar(
        x[non_primary_mask],
        y[non_primary_mask],
        yerr=yerr[:, non_primary_mask],
        fmt="o",
        markersize=3.6,
        markerfacecolor="white",
        markeredgecolor="black",
        markeredgewidth=0.8,
        ecolor="0.45",
        elinewidth=0.8,
        capsize=2.0,
        capthick=0.8,
        linestyle="none",
        zorder=3,
    )

    # Emphasize the prespecified primary NPR threshold with a larger filled marker.
    ax.errorbar(
        x[primary_mask],
        y[primary_mask],
        yerr=yerr[:, primary_mask],
        fmt="o",
        markersize=5.8,
        markerfacecolor="black",
        markeredgecolor="black",
        markeredgewidth=0.9,
        ecolor="black",
        elinewidth=1.1,
        capsize=2.5,
        capthick=1.0,
        linestyle="none",
        zorder=5,
    )

    # Reference lines: no effect and the prespecified primary NPR threshold.
    ax.axhline(0.0, color="0.35", linewidth=0.8, linestyle=(0, (2, 2)), zorder=1)
    ax.axvline(
        primary_threshold,
        color="0.35",
        linewidth=0.8,
        linestyle=(0, (4, 2)),
        zorder=1,
    )

    ax.set_xlabel(r"NPR threshold ($\tau$)")
    ax.set_ylabel(r"Estimated effect on future velocity ($\hat{\gamma}$)")

    # Show every second threshold to keep a single-column figure readable.
    tick_values = x[::2]
    ax.set_xticks(tick_values)
    ax.set_xticklabels([f"{value:.2f}" for value in tick_values])

    y_span = float(np.nanmax(upper) - np.nanmin(lower))
    margin = max(0.08, 0.06 * y_span)
    ax.set_ylim(float(np.nanmin(lower) - margin), float(max(0.0, np.nanmax(upper)) + margin))
    ax.set_xlim(float(x.min() - 0.018), float(x.max() + 0.018))

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(direction="out", length=2.5, width=0.7)

    fig.tight_layout(pad=0.55)
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()

    summary_path = Path(args.summary_file).resolve()
    qc_path = Path(args.qc_file).resolve()
    metadata_path = Path(args.metadata_file).resolve()
    output_dir = Path(args.output_dir).resolve()

    for path, label in [
        (summary_path, "G06 summary"),
        (qc_path, "G06 QC"),
        (metadata_path, "G06 metadata"),
    ]:
        if not path.is_file():
            abort(f"{label} file not found: {path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    summary = pd.read_csv(summary_path)
    qc = pd.read_csv(qc_path)
    metadata = pd.read_csv(metadata_path)

    data, checks = validate_g06_inputs(
        summary=summary,
        qc=qc,
        metadata=metadata,
        primary_threshold=args.primary_threshold,
        expected_thresholds=args.expected_thresholds,
    )

    figure_pdf = output_dir / f"fig_npr_threshold_sensitivity-{args.implementation_version}.pdf"
    figure_png = output_dir / f"fig_npr_threshold_sensitivity-{args.implementation_version}.png"
    plot_data_path = output_dir / "plot_npr_threshold_sensitivity_data.csv"
    plot_qc_path = output_dir / "plot_npr_threshold_sensitivity_qc.csv"
    plot_metadata_path = output_dir / "plot_npr_threshold_sensitivity_metadata.csv"

    plot_columns = [
        "threshold_id",
        "threshold",
        "primary_analysis",
        "estimate",
        "std_error",
        "conf_low",
        "conf_high",
        "p_value",
        "selected_file_rows",
        "selected_issue_total",
        "zero_issue_share_active",
        "repositories_with_within_quality_variation_active",
    ]
    data[plot_columns].to_csv(plot_data_path, index=False)
    pd.DataFrame(checks).to_csv(plot_qc_path, index=False)

    plot_sensitivity(
        data=data,
        primary_threshold=args.primary_threshold,
        pdf_path=figure_pdf,
        png_path=figure_png,
        dpi=args.dpi,
    )

    primary_row = data.loc[
        np.isclose(
            data["threshold"].to_numpy(dtype=float),
            args.primary_threshold,
            rtol=0.0,
            atol=1e-10,
        )
    ].iloc[0]

    output_metadata = pd.DataFrame(
        [
            ("run_prefix", "run-x-g07"),
            ("implementation_version", args.implementation_version),
            ("source_experiment", "run-x-g06"),
            ("source_summary", str(summary_path)),
            ("source_summary_sha256", sha256_file(summary_path)),
            ("source_qc", str(qc_path)),
            ("source_qc_sha256", sha256_file(qc_path)),
            ("source_metadata", str(metadata_path)),
            ("source_metadata_sha256", sha256_file(metadata_path)),
            ("threshold_count", str(len(data))),
            ("primary_threshold", f"{args.primary_threshold:.6f}"),
            ("primary_estimate", f"{float(primary_row['estimate']):.12g}"),
            ("primary_conf_low", f"{float(primary_row['conf_low']):.12g}"),
            ("primary_conf_high", f"{float(primary_row['conf_high']):.12g}"),
            ("figure_pdf", str(figure_pdf)),
            ("figure_png", str(figure_png)),
            ("figure_design", "point+line+95CI; y=0 reference; primary threshold reference; primary point emphasized"),
        ],
        columns=["metric", "value"],
    )
    output_metadata.to_csv(plot_metadata_path, index=False)

    for path in [figure_pdf, figure_png, plot_data_path, plot_qc_path, plot_metadata_path]:
        if not path.is_file() or path.stat().st_size == 0:
            abort(f"Expected non-empty G07 output missing: {path}")

    print("run-x-g07 NPR threshold-sensitivity figure: PASS")
    print(f"Threshold rows: {len(data)}")
    print(f"Primary threshold: {args.primary_threshold:.6f}")
    print(f"Primary estimate: {float(primary_row['estimate']):.6f}")
    print(f"Primary 95% CI: [{float(primary_row['conf_low']):.6f}, {float(primary_row['conf_high']):.6f}]")
    print(f"PDF: {figure_pdf}")
    print(f"PNG: {figure_png}")
    print(f"Plot data: {plot_data_path}")
    print(f"QC: {plot_qc_path}")


if __name__ == "__main__":
    main()
