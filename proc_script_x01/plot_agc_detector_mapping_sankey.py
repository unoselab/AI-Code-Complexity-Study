#!/usr/bin/env python3
"""Plot the NPR-vs-ML AGC detector mapping as a publication Sankey figure.

Inputs are the validated run-x-f06 detector-mapping CSV artifacts. The Sankey
universe contains repo-month Python file occurrences selected by at least one
frozen detector. Flow width is proportional to repo-month file occurrences.

The plot intentionally excludes files selected by neither detector because the
figure is designed to show the relationship between the two positive detector
subsets, not the full background Python-file universe.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch, Rectangle
import pandas as pd


REQUIRED_CLASSES = ("Both", "NPR-only", "ML-only")
EXPECTED_FLOW_UNIT = "repo_month_file_occurrences"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot the frozen NPR-vs-ML detector mapping Sankey figure."
    )
    parser.add_argument("--edges-file", required=True)
    parser.add_argument("--summary-file", required=True)
    parser.add_argument("--qc-file", required=True)
    parser.add_argument("--metadata-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--output-prefix",
        default="fig_agc_detector_mapping_sankey-v1",
        help="Filename prefix for PDF/PNG outputs.",
    )
    parser.add_argument("--width-inches", type=float, default=3.35)
    parser.add_argument("--height-inches", type=float, default=2.70)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--expected-union", type=int, default=53445)
    parser.add_argument("--expected-both", type=int, default=3619)
    parser.add_argument("--expected-npr-only", type=int, default=10120)
    parser.add_argument("--expected-ml-only", type=int, default=39706)
    parser.add_argument(
        "--expected-jaccard", type=float, default=0.06771447282252784
    )
    return parser.parse_args()


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def validate_qc(qc: pd.DataFrame) -> None:
    if "status" not in qc.columns:
        fail("QC file is missing the status column")
    failed = qc.loc[qc["status"].astype(str).str.lower() == "fail"]
    if not failed.empty:
        checks = failed.get("check", pd.Series(dtype=str)).astype(str).tolist()
        fail(f"run-x-f06 hard QC contains failures: {checks}")


def validate_edges(
    edges: pd.DataFrame,
    expected_counts: Dict[str, int],
    expected_union: int,
) -> pd.DataFrame:
    required = {
        "mapping_class",
        "file_occurrences",
        "unique_historical_files",
        "issue_stock",
        "share_of_union_file_occurrences",
        "primary_flow_value",
        "primary_flow_unit",
    }
    missing = sorted(required - set(edges.columns))
    if missing:
        fail(f"Sankey edge file is missing columns: {missing}")

    if edges["mapping_class"].duplicated().any():
        fail("Sankey edge file contains duplicate mapping classes")

    classes = set(edges["mapping_class"].astype(str))
    if classes != set(REQUIRED_CLASSES):
        fail(f"Unexpected mapping classes: {sorted(classes)}")

    edges = edges.copy()
    for column in (
        "file_occurrences",
        "unique_historical_files",
        "issue_stock",
        "share_of_union_file_occurrences",
        "primary_flow_value",
    ):
        edges[column] = pd.to_numeric(edges[column], errors="raise")

    if not (edges["primary_flow_unit"].astype(str) == EXPECTED_FLOW_UNIT).all():
        fail(f"Expected primary flow unit {EXPECTED_FLOW_UNIT}")
    if not (edges["primary_flow_value"] == edges["file_occurrences"]).all():
        fail("primary_flow_value must equal file_occurrences for every edge")
    if (edges["file_occurrences"] <= 0).any():
        fail("All Sankey flows must have positive file-occurrence counts")

    observed_union = int(edges["file_occurrences"].sum())
    if observed_union != expected_union:
        fail(f"Union count mismatch: expected {expected_union}, observed {observed_union}")

    for mapping_class, expected in expected_counts.items():
        observed = int(
            edges.loc[edges["mapping_class"] == mapping_class, "file_occurrences"].iloc[0]
        )
        if observed != expected:
            fail(
                f"{mapping_class} count mismatch: expected {expected}, observed {observed}"
            )

    share_sum = float(edges["share_of_union_file_occurrences"].sum())
    if not math.isclose(share_sum, 1.0, rel_tol=0.0, abs_tol=1e-12):
        fail(f"Union shares must sum to 1.0, observed {share_sum:.15f}")

    return edges.set_index("mapping_class").loc[list(REQUIRED_CLASSES)].reset_index()


def read_summary(summary: pd.DataFrame, expected_union: int, expected_jaccard: float) -> float:
    required = {
        "selection",
        "file_occurrences",
        "jaccard_npr_ml",
        "npr_overlap_share",
        "ml_overlap_share",
    }
    missing = sorted(required - set(summary.columns))
    if missing:
        fail(f"Summary file is missing columns: {missing}")

    union_rows = summary.loc[summary["selection"].astype(str) == "Union"]
    if len(union_rows) != 1:
        fail("Summary must contain exactly one Union row")
    union_count = int(pd.to_numeric(union_rows["file_occurrences"], errors="raise").iloc[0])
    if union_count != expected_union:
        fail(f"Summary union mismatch: expected {expected_union}, observed {union_count}")

    jaccard = float(pd.to_numeric(union_rows["jaccard_npr_ml"], errors="raise").iloc[0])
    if not math.isclose(jaccard, expected_jaccard, rel_tol=0.0, abs_tol=1e-12):
        fail(
            f"Jaccard mismatch: expected {expected_jaccard:.15f}, observed {jaccard:.15f}"
        )
    return jaccard


def read_thresholds(metadata: pd.DataFrame) -> Tuple[str, str]:
    if not {"section", "metric", "value"}.issubset(metadata.columns):
        fail("Metadata file must contain section, metric, and value columns")
    lookup = dict(zip(metadata["metric"].astype(str), metadata["value"].astype(str)))
    npr_rule = lookup.get("npr_rule", "NPR primary rule")
    ml_rule = lookup.get("ml_rule", "ML primary rule")
    return npr_rule, ml_rule


def band_patch(
    x0: float,
    x1: float,
    y0_bottom: float,
    y0_top: float,
    y1_bottom: float,
    y1_top: float,
    color,
    alpha: float = 0.58,
) -> PathPatch:
    """Create a smooth filled Sankey band between two vertical intervals."""
    curvature = 0.42 * (x1 - x0)
    vertices = [
        (x0, y0_bottom),
        (x0 + curvature, y0_bottom),
        (x1 - curvature, y1_bottom),
        (x1, y1_bottom),
        (x1, y1_top),
        (x1 - curvature, y1_top),
        (x0 + curvature, y0_top),
        (x0, y0_top),
        (x0, y0_bottom),
    ]
    codes = [
        MplPath.MOVETO,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.LINETO,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CLOSEPOLY,
    ]
    return PathPatch(
        MplPath(vertices, codes),
        facecolor=color,
        edgecolor="none",
        alpha=alpha,
        zorder=1,
    )


def interval_center(interval: Tuple[float, float]) -> float:
    return 0.5 * (interval[0] + interval[1])


def draw_node(
    ax,
    x: float,
    interval: Tuple[float, float],
    width: float,
    label: str,
    label_side: str,
) -> None:
    bottom, top = interval
    ax.add_patch(
        Rectangle(
            (x - width / 2, bottom),
            width,
            top - bottom,
            facecolor="white",
            edgecolor="black",
            linewidth=0.8,
            zorder=3,
        )
    )
    if not label:
        return
    dx = 0.018
    if label_side == "left":
        ax.text(
            x - width / 2 - dx,
            interval_center(interval),
            label,
            ha="right",
            va="center",
            fontsize=7.0,
            linespacing=1.05,
        )
    else:
        ax.text(
            x + width / 2 + dx,
            interval_center(interval),
            label,
            ha="left",
            va="center",
            fontsize=7.0,
            linespacing=1.05,
        )


def format_flow_label(mapping_class: str, count: int, share: float) -> str:
    display = {
        "Both": "Both",
        "NPR-only": "NPR only",
        "ML-only": "ML only",
    }[mapping_class]
    return f"{display}\n{count:,} ({share * 100:.1f}%)"


def write_plot_qc(
    output_path: Path,
    edges: pd.DataFrame,
    jaccard: float,
    pdf_path: Path,
    png_path: Path,
) -> None:
    rows: List[Dict[str, object]] = []
    for _, row in edges.iterrows():
        rows.append(
            {
                "check": f"flow_{row['mapping_class']}",
                "observed": int(row["file_occurrences"]),
                "status": "pass",
            }
        )
    rows.extend(
        [
            {
                "check": "union_total",
                "observed": int(edges["file_occurrences"].sum()),
                "status": "pass",
            },
            {"check": "jaccard", "observed": jaccard, "status": "pass"},
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
    )
    pd.DataFrame(rows).to_csv(output_path, index=False)


def write_metadata(
    output_path: Path,
    args: argparse.Namespace,
    jaccard: float,
    npr_rule: str,
    ml_rule: str,
) -> None:
    rows = [
        ("run", "experiment", "run-x-f07-plot-detector-mapping-figure"),
        ("run", "implementation_version", "v1"),
        ("input", "edges_file", str(args.edges_file)),
        ("input", "summary_file", str(args.summary_file)),
        ("input", "qc_file", str(args.qc_file)),
        ("input", "metadata_file", str(args.metadata_file)),
        ("figure", "primary_flow_unit", "repo-month historical Python file occurrence"),
        ("figure", "universe", "NPR selected OR ML selected"),
        ("figure", "excluded", "files selected by neither detector"),
        ("figure", "npr_rule", npr_rule),
        ("figure", "ml_rule", ml_rule),
        ("figure", "jaccard", f"{jaccard:.15f}"),
        ("figure", "width_inches", str(args.width_inches)),
        ("figure", "height_inches", str(args.height_inches)),
        ("figure", "dpi", str(args.dpi)),
        ("figure", "right_node_order", "ML not selected above ML selected to minimize crossing"),
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["section", "metric", "value"])
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    if args.width_inches <= 0 or args.height_inches <= 0 or args.dpi <= 0:
        fail("Figure dimensions and DPI must be positive")

    edges_path = Path(args.edges_file)
    summary_path = Path(args.summary_file)
    qc_path = Path(args.qc_file)
    metadata_path = Path(args.metadata_file)
    for path in (edges_path, summary_path, qc_path, metadata_path):
        if not path.is_file():
            fail(f"Required input file not found: {path}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    qc = pd.read_csv(qc_path)
    validate_qc(qc)

    expected_counts = {
        "Both": args.expected_both,
        "NPR-only": args.expected_npr_only,
        "ML-only": args.expected_ml_only,
    }
    edges = validate_edges(pd.read_csv(edges_path), expected_counts, args.expected_union)
    jaccard = read_summary(pd.read_csv(summary_path), args.expected_union, args.expected_jaccard)
    npr_rule, ml_rule = read_thresholds(pd.read_csv(metadata_path))

    row_by_class = {row["mapping_class"]: row for _, row in edges.iterrows()}
    both = int(row_by_class["Both"]["file_occurrences"])
    npr_only = int(row_by_class["NPR-only"]["file_occurrences"])
    ml_only = int(row_by_class["ML-only"]["file_occurrences"])
    union = both + npr_only + ml_only

    # Common scale keeps band widths identical at source and target nodes.
    x_left = 0.145
    x_right = 0.855
    node_width = 0.030
    y_top = 0.835
    y_bottom = 0.095
    inter_node_gap = 0.065
    usable_height = y_top - y_bottom - inter_node_gap
    scale = usable_height / union

    h_both = both * scale
    h_npr_only = npr_only * scale
    h_ml_only = ml_only * scale

    # Left order: NPR selected above NPR not selected.
    left_selected = (y_top - (h_npr_only + h_both), y_top)
    left_not_selected = (y_bottom, y_bottom + h_ml_only)

    # Right order is intentionally reversed to minimize flow crossings:
    # ML not-selected (NPR-only) above ML selected (Both + ML-only).
    right_not_selected = (y_top - h_npr_only, y_top)
    right_selected = (y_bottom, y_bottom + h_ml_only + h_both)

    # Flow sub-intervals within nodes.
    left_npr_only = (left_selected[1] - h_npr_only, left_selected[1])
    left_both = (left_selected[0], left_selected[0] + h_both)
    left_ml_only = left_not_selected

    right_npr_only = right_not_selected
    right_ml_only = (right_selected[0], right_selected[0] + h_ml_only)
    right_both = (right_selected[1] - h_both, right_selected[1])

    fig, ax = plt.subplots(figsize=(args.width_inches, args.height_inches))
    colors = {
        "NPR-only": "#845ec2",
        "Both": "#0089ba",
        "ML-only": "#008f7a",
    }

    # Draw the largest flows first; draw consensus last so it stays visible.
    ax.add_patch(
        band_patch(
            x_left + node_width / 2,
            x_right - node_width / 2,
            left_ml_only[0],
            left_ml_only[1],
            right_ml_only[0],
            right_ml_only[1],
            colors["ML-only"],
        )
    )
    ax.add_patch(
        band_patch(
            x_left + node_width / 2,
            x_right - node_width / 2,
            left_npr_only[0],
            left_npr_only[1],
            right_npr_only[0],
            right_npr_only[1],
            colors["NPR-only"],
        )
    )
    ax.add_patch(
        band_patch(
            x_left + node_width / 2,
            x_right - node_width / 2,
            left_both[0],
            left_both[1],
            right_both[0],
            right_both[1],
            colors["Both"],
            alpha=0.72,
        )
    )

    draw_node(ax, x_left, left_selected, node_width, "", "left")
    draw_node(ax, x_left, left_not_selected, node_width, "", "left")
    draw_node(ax, x_right, right_not_selected, node_width, "", "right")
    draw_node(ax, x_right, right_selected, node_width, "", "right")

    ax.text(
        x_left,
        0.955,
        "(a)",
        ha="center",
        va="center",
        fontsize=8.2,
        fontweight="bold",
    )
    ax.text(
        x_right,
        0.955,
        "(b)",
        ha="center",
        va="center",
        fontsize=8.2,
        fontweight="bold",
    )

    flow_labels = {
        "NPR-only": (
            0.50,
            interval_center(left_npr_only) * 0.52 + interval_center(right_npr_only) * 0.48,
        ),
        "Both": (
            0.50,
            interval_center(left_both) * 0.52 + interval_center(right_both) * 0.48,
        ),
        "ML-only": (
            0.50,
            interval_center(left_ml_only) * 0.52 + interval_center(right_ml_only) * 0.48,
        ),
    }
    for mapping_class in ("NPR-only", "Both", "ML-only"):
        row = row_by_class[mapping_class]
        ax.text(
            flow_labels[mapping_class][0],
            flow_labels[mapping_class][1],
            format_flow_label(
                mapping_class,
                int(row["file_occurrences"]),
                float(row["share_of_union_file_occurrences"]),
            ),
            ha="center",
            va="center",
            fontsize=6.3,
            fontweight="bold" if mapping_class == "Both" else "normal",
            bbox={"boxstyle": "round,pad=0.16", "facecolor": "white", "edgecolor": "none", "alpha": 0.82},
            zorder=5,
        )

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)

    pdf_path = output_dir / f"{args.output_prefix}.pdf"
    png_path = output_dir / f"{args.output_prefix}.png"
    fig.savefig(pdf_path, bbox_inches="tight", pad_inches=0.02)
    fig.savefig(png_path, dpi=args.dpi, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)

    plot_qc_path = output_dir / "agc_detector_mapping_plot_qc.csv"
    plot_metadata_path = output_dir / "agc_detector_mapping_plot_metadata.csv"
    write_plot_qc(plot_qc_path, edges, jaccard, pdf_path, png_path)
    write_metadata(plot_metadata_path, args, jaccard, npr_rule, ml_rule)

    plot_qc = pd.read_csv(plot_qc_path)
    if (plot_qc["status"] == "fail").any():
        fail("Plot output QC failed")

    print("run-x-f07 detector-mapping Sankey plot: PASS")
    print(f"Both: {both} ({both / union:.3%})")
    print(f"NPR-only: {npr_only} ({npr_only / union:.3%})")
    print(f"ML-only: {ml_only} ({ml_only / union:.3%})")
    print(f"Union: {union}")
    print(f"Jaccard: {jaccard:.6f}")
    print(f"PDF: {pdf_path}")
    print(f"PNG: {png_path}")
    print(f"Plot QC: {plot_qc_path}")


if __name__ == "__main__":
    main()
