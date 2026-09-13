#!/usr/bin/env python3
"""run-y-b11 v1: plot/report K12 v2 FECS GMM sweeps, without re-estimation.

Requires Python >=3.9, numpy, pandas, matplotlib. Coefficients describe lagged
localized log1p issue burden and subsequent log1p Python velocity, not DiD ATTs.
All 21 thresholds and source pointwise 95% normal CIs are retained unchanged.
P-values are unadjusted. A filled marker denotes the primary, not significance.
Only colors are adapted from the paper's NPR/ML RF+CM sensitivity-v3 PDFs.
No coefficients, model settings or thresholds are taken from K09/K10.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from statistics import NormalDist
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

VERSION = "v1"
FILES = {k: "dynamic_panel_gmm_localization_threshold_" + k + ".csv" for k in (
    "summary", "coefficients", "diagnostics", "instrument_qc", "support_diagnostics",
    "primary_reproduction", "qc", "run_metadata", "model_failures")}
KEY = ["detector", "scope_id", "threshold_id"]
SCOPES = {"rf": "RF", "cm": "CM", "rf_cm": "RF+CM"}
# Exact RGB colors extracted from the existing v3 figure PDFs.
PALETTE = ["#2c73d2", "#656dc8", "#8467bc", "#9a62ad", "#a85f9e"]
PRIMARY_COLOR = "#b15e8f"
FIELDS = ["estimate", "std_error", "conf_low", "conf_high", "p_value"]


def require(condition, message):
    if not bool(condition):
        raise ValueError(message)


def boolean(values):
    text = values.astype(str).str.strip().str.lower()
    require(text.isin(["true", "false", "1", "0"]).all(), "Invalid Boolean values")
    return text.isin(["true", "1"])


def numeric(frame, columns):
    for column in columns:
        require(column in frame, f"Missing required column: {column}")
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        require(np.isfinite(frame[column]).all(), f"Non-finite column: {column}")


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def keyed(frame, keys=KEY):
    require(set(keys).issubset(frame), f"Missing keys: {keys}")
    require(not frame.duplicated(keys).any(), f"Duplicate keys: {keys}")
    return frame.set_index(keys).sort_index()


def close(a, b, tolerance=1e-10):
    return np.allclose(np.asarray(a, dtype=float), np.asarray(b, dtype=float), rtol=0, atol=tolerance)


def validate(data, args):
    checks = []

    def check(name, ok):
        checks.append({"check": name, "status": "pass" if ok else "fail"})
        require(ok, "Reconciliation failed: " + name)

    summary = data["summary"].copy()
    numeric(summary, ["threshold", *FIELDS])
    check("126_summary_rows", len(summary) == 6 * args.expected_thresholds)
    check("six_detector_scope_pairs", set(zip(summary.detector, summary.scope_id)) ==
          {(d, s) for d in ("NPR", "ML") for s in SCOPES})
    check("FECS_only", summary.specification.eq("FECS").all())
    check("models_successful", summary.fit_status.eq("success").all())
    check("no_model_failures", data["model_failures"].empty)
    check("positive_SE", summary.std_error.gt(0).all())
    check("p_value_bounds", summary.p_value.between(0, 1).all())
    alpha = 1 - args.confidence_level
    z = NormalDist().inv_cdf(1 - alpha / 2)
    check("normal_CI_low", close(summary.conf_low, summary.estimate - z * summary.std_error))
    check("normal_CI_high", close(summary.conf_high, summary.estimate + z * summary.std_error))
    p = [math.erfc(abs(b / se) / math.sqrt(2)) for b, se in zip(summary.estimate, summary.std_error)]
    check("normal_p_values", close(summary.p_value, p))
    check("significance_flags", (boolean(summary.significant) == summary.p_value.lt(alpha)).all())
    sk = keyed(summary)
    coefficients = data["coefficients"]
    focal = coefficients.loc[boolean(coefficients.is_primary_interaction_term)].copy()
    check("focal_term", focal.term.eq("lag(log1p_selected_issue_total, 1)").all())
    check("focal_FECS", focal.specification.eq("FECS").all())
    fk = keyed(focal)
    check("coefficient_keys", sk.index.equals(fk.index))
    for field in ["threshold", *FIELDS]:
        check("coefficient_" + field, close(sk[field], fk[field]))
    support = keyed(data["support_diagnostics"])
    instruments = keyed(data["instrument_qc"])
    check("support_keys", sk.index.equals(support.index))
    check("instrument_keys", sk.index.equals(instruments.index))
    shared = set(sk.columns).intersection(support.columns) - {
        "localization_scope", "threshold_role", "source_output_dir"}
    for field in sorted(shared):
        check("support_" + field, close(sk[field], support[field]))
    expected = {"source_rows": 1954, "source_repositories": 167, "active_rows": 1631,
                "active_repositories": 146, "active_treatment_repositories": 61,
                "active_control_repositories": 85, "active_post_treatment_rows": 350}
    for field, value in expected.items():
        check("sample_" + field, support[field].eq(value).all())
    check("stats_nobs", close(instruments.stats_nobs, support.active_rows))
    check("instrument_thresholds", close(instruments.threshold, sk.threshold))
    check("instrument_count", instruments.instrument_count.eq(43).all())
    check("instrument_specification", instruments.instrument_specification.eq("lag(velocity,2)").all())
    check("instruments_uncollapsed", (~boolean(instruments.collapse)).all())
    check("instrument_ratio", close(instruments.instrument_to_repository_ratio,
                                     instruments.instrument_count / support.active_repositories))
    check("instrument_denominator", close(instruments.instrument_ratio_denominator, support.active_repositories))
    diagnostics = data["diagnostics"].copy()
    numeric(diagnostics, ["threshold", "statistic", "p_value", "warning_count"])
    dk = keyed(diagnostics, KEY + ["diagnostic"])
    check("diagnostic_rows", len(dk) == 3 * len(sk))
    check("diagnostic_names", set(diagnostics.diagnostic) == {"ar1", "ar2", "sargan"})
    check("diagnostics_available", diagnostics.status.eq("available").all())
    check("diagnostic_p_bounds", diagnostics.p_value.between(0, 1).all())
    for name in ("ar1", "ar2", "sargan"):
        part = dk.xs(name, level="diagnostic")
        check("diagnostic_keys_" + name, sk.index.equals(part.index))
        check("diagnostic_threshold_" + name, close(sk.threshold, part.threshold))
    qc = data["qc"]
    check("qc_unique", not qc.duplicated(KEY + ["check"]).any())
    check("qc_rows", len(qc) == 12 * len(sk))
    check("qc_no_hard_failure", qc.status.isin(["pass", "caution"]).all())
    check("qc_coverage", keyed(qc[KEY].drop_duplicates()).index.equals(sk.index))
    check("qc_checks_per_model", qc.groupby(KEY).size().eq(12).all())
    reproduction = data["primary_reproduction"].copy()
    numeric(reproduction, ["reference_value", "k12_primary_value", "absolute_difference", "tolerance"])
    check("reproduction_rows", len(reproduction) == 18)
    rp = keyed(reproduction, ["detector", "scope_id", "metric"])
    check("reproduction_keys", set(rp.index) == {(d, s, m) for d in ("NPR", "ML")
          for s in SCOPES for m in ("estimate", "std_error", "p_value")})
    check("reproduction_pass", reproduction.status.eq("pass").all())
    check("reproduction_tolerance", reproduction.absolute_difference.le(reproduction.tolerance).all()
          and reproduction.tolerance.gt(0).all() and reproduction.tolerance.le(1e-10).all())
    check("reproduction_numeric", close(reproduction.reference_value, reproduction.k12_primary_value))
    check("reproduction_difference", close(reproduction.absolute_difference,
          abs(reproduction.reference_value - reproduction.k12_primary_value), 1e-14))
    meta = data["run_metadata"]
    check("metadata_groups", meta.source_output_dir.nunique() == 6)
    for detector in ("NPR", "ML"):
        tag = detector.lower()
        lo, hi, step = (getattr(args, tag + "_" + suffix) for suffix in ("min", "max", "step"))
        primary = getattr(args, tag + "_primary")
        grid = np.round(lo + np.arange(args.expected_thresholds) * step, 6)
        check(tag + "_grid_endpoint", abs(grid[-1] - hi) < 1e-10)
        for scope, label in SCOPES.items():
            group = summary[(summary.detector == detector) & (summary.scope_id == scope)].sort_values("threshold")
            prefix = detector + "_" + scope + "_"
            check(prefix + "threshold_count", len(group) == args.expected_thresholds)
            check(prefix + "grid", close(group.threshold, grid))
            check(prefix + "scope_label", group.localization_scope.eq(label).all())
            mask = np.isclose(group.threshold, primary, rtol=0, atol=1e-10)
            check(prefix + "primary_unique", mask.sum() == 1)
            check(prefix + "primary_flag", (boolean(group.primary_analysis).to_numpy() == mask).all())
            row = group.loc[mask].iloc[0]
            for field in ("estimate", "std_error", "p_value"):
                check(prefix + "primary_" + field,
                      abs(float(rp.loc[(detector, scope, field), "k12_primary_value"]) - row[field]) < 1e-10)
            for field in ("selected_file_rows", "selected_issue_total"):
                check(prefix + field + "_nonincreasing", (np.diff(group[field]) <= 0).all())
            check(prefix + "metadata_dir", group.source_output_dir.nunique() == 1)
            subset = meta[meta.source_output_dir == group.source_output_dir.iloc[0]]
            require(not subset.duplicated(["section", "metric"]).any(), "Duplicate metadata")
            mm = dict(zip(subset.metric, subset.value.astype(str)))
            for field, value in {"run_prefix": "run-x-k12", "implementation_version": "v2",
                    "detector": detector, "scope_id": scope, "specification": "FECS",
                    "sample_spec": "full_sample", "threshold_operator": ">",
                    "gmm_effect": "twoways", "gmm_model": "twosteps", "gmm_transformation": "d",
                    "collapse": "FALSE", "velocity": "log_lines_added_py_source",
                    "localized_quality": "log1p_selected_issue_total"}.items():
                check(prefix + "metadata_" + field, mm.get(field) == value)
            for field, value in {"primary_threshold": primary, "threshold_min": lo,
                                 "threshold_max": hi, "threshold_step": step}.items():
                check(prefix + "metadata_" + field, abs(float(mm.get(field, "nan")) - value) < 1e-10)
    return summary, pd.DataFrame(checks)


def contiguous_runs(group, alpha):
    """Retain gaps in significant threshold sets; never report just min/max."""
    result, start = [], None
    rows = list(group.itertuples())
    for i in range(len(rows) + 1):
        significant = i < len(rows) and rows[i].p_value < alpha
        if significant and start is None:
            start = i
        if not significant and start is not None:
            result.append({"detector": rows[0].detector, "scope_id": rows[0].scope_id,
                           "threshold_start": rows[start].threshold,
                           "threshold_end": rows[i - 1].threshold, "threshold_count": i - start})
            start = None
    return result


def summaries(frame, diagnostics, args):
    series, runs, diag_rows = [], [], []
    for (d, s), group in frame.groupby(["detector", "scope_id"], sort=False):
        group = group.sort_values("threshold")
        primary = group.loc[boolean(group.primary_analysis)].iloc[0]
        first, last = group.iloc[0], group.iloc[-1]
        record = {"detector": d, "scope_id": s, "localization_scope": SCOPES[s],
                  "threshold_count": len(group), "negative_estimates": int(group.estimate.lt(0).sum()),
                  "significant_negative": int((group.estimate.lt(0) & group.p_value.lt(1-args.confidence_level)).sum()),
                  "significant_positive": int((group.estimate.gt(0) & group.p_value.lt(1-args.confidence_level)).sum()),
                  "primary_threshold": primary.threshold,
                  **{"primary_" + c: primary[c] for c in FIELDS},
                  "estimate_min": group.estimate.min(), "estimate_max": group.estimate.max(),
                  "inference": "pointwise; no multiplicity adjustment"}
        for field in ("selected_file_rows", "zero_issue_share_active",
                      "repositories_with_within_quality_variation_active"):
            record[field + "_lowest_threshold"] = first[field]
            record[field + "_highest_threshold"] = last[field]
        series.append(record)
        runs.extend(contiguous_runs(group, 1 - args.confidence_level))
        for name in ("ar1", "ar2", "sargan"):
            part = diagnostics[(diagnostics.detector == d) & (diagnostics.scope_id == s) & (diagnostics.diagnostic == name)]
            diag_rows.append({"detector": d, "scope_id": s, "diagnostic": name,
                "p_min": part.p_value.min(), "p_max": part.p_value.max(),
                "p_below_005_count": int(part.p_value.lt(.05).sum()), "models": len(part)})
    return pd.DataFrame(series), pd.DataFrame(runs, columns=["detector", "scope_id",
          "threshold_start", "threshold_end", "threshold_count"]), pd.DataFrame(diag_rows)


def draw_panel(ax, group, primary, label, ylabel=True):
    x, y = group.threshold.to_numpy(), group.estimate.to_numpy()
    lo, hi = group.conf_low.to_numpy(), group.conf_high.to_numpy()
    primary_index = int(np.flatnonzero(np.isclose(x, primary, rtol=0, atol=1e-10))[0])
    ax.plot(x, y, color="#c7c7c7", lw=1.0, zorder=1)
    for i in range(len(group)):
        distance = abs(i - primary_index)
        color = PRIMARY_COLOR if distance == 0 else PALETTE[4 - (distance - 1) // 2]
        ax.errorbar(x[i], y[i], yerr=[[y[i]-lo[i]], [hi[i]-y[i]]], fmt="o",
                    ms=5.0 if distance == 0 else 3.1,
                    mfc=PRIMARY_COLOR if distance == 0 else "white",
                    mec=PRIMARY_COLOR if distance == 0 else PALETTE[2],
                    mew=.9, ecolor=color, elinewidth=1.1, capsize=1.8, zorder=4)
    ax.axhline(0, color=PALETTE[3], ls=(0, (2, 2)), lw=.8, zorder=0)
    ax.axvline(primary, color=PRIMARY_COLOR, ls=(0, (4, 2)), lw=.8, zorder=0)
    span = max(float(hi.max()), 0) - min(float(lo.min()), 0)
    pad = max(.05, .07 * span)
    ax.set_ylim(min(float(lo.min()), 0)-pad, max(float(hi.max()), 0)+pad)
    ax.set_xlim(x[0] - (x[1]-x[0])*.45, x[-1] + (x[1]-x[0])*.45)
    indices = sorted(set([0, 5, 10, 15, 20, primary_index]))
    ax.set_xticks(x[indices], [f"{v:.2f}" for v in x[indices]])
    ax.set_xlabel(group.detector.iloc[0] + r" threshold ($\tau$)", labelpad=3)
    ax.set_title(label, loc="left", fontsize=8.5, pad=5)
    if ylabel:
        ax.set_ylabel(r"GMM coefficient ($\hat{\gamma}$)", labelpad=3)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(direction="out", length=2.5, width=.7, pad=2)
    return ax.get_ylim()


def render(frame, args):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.labelsize": 8,
                         "xtick.labelsize": 7, "ytick.labelsize": 7, "pdf.fonttype": 42, "ps.fonttype": 42})
    fig, axes = plt.subplots(2, 3, figsize=(args.figure_width, args.figure_height))
    fig.subplots_adjust(left=.085, right=.99, bottom=.17, top=.94, wspace=.32, hspace=.60)
    limits = []
    for i, detector in enumerate(("NPR", "ML")):
        for j, (scope, label) in enumerate(SCOPES.items()):
            group = frame[(frame.detector == detector) & (frame.scope_id == scope)].sort_values("threshold")
            primary = getattr(args, detector.lower() + "_primary")
            title = f"({chr(97 + i*3+j)}) {detector}: {label}"
            lower, upper = draw_panel(axes[i, j], group, primary, title, ylabel=j == 0)
            limits.append({"detector": detector, "scope_id": scope, "y_min": lower, "y_max": upper})
            single, ax = plt.subplots(figsize=(3.45, 2.55))
            draw_panel(ax, group, primary, title)
            single.tight_layout(pad=.6)
            for ext in ("pdf", "png"):
                single.savefig(args.figure_dir / f"fig_gmm_{detector.lower()}_{scope}_threshold_sensitivity-{VERSION}.{ext}", dpi=args.dpi)
            plt.close(single)
    handles = [Line2D([], [], color=PALETTE[2], marker="o", mfc="white", ls="none", ms=4,
                      label="Estimate with 95% CI"),
               Line2D([], [], color=PRIMARY_COLOR, marker="o", ls="--", ms=5, label="Primary threshold")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.52, .04), ncol=2, frameon=False, fontsize=7.5)
    fig.text(.52, .01, "Primary thresholds: NPR = 1.515059; ML = 0.50. Y-axis ranges vary by panel.", ha="center", fontsize=7)
    for ext in ("pdf", "png"):
        fig.savefig(args.figure_dir / f"fig_gmm_localization_threshold_sensitivity-{VERSION}.{ext}", dpi=args.dpi)
    plt.close(fig)
    return limits


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("input-root", "output-root", "figure-dir", "output-tex"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--implementation-version", choices=[VERSION], default=VERSION)
    for name, default in {"npr-primary": 1.515059, "npr-min": 1.015059, "npr-max": 2.015059,
            "npr-step": .05, "ml-primary": .5, "ml-min": .1, "ml-max": .9, "ml-step": .04,
            "confidence-level": .95, "figure-width": 7.1, "figure-height": 4.6}.items():
        parser.add_argument("--" + name, type=float, default=default)
    parser.add_argument("--expected-thresholds", type=int, choices=[21], default=21)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    require(args.confidence_level == .95, "K12 source CIs require confidence-level=0.95")
    require(args.npr_primary == 1.515059 and args.ml_primary == .5, "This release targets K12 v2 primary thresholds")
    require(args.figure_width >= 6.5 and args.figure_height >= 4.2 and args.dpi >= 100,
            "Six-panel figure requires width>=6.5, height>=4.2, dpi>=100")
    paths = {key: args.input_root / filename for key, filename in FILES.items()}
    for path in paths.values():
        require(path.is_file(), f"Missing required input: {path}")
    data = {key: pd.read_csv(path, keep_default_na=False) for key, path in paths.items()}
    frame, checks = validate(data, args)
    series, runs, diagnostics = summaries(frame, data["diagnostics"], args)
    stems = [f"fig_gmm_localization_threshold_sensitivity-{VERSION}"] + [
        f"fig_gmm_{d}_{s}_threshold_sensitivity-{VERSION}" for d in ("npr", "ml") for s in SCOPES]
    csv_names = ["plot_data", "series_summary", "significant_threshold_runs", "diagnostic_summary", "reconciliation_checks"]
    csv_paths = {name: args.output_root / f"gmm_localization_threshold_{name}.csv" for name in csv_names}
    metadata_path = args.output_root / "gmm_localization_threshold_metadata.json"
    targets = [args.figure_dir / (stem + "." + ext) for stem in stems for ext in ("pdf", "png")]
    targets += list(csv_paths.values()) + [metadata_path, args.output_tex]
    require(len(set(p.resolve() for p in targets)) == len(targets), "Duplicate output paths")
    require(not set(p.resolve() for p in paths.values()).intersection(p.resolve() for p in targets), "Output would overwrite input")
    existing = [str(p) for p in targets if p.exists()]
    require(args.overwrite or not existing, "Outputs exist; use --overwrite explicitly: " + ", ".join(existing[:3]))
    figure_path = Path(os.path.relpath(args.figure_dir / (stems[0] + ".pdf"), Path.cwd())).as_posix()
    require(re.fullmatch(r"[A-Za-z0-9_./-]+", figure_path) is not None, "Unsafe LaTeX figure path")
    for directory in (args.output_root, args.figure_dir, args.output_tex.parent):
        directory.mkdir(parents=True, exist_ok=True)
    print(f"Validated K12 v2: {len(frame)} FECS GMM estimates; no re-estimation")
    limits = render(frame, args)
    for name, table in zip(csv_names, [frame, series, runs, diagnostics, checks]):
        table.to_csv(csv_paths[name], index=False, float_format="%.17g")
    tex = ("% Generated by run-y-b11 v1. Replace the old figure environment; do not duplicate its label.\n"
           "\\begin{figure*}[!t]\n\\centering\n"
           f"\\includegraphics[width=\\textwidth]{{{figure_path}}}\n"
           "\\caption{Threshold sensitivity of dynamic-panel GMM estimates for detector-localized issue burden and subsequent velocity.}\n"
           "\\label{fig:gmm-rf-cm-threshold-sensitivity}\n\\end{figure*}\n"
           "% Points report lagged issue-burden coefficients with pointwise 95\\% CIs.\n"
           "% Columns: RF, CM, RF+CM; rows: NPR, ML. All models use FECS.\n"
           "% Filled markers mark primary thresholds. Y-axis ranges vary by panel.\n"
           "% CI colors indicate distance from the primary threshold, not significance.\n")
    args.output_tex.write_text(tex, encoding="utf-8")
    metadata = {"run_id": "run-y-b11", "implementation_version": VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(), "script_sha256": digest(Path(__file__)),
        "inputs": {key: {"path": str(path.resolve()), "sha256": digest(path), "rows": len(data[key])} for key, path in paths.items()},
        "arguments": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "software": {"python": sys.version, "numpy": np.__version__, "pandas": pd.__version__, "matplotlib": matplotlib.__version__},
        "color_reference": ["fig_npr_rf_cm_threshold_sensitivity-v3.pdf", "fig_ml_rf_cm_threshold_sensitivity-v3.pdf"],
        "palette": PALETTE, "primary_color": PRIMARY_COLOR, "y_limits": limits,
        "coefficient": "lag(log1p_selected_issue_total, 1)", "sample": "full_sample",
        "inference": "pointwise normal-approximation CIs; no multiplicity adjustment",
        "source_qc_cautions": int(data["qc"].status.eq("caution").sum()),
        "source_model_warnings": int(data["instrument_qc"].warning_count.sum()),
        "support_note": "Constant model sample does not imply constant localized-issue variation. Selected-file rows are occurrences, not unique files.",
        "outputs": {str(p.resolve()): digest(p) for p in targets if p != metadata_path}}
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    for row in series.itertuples():
        print(f"{row.detector} {row.localization_scope}: primary={row.primary_estimate:.3f}, "
              f"SE={row.primary_std_error:.3f}, p={row.primary_p_value:.6g}; "
              f"negative={row.negative_estimates}/21; significant negative={row.significant_negative}/21")
    print(f"PASS: {len(checks)} reconciliation checks")
    print(f"Source QC cautions: {metadata['source_qc_cautions']}; model warnings: {metadata['source_model_warnings']}")
    print(f"Figure: {args.figure_dir / (stems[0] + '.pdf')}")
    print(f"LaTeX: {args.output_tex}")
    print(f"Summary: {csv_paths['series_summary']}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
