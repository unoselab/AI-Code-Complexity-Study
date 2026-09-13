#!/usr/bin/env python3
"""Create detector-localized monthly and weekly Python velocity figures.

run-y-b13 v1 is a reporting-only analysis. It reads the established dynamic
DiD estimates from run-x-b08-v4 and run-x-b09-v2, verifies their statistical
and structural consistency, and creates a combined 2-by-3 figure. No model is
estimated by this script, and no existing experiment script is invoked.

The combined figure uses columns for RF, CM, and RF+CM and rows for monthly
and weekly estimates. Color distinguishes NPR and ML, while line style and
marker shape distinguish FECS and FEOS. Small horizontal offsets prevent the
four pointwise 95% confidence intervals at an event time from overlapping.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import NormalDist
import sys
import tempfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd


VERSION = "v1"
RUN_ID = "run-y-b13"
DETECTORS = ("NPR", "ML")
SCOPES = ("RF", "CM", "RF+CM")
SPECIFICATIONS = ("FECS", "FEOS")
MONTHLY_EVENTS = tuple(range(-6, -1)) + tuple(range(0, 7))
WEEKLY_EVENTS = tuple(range(-12, -1)) + tuple(range(0, 13))

# Okabe-Ito colors remain distinguishable in grayscale and common forms of
# color-vision deficiency. Specification is encoded independently by shape and
# line style, so interpretation does not depend on color alone.
COLORS = {"NPR": "#0072B2", "ML": "#D55E00"}
LINESTYLES = {"FECS": "-", "FEOS": (0, (4, 2))}
MARKERS = {"FECS": "o", "FEOS": "s"}
OFFSETS = {
    ("NPR", "FECS"): -0.18,
    ("NPR", "FEOS"): -0.06,
    ("ML", "FECS"): 0.06,
    ("ML", "FEOS"): 0.18,
}


def require(condition: bool, message: str) -> None:
    """Raise a concise validation error when a required condition is false."""
    if not bool(condition):
        raise ValueError(message)


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_boolean(values: pd.Series, label: str) -> pd.Series:
    """Parse strict CSV Boolean values and reject ambiguous representations."""
    normalized = values.astype(str).str.strip().str.lower()
    require(
        normalized.isin(("true", "false", "1", "0")).all(),
        f"Invalid Boolean value in {label}",
    )
    return normalized.isin(("true", "1"))


def normalize_effect_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize punctuation in source column names while preserving values."""
    aliases = {
        "std.error": "std_error",
        "conf.low": "conf_low",
        "conf.high": "conf_high",
    }
    frame = frame.rename(columns=aliases).copy()
    required = {
        "estimate",
        "std_error",
        "conf_low",
        "conf_high",
        "p_value",
        "event_time",
        "specification",
        "detector",
        "scope",
        "outcome",
        "term_type",
    }
    missing = sorted(required.difference(frame.columns))
    require(not missing, "Missing required effect columns: " + ", ".join(missing))
    for column in (
        "estimate",
        "std_error",
        "conf_low",
        "conf_high",
        "p_value",
        "event_time",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        require(np.isfinite(frame[column]).all(), f"Non-finite values in {column}")
    frame["event_time"] = frame["event_time"].astype(int)
    return frame


def validate_effects(
    frame: pd.DataFrame,
    time_unit: str,
    expected_rows: int,
    confidence_level: float,
    checks: list[dict[str, object]],
) -> pd.DataFrame:
    """Validate one source table and append machine-readable checks."""

    def check(name: str, observed: object, expected: object, passed: bool) -> None:
        checks.append(
            {
                "check_name": f"{time_unit}_{name}",
                "observed": observed,
                "expected": expected,
                "pass": bool(passed),
            }
        )
        require(passed, f"Reconciliation failed: {time_unit}_{name}")

    frame = normalize_effect_columns(frame)
    expected_events = MONTHLY_EVENTS if time_unit == "month" else WEEKLY_EVENTS
    expected_pairs = {
        (detector, scope, specification)
        for detector in DETECTORS
        for scope in SCOPES
        for specification in SPECIFICATIONS
    }
    observed_pairs = set(zip(frame.detector, frame.scope, frame.specification))
    check("row_count", len(frame), expected_rows, len(frame) == expected_rows)
    check("detector_scope_specification_pairs", len(observed_pairs), 12, observed_pairs == expected_pairs)
    keys = ["detector", "scope", "specification", "event_time"]
    duplicates = int(frame.duplicated(keys).sum())
    check("duplicate_keys", duplicates, 0, duplicates == 0)
    check("positive_standard_errors", int(frame.std_error.gt(0).sum()), len(frame), frame.std_error.gt(0).all())
    check("p_value_bounds", int(frame.p_value.between(0, 1).sum()), len(frame), frame.p_value.between(0, 1).all())

    events_valid = True
    for _, group in frame.groupby(["detector", "scope", "specification"], sort=False):
        if tuple(sorted(group.event_time.tolist())) != expected_events:
            events_valid = False
            break
    check("event_support", events_valid, True, events_valid)
    check("omitted_reference_absent", int(frame.event_time.eq(-1).sum()), 0, not frame.event_time.eq(-1).any())

    alpha = 1.0 - confidence_level
    critical = NormalDist().inv_cdf(1.0 - alpha / 2.0)
    expected_low = frame.estimate - critical * frame.std_error
    expected_high = frame.estimate + critical * frame.std_error
    low_ok = np.allclose(frame.conf_low, expected_low, rtol=0, atol=1e-9)
    high_ok = np.allclose(frame.conf_high, expected_high, rtol=0, atol=1e-9)
    expected_p = np.array(
        [math.erfc(abs(estimate / se) / math.sqrt(2.0)) for estimate, se in zip(frame.estimate, frame.std_error)]
    )
    p_ok = np.allclose(frame.p_value, expected_p, rtol=0, atol=1e-9)
    check("confidence_interval_lower", low_ok, True, low_ok)
    check("confidence_interval_upper", high_ok, True, high_ok)
    check("two_sided_normal_p_values", p_ok, True, p_ok)

    expected_term_type = np.where(frame.event_time.lt(0), "placebo_pretrend", "post_treatment")
    term_ok = np.array_equal(frame.term_type.astype(str).to_numpy(), expected_term_type)
    check("term_type", term_ok, True, term_ok)

    if time_unit == "week":
        timing_ok = "timing_spec" in frame and frame.timing_spec.eq("exact_observed_date").all()
        unit_ok = "time_unit" in frame and frame.time_unit.eq("week").all()
        check("exact_observed_date", timing_ok, True, timing_ok)
        check("time_unit", unit_ok, True, unit_ok)
        if "significant_05" in frame:
            source_flag = parse_boolean(frame.significant_05, "significant_05")
            flag_ok = np.array_equal(source_flag.to_numpy(), frame.p_value.lt(alpha).to_numpy())
            check("significance_flag", flag_ok, True, flag_ok)

    frame["time_unit"] = time_unit
    frame["significant_05"] = frame.p_value.lt(alpha)
    frame["source_row"] = True
    return frame


def validate_source_qc(
    qc: pd.DataFrame,
    expected_rows: int,
    checks: list[dict[str, object]],
) -> None:
    """Require all upstream sensitivity checks to pass before plotting."""
    required = {"check_name", "observed", "expected", "pass"}
    missing = sorted(required.difference(qc.columns))
    require(not missing, "Missing source-QC columns: " + ", ".join(missing))
    flags = parse_boolean(qc["pass"], "source QC pass")
    checks.append(
        {
            "check_name": "source_qc_row_count",
            "observed": len(qc),
            "expected": expected_rows,
            "pass": len(qc) == expected_rows,
        }
    )
    checks.append(
        {
            "check_name": "source_qc_failures",
            "observed": int((~flags).sum()),
            "expected": 0,
            "pass": bool(flags.all()),
        }
    )
    require(len(qc) == expected_rows, f"Expected {expected_rows} source-QC rows; observed {len(qc)}")
    require(flags.all(), "At least one upstream sensitivity QC check failed")


def add_reference_period(frame: pd.DataFrame) -> pd.DataFrame:
    """Add event time -1 at zero solely as the omitted visual reference."""
    rows: list[dict[str, object]] = []
    for (time_unit, detector, scope, specification, outcome), _ in frame.groupby(
        ["time_unit", "detector", "scope", "specification", "outcome"], sort=False
    ):
        rows.append(
            {
                "time_unit": time_unit,
                "detector": detector,
                "scope": scope,
                "specification": specification,
                "outcome": outcome,
                "event_time": -1,
                "estimate": 0.0,
                "std_error": np.nan,
                "conf_low": np.nan,
                "conf_high": np.nan,
                "p_value": np.nan,
                "significant_05": False,
                "term_type": "omitted_reference",
                "source_row": False,
            }
        )
    return pd.concat([frame, pd.DataFrame(rows)], ignore_index=True, sort=False)


def y_limits(frame: pd.DataFrame, time_unit: str) -> tuple[float, float]:
    """Use a common y-axis within a temporal resolution for scope comparison."""
    part = frame[(frame.time_unit == time_unit) & frame.source_row]
    lower = min(0.0, float(part.conf_low.min()))
    upper = max(0.0, float(part.conf_high.max()))
    span = max(upper - lower, 0.1)
    return lower - 0.06 * span, upper + 0.06 * span


def draw_panel(
    ax: plt.Axes,
    frame: pd.DataFrame,
    time_unit: str,
    scope: str,
    panel_label: str,
    limits: tuple[float, float],
    show_ylabel: bool,
) -> None:
    """Draw four offset detector/specification series in one panel."""
    part = frame[(frame.time_unit == time_unit) & (frame.scope == scope)]
    for detector in DETECTORS:
        for specification in SPECIFICATIONS:
            group = part[
                (part.detector == detector) & (part.specification == specification)
            ].sort_values("event_time")
            require(not group.empty, f"Missing series: {time_unit}/{detector}/{scope}/{specification}")
            offset = OFFSETS[(detector, specification)]
            x = group.event_time.to_numpy(dtype=float) + offset
            y = group.estimate.to_numpy(dtype=float)
            source = group.source_row.to_numpy(dtype=bool)
            color = COLORS[detector]
            ax.plot(
                x,
                y,
                color=color,
                linestyle=LINESTYLES[specification],
                linewidth=1.0,
                marker=MARKERS[specification],
                markersize=2.8,
                markerfacecolor="white" if specification == "FEOS" else color,
                markeredgecolor=color,
                markeredgewidth=0.7,
                zorder=3,
            )
            observed = group.loc[source]
            observed_x = observed.event_time.to_numpy(dtype=float) + offset
            observed_y = observed.estimate.to_numpy(dtype=float)
            ax.errorbar(
                observed_x,
                observed_y,
                yerr=np.vstack(
                    (
                        observed_y - observed.conf_low.to_numpy(dtype=float),
                        observed.conf_high.to_numpy(dtype=float) - observed_y,
                    )
                ),
                fmt="none",
                ecolor=color,
                elinewidth=0.75,
                capsize=1.4,
                capthick=0.7,
                alpha=0.92,
                zorder=2,
            )

    ax.axhline(0.0, color="#666666", linewidth=0.7, zorder=0)
    ax.axvline(-0.5, color="#999999", linestyle=(0, (2, 2)), linewidth=0.7, zorder=0)
    ax.set_ylim(*limits)
    if time_unit == "month":
        ax.set_xlim(-6.55, 6.55)
        ax.set_xticks((-6, -4, -2, 0, 2, 4, 6))
        ax.set_xlabel("Event month")
    else:
        ax.set_xlim(-12.55, 12.55)
        ax.set_xticks((-12, -8, -4, 0, 4, 8, 12))
        ax.set_xlabel("Event week")
    if show_ylabel:
        ax.set_ylabel("ATT (log scale)")
    ax.set_title(panel_label, loc="left", fontsize=8.3, pad=4)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(direction="out", length=2.4, width=0.65, pad=2)


def legend_handles() -> list[Line2D]:
    """Return a detector/specification legend matching every visual encoding."""
    return [
        Line2D(
            [],
            [],
            color=COLORS[detector],
            linestyle=LINESTYLES[specification],
            marker=MARKERS[specification],
            markersize=4.0,
            markerfacecolor="white" if specification == "FEOS" else COLORS[detector],
            markeredgecolor=COLORS[detector],
            linewidth=1.1,
            label=f"{detector} ({specification})",
        )
        for detector in DETECTORS
        for specification in SPECIFICATIONS
    ]


def configure_style() -> None:
    """Apply compact publication settings and embed editable TrueType fonts."""
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 7.5,
            "axes.labelsize": 7.5,
            "xtick.labelsize": 6.8,
            "ytick.labelsize": 6.8,
            "legend.fontsize": 7.2,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def render_combined(
    frame: pd.DataFrame,
    output_pdf: Path,
    output_png: Path,
    width: float,
    height: float,
    dpi: int,
) -> dict[str, list[float]]:
    """Create the primary double-column 2-by-3 figure."""
    configure_style()
    limits = {unit: y_limits(frame, unit) for unit in ("month", "week")}
    fig, axes = plt.subplots(2, 3, figsize=(width, height), sharey="row")
    fig.subplots_adjust(left=0.075, right=0.99, bottom=0.14, top=0.97, wspace=0.18, hspace=0.42)
    panel = 0
    for row, time_unit in enumerate(("month", "week")):
        temporal_label = "Monthly" if time_unit == "month" else "Weekly"
        for column, scope in enumerate(SCOPES):
            label = f"({chr(97 + panel)}) {temporal_label}: {scope}"
            draw_panel(
                axes[row, column],
                frame,
                time_unit,
                scope,
                label,
                limits[time_unit],
                show_ylabel=column == 0,
            )
            panel += 1
    fig.legend(
        handles=legend_handles(),
        loc="lower center",
        bbox_to_anchor=(0.53, 0.015),
        ncol=4,
        frameon=False,
        handlelength=2.2,
        columnspacing=1.4,
    )
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_pdf, bbox_inches="tight")
    fig.savefig(output_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return {key: [float(value) for value in values] for key, values in limits.items()}


def render_temporal(
    frame: pd.DataFrame,
    time_unit: str,
    output_pdf: Path,
    output_png: Path,
    width: float,
    dpi: int,
) -> None:
    """Create a one-row alternative for manuscripts with different layouts."""
    configure_style()
    limits = y_limits(frame, time_unit)
    fig, axes = plt.subplots(1, 3, figsize=(width, 2.45), sharey=True)
    fig.subplots_adjust(left=0.075, right=0.99, bottom=0.24, top=0.93, wspace=0.18)
    temporal_label = "Monthly" if time_unit == "month" else "Weekly"
    for column, scope in enumerate(SCOPES):
        draw_panel(
            axes[column],
            frame,
            time_unit,
            scope,
            f"({chr(97 + column)}) {scope}",
            limits,
            show_ylabel=column == 0,
        )
    fig.legend(
        handles=legend_handles(),
        loc="lower center",
        bbox_to_anchor=(0.53, 0.035),
        ncol=4,
        frameon=False,
        handlelength=2.2,
        columnspacing=1.4,
    )
    fig.suptitle(f"{temporal_label} detector-localized velocity effects", fontsize=8.5, y=0.995)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_pdf, bbox_inches="tight")
    fig.savefig(output_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def event_list(values: pd.Series) -> str:
    """Encode event times without implying that separated periods are contiguous."""
    return "|".join(str(int(value)) for value in sorted(values.tolist()))


def summarize(frame: pd.DataFrame, confidence_level: float) -> pd.DataFrame:
    """Summarize pointwise inference without replacing the plotted estimates."""
    alpha = 1.0 - confidence_level
    records: list[dict[str, object]] = []
    for keys, group in frame[frame.source_row].groupby(
        ["time_unit", "detector", "scope", "specification"], sort=False
    ):
        time_unit, detector, scope, specification = keys
        pre = group[group.event_time.lt(-1)]
        post = group[group.event_time.ge(0)]
        significant_pre = pre[pre.p_value.lt(alpha)]
        significant_post = post[post.p_value.lt(alpha)]
        record: dict[str, object] = {
            "time_unit": time_unit,
            "detector": detector,
            "scope": scope,
            "specification": specification,
            "source_rows": len(group),
            "pointwise_significant_pre_periods": len(significant_pre),
            "significant_pre_event_times": event_list(significant_pre.event_time),
            "pointwise_significant_post_periods": len(significant_post),
            "significant_post_event_times": event_list(significant_post.event_time),
            "minimum_pre_p_value": float(pre.p_value.min()),
            "minimum_post_p_value": float(post.p_value.min()),
            "inference": "pointwise 95% normal confidence intervals; no multiplicity adjustment",
        }
        for event_time in (0, 1):
            row = group[group.event_time.eq(event_time)]
            if len(row) == 1:
                record[f"event_{event_time}_estimate"] = float(row.estimate.iloc[0])
                record[f"event_{event_time}_std_error"] = float(row.std_error.iloc[0])
                record[f"event_{event_time}_p_value"] = float(row.p_value.iloc[0])
        records.append(record)
    return pd.DataFrame(records)


def build_fixture() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Construct deterministic source-shaped data for the structural self-test."""
    critical = NormalDist().inv_cdf(0.975)
    frames: dict[str, list[dict[str, object]]] = {"month": [], "week": []}
    for time_unit, events in (("month", MONTHLY_EVENTS), ("week", WEEKLY_EVENTS)):
        for detector_index, detector in enumerate(DETECTORS):
            for scope_index, scope in enumerate(SCOPES):
                for specification_index, specification in enumerate(SPECIFICATIONS):
                    for event_time in events:
                        estimate = 0.05 * detector_index + 0.03 * scope_index + 0.02 * specification_index
                        estimate += 0.20 if event_time >= 0 else 0.01 * event_time
                        std_error = 0.12 + 0.005 * scope_index
                        p_value = math.erfc(abs(estimate / std_error) / math.sqrt(2.0))
                        row: dict[str, object] = {
                            "term": event_time,
                            "estimate": estimate,
                            "std.error": std_error,
                            "conf.low": estimate - critical * std_error,
                            "conf.high": estimate + critical * std_error,
                            "p_value": p_value,
                            "percent_change": 100.0 * math.expm1(estimate),
                            "event_time": event_time,
                            "specification": specification,
                            "first_stage_formula": "fixture",
                            "outcome": f"fixture_{detector.lower()}_{scope.lower().replace('+', '_')}",
                            "detector": detector,
                            "scope": scope,
                            "term_type": "placebo_pretrend" if event_time < 0 else "post_treatment",
                        }
                        if time_unit == "week":
                            row.update(
                                {
                                    "significant_05": str(p_value < 0.05).upper(),
                                    "support_rows": 50,
                                    "support_repositories": 50,
                                    "timing_spec": "exact_observed_date",
                                    "timing_label": "Exact first observable Cursor-related commit",
                                    "adoption_shift": 0,
                                    "time_unit": "week",
                                }
                            )
                        frames[time_unit].append(row)
    qc = pd.DataFrame(
        {
            "check_name": [f"fixture_{index}" for index in range(15)],
            "observed": [1] * 15,
            "expected": [1] * 15,
            "pass": ["TRUE"] * 15,
        }
    )
    return pd.DataFrame(frames["month"]), pd.DataFrame(frames["week"]), qc


def self_test() -> None:
    """Exercise validation, omitted-period handling, summaries, and rendering."""
    monthly, weekly, source_qc = build_fixture()
    checks: list[dict[str, object]] = []
    monthly = validate_effects(monthly, "month", 144, 0.95, checks)
    weekly = validate_effects(weekly, "week", 288, 0.95, checks)
    validate_source_qc(source_qc, 15, checks)
    combined = add_reference_period(pd.concat([monthly, weekly], ignore_index=True, sort=False))
    require(len(combined) == 456, "Self-test reference-period row count mismatch")
    require((~combined.source_row).sum() == 24, "Self-test omitted-reference count mismatch")
    summary = summarize(combined, 0.95)
    require(len(summary) == 24, "Self-test series-summary row count mismatch")
    with tempfile.TemporaryDirectory(prefix="run-y-b13-self-test-") as directory:
        root = Path(directory)
        render_combined(combined, root / "combined.pdf", root / "combined.png", 7.1, 4.8, 100)
        render_temporal(combined, "month", root / "month.pdf", root / "month.png", 7.1, 100)
        render_temporal(combined, "week", root / "week.pdf", root / "week.png", 7.1, 100)
        for filename in ("combined.pdf", "combined.png", "month.pdf", "month.png", "week.pdf", "week.png"):
            require((root / filename).stat().st_size > 0, f"Self-test did not create {filename}")
    print(f"SELF-TEST PASS: {len(checks)} source checks, 24 series, and six figure files")


def parse_arguments() -> argparse.Namespace:
    """Parse reporting inputs while allowing a source-independent self-test."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monthly-effects-file", type=Path)
    parser.add_argument("--weekly-effects-file", type=Path)
    parser.add_argument("--source-qc-file", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--figure-output", type=Path)
    parser.add_argument("--implementation-version", choices=[VERSION], default=VERSION)
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument("--expected-monthly-rows", type=int, default=144)
    parser.add_argument("--expected-weekly-rows", type=int, default=288)
    parser.add_argument("--expected-source-qc-rows", type=int, default=15)
    parser.add_argument("--figure-width", type=float, default=7.1)
    parser.add_argument("--figure-height", type=float, default=4.8)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Validate established estimates, create figures, and preserve provenance."""
    args = parse_arguments()
    if args.self_test:
        self_test()
        return

    for name in ("monthly_effects_file", "weekly_effects_file", "source_qc_file", "output_root", "figure_output"):
        require(getattr(args, name) is not None, f"--{name.replace('_', '-')} is required")
    require(abs(args.confidence_level - 0.95) < 1e-12, "Source estimates require confidence-level=0.95")
    require(args.expected_monthly_rows == 144, "This release expects 144 monthly effect rows")
    require(args.expected_weekly_rows == 288, "This release expects 288 weekly effect rows")
    require(args.expected_source_qc_rows == 15, "This release expects 15 upstream QC rows")
    require(args.figure_width >= 6.5, "The six-panel figure requires width >= 6.5 inches")
    require(args.figure_height >= 4.2, "The six-panel figure requires height >= 4.2 inches")
    require(args.dpi >= 100, "DPI must be at least 100")

    input_paths = {
        "monthly_effects": args.monthly_effects_file,
        "weekly_effects": args.weekly_effects_file,
        "source_qc": args.source_qc_file,
    }
    for label, path in input_paths.items():
        require(path.is_file(), f"Missing {label}: {path}")

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    figure_dir = output_root / "figure"
    figure_dir.mkdir(parents=True, exist_ok=True)
    combined_png = figure_dir / f"fig_did_velocity_python_localized_dynamic-{VERSION}.png"
    monthly_pdf = figure_dir / f"fig_did_velocity_python_localized_monthly_dynamic-{VERSION}.pdf"
    monthly_png = figure_dir / f"fig_did_velocity_python_localized_monthly_dynamic-{VERSION}.png"
    weekly_pdf = figure_dir / f"fig_did_velocity_python_localized_weekly_dynamic-{VERSION}.pdf"
    weekly_png = figure_dir / f"fig_did_velocity_python_localized_weekly_dynamic-{VERSION}.png"
    plot_data_path = output_root / "python_velocity_localized_dynamic_plot_data.csv"
    summary_path = output_root / "python_velocity_localized_dynamic_series_summary.csv"
    checks_path = output_root / "python_velocity_localized_dynamic_reconciliation_checks.csv"
    metadata_path = output_root / "python_velocity_localized_dynamic_run_metadata.json"
    targets = [
        args.figure_output,
        combined_png,
        monthly_pdf,
        monthly_png,
        weekly_pdf,
        weekly_png,
        plot_data_path,
        summary_path,
        checks_path,
        metadata_path,
    ]
    require(len({path.resolve() for path in targets}) == len(targets), "Duplicate output paths")
    input_resolved = {path.resolve() for path in input_paths.values()}
    require(not input_resolved.intersection(path.resolve() for path in targets), "An output would overwrite an input")
    existing = [str(path) for path in targets if path.exists()]
    require(args.overwrite or not existing, "Outputs exist; use --overwrite: " + ", ".join(existing[:4]))

    monthly_source = pd.read_csv(args.monthly_effects_file, keep_default_na=False)
    weekly_source = pd.read_csv(args.weekly_effects_file, keep_default_na=False)
    source_qc = pd.read_csv(args.source_qc_file, keep_default_na=False)
    checks: list[dict[str, object]] = []
    monthly = validate_effects(
        monthly_source,
        "month",
        args.expected_monthly_rows,
        args.confidence_level,
        checks,
    )
    weekly = validate_effects(
        weekly_source,
        "week",
        args.expected_weekly_rows,
        args.confidence_level,
        checks,
    )
    validate_source_qc(source_qc, args.expected_source_qc_rows, checks)
    combined = add_reference_period(pd.concat([monthly, weekly], ignore_index=True, sort=False))
    summary = summarize(combined, args.confidence_level)

    y_axis_limits = render_combined(
        combined,
        args.figure_output,
        combined_png,
        args.figure_width,
        args.figure_height,
        args.dpi,
    )
    render_temporal(combined, "month", monthly_pdf, monthly_png, args.figure_width, args.dpi)
    render_temporal(combined, "week", weekly_pdf, weekly_png, args.figure_width, args.dpi)

    combined.sort_values(
        ["time_unit", "scope", "detector", "specification", "event_time"]
    ).to_csv(plot_data_path, index=False, float_format="%.17g")
    summary.to_csv(summary_path, index=False, float_format="%.17g")
    checks_frame = pd.DataFrame(checks)
    checks_frame.to_csv(checks_path, index=False)
    require(checks_frame["pass"].all(), "At least one reporting reconciliation check failed")

    metadata = {
        "run_id": RUN_ID,
        "implementation_version": VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "script_sha256": sha256(Path(__file__)),
        "inputs": {
            label: {"path": str(path.resolve()), "sha256": sha256(path), "rows": len(source)}
            for (label, path), source in zip(
                input_paths.items(), (monthly_source, weekly_source, source_qc)
            )
        },
        "design": {
            "monthly_source": "run-x-b08-v4 recorded treatment month",
            "weekly_source": "run-x-b09-v2 exact first observable Cursor-related commit date",
            "detectors": list(DETECTORS),
            "scopes": list(SCOPES),
            "specifications": list(SPECIFICATIONS),
            "omitted_reference_period": -1,
            "reference_period_displayed_at_zero": True,
            "confidence_level": args.confidence_level,
            "inference": "pointwise normal confidence intervals; no multiplicity adjustment",
            "horizontal_offsets": {f"{key[0]}_{key[1]}": value for key, value in OFFSETS.items()},
            "common_y_axis_within_time_unit": True,
            "y_axis_limits": y_axis_limits,
        },
        "software": {
            "python": sys.version,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "arguments": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
        },
        "outputs": {
            str(path.resolve()): sha256(path)
            for path in targets
            if path != metadata_path
        },
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(f"Validated monthly effects: {len(monthly)} rows")
    print(f"Validated weekly effects:  {len(weekly)} rows")
    for row in summary.itertuples(index=False):
        print(
            f"{row.time_unit} {row.detector}/{row.scope} {row.specification}: "
            f"significant pre={row.pointwise_significant_pre_periods}; "
            f"significant post={row.pointwise_significant_post_periods}; "
            f"event 0={row.event_0_estimate:.3f} (p={row.event_0_p_value:.4g})"
        )
    print(f"PASS: {len(checks_frame)} reconciliation checks")
    print(f"Figure: {args.figure_output}")
    print(f"Preview: {combined_png}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, pd.errors.ParserError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
