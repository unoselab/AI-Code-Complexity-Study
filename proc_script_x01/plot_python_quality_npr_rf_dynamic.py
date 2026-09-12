#!/usr/bin/env python3
"""Create RF NPR threshold-sensitivity event-study figures.

The script reads completed Borusyak DiD estimates. It does not estimate the
models again and has no dependency on an upstream shell wrapper.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from statistics import NormalDist

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


IMPLEMENTATION_VERSION = "v1"
DEFAULT_OUTPUT_NAMES = {
    ("adjusted_burden", "below"): "fig_did_quality_npr_rf_dynamic-fecs-below-v1.pdf",
    ("adjusted_burden", "at_or_above"): "fig_did_quality_npr_rf_dynamic-fecs-primary-above-v1.pdf",
    ("fe_only_burden", "below"): "fig_did_quality_npr_rf_dynamic-feos-below-v1.pdf",
    ("fe_only_burden", "at_or_above"): "fig_did_quality_npr_rf_dynamic-feos-primary-above-v1.pdf",
}
REQUIRED_COLUMNS = {
    "sample_spec",
    "threshold_role",
    "threshold",
    "delta_from_primary",
    "event_time",
    "scope_id",
    "model_spec",
    "outcome",
    "estimate",
    "std.error",
    "conf.low",
    "conf.high",
    "term_present",
    "model_status",
    "sparse_support_flag",
}

# Match the manuscript styling of
# plot_did_quality_fun_npr_dynamic_4panel-v7.py. Eleven marker shapes are
# available because the at-or-above panel can contain the primary threshold
# and ten higher thresholds.
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "<", ">", "*", "h"]
FIGURE_SIZE_INCHES = (3.45, 2.75)
TIGHT_LAYOUT_PAD = 0.45


def configure_matplotlib() -> None:
    """Apply the compact typography used by the manuscript figures."""
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 8.0,
            "axes.labelsize": 8.0,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 7.5,
            "axes.linewidth": 0.7,
            "lines.linewidth": 1.2,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot NPR-localized RF issue-burden event-study estimates."
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument("--figure-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--sample-spec", default="exclude_scope_mismatch_repos")
    parser.add_argument("--scope-id", default="rf")
    parser.add_argument("--fecs-spec", default="adjusted_burden")
    parser.add_argument("--feos-spec", default="fe_only_burden")
    parser.add_argument("--outcome", default="log1p_selected_issue_total")
    parser.add_argument("--primary-threshold", type=float, default=1.515059)
    parser.add_argument("--threshold-radius", type=float, default=0.50)
    parser.add_argument("--threshold-step", type=float, default=0.05)
    parser.add_argument("--event-min", type=int, default=-6)
    parser.add_argument("--event-max", type=int, default=6)
    parser.add_argument("--reference-event", type=int, default=-1)
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument(
        "--threshold-x-spread",
        type=float,
        default=0.48,
        help=(
            "Total horizontal spread, in event-month units, used to separate "
            "threshold estimates within each event month. Default: 0.48."
        ),
    )
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument(
        "--show-axis-labels",
        action="store_true",
        help="Show x/y axis titles. The default omits them for the composite manuscript figure.",
    )
    parser.add_argument(
        "--no-legends",
        action="store_true",
        help="Suppress the threshold legend inside each panel.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if not args.self_test:
        missing = [name for name in ("input", "figure_dir", "output_dir") if getattr(args, name) is None]
        if missing:
            parser.error("the following arguments are required: " + ", ".join(f"--{x.replace('_', '-')}" for x in missing))
    if not 0.0 <= args.threshold_x_spread < 1.0:
        parser.error("--threshold-x-spread must be at least 0 and less than 1")
    return args


def as_bool(series: pd.Series, column: str) -> pd.Series:
    values = series.astype(str).str.strip().str.lower()
    mapping = {"true": True, "false": False, "1": True, "0": False}
    invalid = sorted(set(values) - set(mapping))
    if invalid:
        raise ValueError(f"{column} contains invalid Boolean values: {invalid}")
    return values.map(mapping).astype(bool)


def expected_events(event_min: int, event_max: int, reference_event: int) -> list[int]:
    return [event for event in range(event_min, event_max + 1) if event != reference_event]


def expected_thresholds(primary: float, radius: float, step: float) -> np.ndarray:
    if radius <= 0 or step <= 0:
        raise ValueError("threshold-radius and threshold-step must be positive")
    steps = radius / step
    if not math.isclose(steps, round(steps), abs_tol=1e-9):
        raise ValueError("threshold-radius must be an integer multiple of threshold-step")
    count = int(round(steps))
    return np.array([primary + offset * step for offset in range(-count, count + 1)])


def load_and_validate(args: argparse.Namespace) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    frame = pd.read_csv(args.input)
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"input is missing required columns: {missing}")

    numeric_columns = [
        "threshold",
        "delta_from_primary",
        "event_time",
        "estimate",
        "std.error",
        "conf.low",
        "conf.high",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame["term_present"] = as_bool(frame["term_present"], "term_present")
    frame["sparse_support_flag"] = as_bool(frame["sparse_support_flag"], "sparse_support_flag")

    model_specs = [args.fecs_spec, args.feos_spec]
    allowed_roles = {"sensitivity_grid", "primary"}
    lower = args.primary_threshold - args.threshold_radius
    upper = args.primary_threshold + args.threshold_radius
    tolerance = max(1e-8, args.threshold_step * 1e-6)
    selected = frame.loc[
        (frame["sample_spec"] == args.sample_spec)
        & (frame["scope_id"].str.lower() == args.scope_id.lower())
        & (frame["model_spec"].isin(model_specs))
        & (frame["outcome"] == args.outcome)
        & (frame["threshold_role"].isin(allowed_roles))
        & (frame["threshold"] >= lower - tolerance)
        & (frame["threshold"] <= upper + tolerance)
    ].copy()
    if selected.empty:
        raise ValueError("no rows remain after applying the requested analysis filters")

    checks: list[dict[str, object]] = []

    def record(name: str, passed: bool, observed: object, expected: object) -> None:
        checks.append(
            {"check": name, "passed": bool(passed), "observed": observed, "expected": expected}
        )
        if not passed:
            raise ValueError(f"{name} failed: observed={observed!r}, expected={expected!r}")

    record("all_model_status_success", bool((selected["model_status"] == "success").all()), sorted(selected["model_status"].unique()), ["success"])
    record("all_terms_present", bool(selected["term_present"].all()), int(selected["term_present"].sum()), len(selected))
    record("finite_estimates", bool(np.isfinite(selected[["estimate", "std.error", "conf.low", "conf.high"]].to_numpy()).all()), "finite" if np.isfinite(selected[["estimate", "std.error", "conf.low", "conf.high"]].to_numpy()).all() else "non-finite", "finite")
    record("nonnegative_standard_errors", bool((selected["std.error"] >= 0).all()), float(selected["std.error"].min()), ">= 0")
    record("ordered_confidence_intervals", bool(((selected["conf.low"] <= selected["estimate"]) & (selected["estimate"] <= selected["conf.high"])).all()), "ordered", "conf.low <= estimate <= conf.high")

    duplicate_columns = ["sample_spec", "scope_id", "model_spec", "outcome", "threshold", "event_time"]
    duplicate_count = int(selected.duplicated(duplicate_columns, keep=False).sum())
    record("unique_model_threshold_event_rows", duplicate_count == 0, duplicate_count, 0)

    actual_thresholds = np.array(sorted(selected["threshold"].unique()))
    wanted_thresholds = expected_thresholds(args.primary_threshold, args.threshold_radius, args.threshold_step)
    threshold_match = len(actual_thresholds) == len(wanted_thresholds) and np.allclose(actual_thresholds, wanted_thresholds, atol=tolerance, rtol=0)
    record("complete_prespecified_threshold_grid", threshold_match, [round(x, 6) for x in actual_thresholds], [round(x, 6) for x in wanted_thresholds])

    wanted_events = expected_events(args.event_min, args.event_max, args.reference_event)
    for model_spec in model_specs:
        for threshold in wanted_thresholds:
            group = selected.loc[
                (selected["model_spec"] == model_spec)
                & np.isclose(selected["threshold"], threshold, atol=tolerance, rtol=0)
            ]
            actual_events = sorted(group["event_time"].astype(int).tolist())
            record(
                f"complete_event_grid::{model_spec}::{threshold:.6f}",
                actual_events == wanted_events,
                actual_events,
                wanted_events,
            )

    primary_rows = selected.loc[np.isclose(selected["threshold"], args.primary_threshold, atol=tolerance, rtol=0)]
    record("primary_threshold_present_for_both_models", primary_rows["model_spec"].nunique() == 2, int(primary_rows["model_spec"].nunique()), 2)
    record("primary_threshold_role", bool((primary_rows["threshold_role"] == "primary").all()), sorted(primary_rows["threshold_role"].unique()), ["primary"])

    z_value = NormalDist().inv_cdf(0.5 + args.confidence_level / 2.0)
    reconstructed_low = selected["estimate"] - z_value * selected["std.error"]
    reconstructed_high = selected["estimate"] + z_value * selected["std.error"]
    ci_tolerance = 5e-6
    ci_match = np.allclose(selected["conf.low"], reconstructed_low, atol=ci_tolerance, rtol=0) and np.allclose(selected["conf.high"], reconstructed_high, atol=ci_tolerance, rtol=0)
    record("confidence_interval_reconciliation", ci_match, "matches" if ci_match else "mismatch", f"estimate +/- {z_value:.6f} * SE")

    selected["event_time"] = selected["event_time"].astype(int)
    selected["specification"] = selected["model_spec"].map(
        {args.fecs_spec: "FECS", args.feos_spec: "FEOS"}
    )
    selected["threshold_group"] = np.where(
        selected["threshold"] < args.primary_threshold - tolerance,
        "below",
        "at_or_above",
    )
    return selected.sort_values(["model_spec", "threshold", "event_time"]), checks


def add_reference_rows(frame: pd.DataFrame, reference_event: int) -> pd.DataFrame:
    references = frame.drop_duplicates(["model_spec", "threshold"]).copy()
    references["event_time"] = reference_event
    references["estimate"] = 0.0
    references["std.error"] = 0.0
    references["conf.low"] = 0.0
    references["conf.high"] = 0.0
    references["is_visual_reference"] = True
    result = frame.copy()
    result["is_visual_reference"] = False
    return pd.concat([result, references], ignore_index=True).sort_values(
        ["model_spec", "threshold", "event_time"]
    )


def atomic_save_figure(fig: plt.Figure, destination: Path, dpi: int, overwrite: bool) -> None:
    if destination.exists() and not overwrite:
        raise FileExistsError(f"output exists; use --overwrite to replace it: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=destination.stem + ".", suffix=destination.suffix, dir=destination.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        fig.savefig(
            temporary,
            format=destination.suffix.lstrip("."),
            dpi=dpi,
            bbox_inches="tight",
        )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def threshold_x_offsets(
    thresholds: np.ndarray,
    primary_threshold: float,
    total_spread: float,
) -> dict[float, float]:
    """Return small within-month offsets for visually separating thresholds.

    The primary threshold remains at the nominal event month. Other thresholds
    are distributed symmetrically around it. Panels without the primary
    threshold use the same symmetric distribution for all thresholds.
    """
    threshold_values = [float(value) for value in thresholds]
    if len(threshold_values) == 1 or math.isclose(total_spread, 0.0, abs_tol=1e-12):
        return {value: 0.0 for value in threshold_values}

    primary = next(
        (
            value
            for value in threshold_values
            if math.isclose(value, primary_threshold, abs_tol=1e-8)
        ),
        None,
    )
    if primary is None:
        offsets = np.linspace(-total_spread / 2.0, total_spread / 2.0, len(threshold_values))
        return {value: float(offset) for value, offset in zip(threshold_values, offsets)}

    non_primary = [value for value in threshold_values if value != primary]
    candidate_offsets = np.linspace(
        -total_spread / 2.0,
        total_spread / 2.0,
        len(non_primary) + 1,
    )
    center_index = int(np.argmin(np.abs(candidate_offsets)))
    non_primary_offsets = np.delete(candidate_offsets, center_index)
    mapping = {
        value: float(offset)
        for value, offset in zip(non_primary, non_primary_offsets)
    }
    mapping[primary] = 0.0
    return mapping


def plot_panel(
    frame: pd.DataFrame,
    model_spec: str,
    threshold_group: str,
    args: argparse.Namespace,
    y_limits: tuple[float, float],
) -> Path:
    panel = frame.loc[
        (frame["model_spec"] == model_spec)
        & (frame["threshold_group"] == threshold_group)
    ].copy()
    if panel.empty:
        raise ValueError(f"empty plot panel: {model_spec}/{threshold_group}")

    thresholds = np.array(sorted(panel["threshold"].unique()))
    cmap = plt.get_cmap("viridis")
    colors = [cmap(index / max(1, len(thresholds) - 1)) for index in range(len(thresholds))]
    x_offsets = threshold_x_offsets(
        thresholds,
        args.primary_threshold,
        args.threshold_x_spread,
    )

    has_primary = any(
        math.isclose(threshold, args.primary_threshold, abs_tol=1e-8)
        for threshold in thresholds
    )
    if has_primary:
        non_primary_markers = [marker for marker in MARKERS if marker != "o"]
        if len(thresholds) - 1 > len(non_primary_markers):
            raise ValueError("not enough distinct marker shapes for the threshold panel")
    elif len(thresholds) > len(MARKERS):
        raise ValueError("not enough distinct marker shapes for the threshold panel")

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_INCHES)
    legend_handles: list[Line2D] = []
    non_primary_index = 0

    for index, threshold in enumerate(thresholds):
        group = panel.loc[np.isclose(panel["threshold"], threshold)].sort_values("event_time")
        is_primary = math.isclose(threshold, args.primary_threshold, abs_tol=1e-8)
        color = "black" if is_primary else colors[index]
        if is_primary:
            marker = "o"
        elif has_primary:
            marker = non_primary_markers[non_primary_index]
            non_primary_index += 1
        else:
            marker = MARKERS[index]
        marker_size = 5.8 if is_primary else 5.0
        yerr = np.vstack(
            [group["estimate"].to_numpy() - group["conf.low"].to_numpy(),
             group["conf.high"].to_numpy() - group["estimate"].to_numpy()]
        )
        event_positions = group["event_time"].to_numpy(dtype=float) + x_offsets[float(threshold)]
        ax.errorbar(
            event_positions,
            group["estimate"],
            yerr=yerr,
            fmt=marker,
            linestyle="none",
            color=color,
            ecolor=color,
            elinewidth=1.10 if is_primary else 0.70,
            capsize=2.4 if is_primary else 1.8,
            markersize=marker_size,
            alpha=0.88 if is_primary else 0.70,
            zorder=5 if is_primary else 2,
        )

        label = f"{threshold:.6f}"
        if is_primary:
            label += " (P)"
        legend_handles.append(
            Line2D(
                [0],
                [0],
                color=color,
                marker=marker,
                linestyle="None",
                markersize=marker_size,
                label=label,
            )
        )

    ax.axhline(0.0, linewidth=0.8, color="0.35", zorder=1)
    ax.axvline(-0.5, linewidth=0.8, linestyle=":", color="0.35", zorder=1)
    ax.set_xlim(args.event_min - 0.55, args.event_max + 0.55)
    ax.set_ylim(*y_limits)
    ax.set_xticks(list(range(args.event_min, args.event_max + 1)))
    ax.tick_params(axis="both", labelsize=8)
    ax.grid(axis="y", linewidth=0.4, alpha=0.35)
    ax.set_axisbelow(True)

    if args.show_axis_labels:
        ax.set_xlabel("Event month")
        ax.set_ylabel("ATT")
    if not args.no_legends:
        ax.legend(
            handles=legend_handles,
            loc="upper left",
            bbox_to_anchor=(0.015, 0.985),
            ncol=2,
            fontsize=5.3,
            frameon=True,
            framealpha=0.85,
            borderpad=0.35,
            handlelength=1.0,
            columnspacing=0.7,
            handletextpad=0.30,
        )

    fig.tight_layout(pad=TIGHT_LAYOUT_PAD)
    destination = args.figure_dir / DEFAULT_OUTPUT_NAMES[(model_spec, threshold_group)]
    atomic_save_figure(fig, destination, args.dpi, args.overwrite)
    plt.close(fig)
    return destination


def write_outputs(
    frame: pd.DataFrame,
    checks: list[dict[str, object]],
    figure_paths: list[Path],
    args: argparse.Namespace,
) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data_path = args.output_dir / "python_quality_npr_rf_dynamic_plot_data.csv"
    checks_path = args.output_dir / "python_quality_npr_rf_dynamic_plot_checks.csv"
    manifest_path = args.output_dir / "python_quality_npr_rf_dynamic_plot_manifest.json"
    for path in (data_path, checks_path, manifest_path):
        if path.exists() and not args.overwrite:
            raise FileExistsError(f"output exists; use --overwrite to replace it: {path}")

    frame.to_csv(data_path, index=False)
    pd.DataFrame(checks).to_csv(checks_path, index=False)
    manifest = {
        "implementation_version": IMPLEMENTATION_VERSION,
        "input": str(args.input.resolve()),
        "sample_spec": args.sample_spec,
        "scope_id": args.scope_id,
        "outcome": args.outcome,
        "fecs_spec": args.fecs_spec,
        "feos_spec": args.feos_spec,
        "primary_threshold": args.primary_threshold,
        "threshold_radius": args.threshold_radius,
        "threshold_step": args.threshold_step,
        "confidence_level": args.confidence_level,
        "threshold_x_spread": args.threshold_x_spread,
        "visual_reference_event": args.reference_event,
        "figure_files": [str(path.resolve()) for path in figure_paths],
        "rows": int(len(frame)),
        "checks": int(len(checks)),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> list[Path]:
    configure_matplotlib()
    frame, checks = load_and_validate(args)
    frame = add_reference_rows(frame, args.reference_event)
    ci_values = np.concatenate([frame["conf.low"].to_numpy(), frame["conf.high"].to_numpy()])
    data_min = float(np.nanmin(ci_values))
    data_max = float(np.nanmax(ci_values))
    span = max(data_max - data_min, 0.2)
    y_limits = (min(-0.05, data_min - 0.06 * span), max(0.05, data_max + 0.06 * span))

    paths: list[Path] = []
    for model_spec in (args.fecs_spec, args.feos_spec):
        for threshold_group in ("below", "at_or_above"):
            paths.append(plot_panel(frame, model_spec, threshold_group, args, y_limits))
    write_outputs(frame, checks, paths, args)
    return paths


def build_self_test_csv(path: Path) -> None:
    primary = 1.515059
    rows: list[dict[str, object]] = []
    z_value = NormalDist().inv_cdf(0.975)
    for model_index, model_spec in enumerate(("adjusted_burden", "fe_only_burden")):
        for offset in range(-10, 11):
            threshold = primary + 0.05 * offset
            role = "primary" if offset == 0 else "sensitivity_grid"
            for event in expected_events(-6, 6, -1):
                estimate = 0.02 * event + 0.01 * offset + 0.04 * model_index
                standard_error = 0.08 + 0.002 * abs(offset)
                rows.append(
                    {
                        "sample_spec": "exclude_scope_mismatch_repos",
                        "threshold_role": role,
                        "threshold": threshold,
                        "delta_from_primary": 0.05 * offset,
                        "event_time": event,
                        "scope_id": "rf",
                        "model_spec": model_spec,
                        "outcome": "log1p_selected_issue_total",
                        "estimate": estimate,
                        "std.error": standard_error,
                        "conf.low": estimate - z_value * standard_error,
                        "conf.high": estimate + z_value * standard_error,
                        "term_present": True,
                        "model_status": "success",
                        "sparse_support_flag": offset >= 3,
                    }
                )
    pd.DataFrame(rows).to_csv(path, index=False)


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="npr-rf-dynamic-self-test-") as temporary:
        root = Path(temporary)
        input_path = root / "input.csv"
        build_self_test_csv(input_path)
        args = parse_args(
            [
                "--input", str(input_path),
                "--figure-dir", str(root / "figure"),
                "--output-dir", str(root / "output"),
                "--overwrite",
            ]
        )
        paths = run(args)
        if len(paths) != 4 or not all(path.exists() and path.stat().st_size > 0 for path in paths):
            raise RuntimeError("self-test did not create all four PDF figures")
    print("PASS: self-test")


def main() -> int:
    args = parse_args()
    try:
        if args.self_test:
            self_test()
            return 0
        paths = run(args)
        print(f"PASS: created {len(paths)} NPR RF dynamic figure panels")
        for path in paths:
            print(f"Figure: {path}")
        print(f"Outputs: {args.output_dir}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
