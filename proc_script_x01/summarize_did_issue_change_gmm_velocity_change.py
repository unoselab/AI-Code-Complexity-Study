#!/usr/bin/env python3
"""Summarize localized DiD issue-burden changes and GMM velocity changes.

This script is designed for the run-y-a02 manuscript-support experiment.
It reads the primary combined RF+CM DiD and GMM result files for the NPR
and ML localization approaches, validates the expected primary rows, and
produces compact CSV/JSON summaries plus a terminal report.

Inputs
------
1. NPR combined RF+CM DiD primary static results (run-x-i05).
2. ML combined RF+CM DiD primary static results (run-x-i09).
3. NPR combined RF+CM GMM coefficients (run-x-k04).
4. ML combined RF+CM GMM coefficients (run-x-k08).

Outputs
-------
1. did_issue_change_summary.csv
   Full-sample adjusted and FE-only DiD estimates and percent changes.
2. gmm_velocity_change_summary.csv
   Full-sample primary GMM coefficients and a configurable model-scale
   velocity-change calculation for a specified burden increase.
3. did_issue_change_gmm_velocity_change_summary.json
   Machine-readable combined summary with interpretation notes.

Important interpretation
------------------------
The DiD outcome is log1p(selected issue burden), so the static ATT is
back-transformed as 100 * (exp(beta) - 1).

The GMM regressor and outcome are both log1p variables. Therefore, for a
burden increase of r percent, the baseline-independent model-scale mapping is:

    100 * ((1 + r/100) ** gamma - 1)

This is a percent change in (1 + subsequent velocity) associated with a
percent change in (1 + prior localized issue burden). It should not be
silently described as an exact raw-count elasticity.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence


SCRIPT_VERSION = "summarize-did-issue-change-gmm-velocity-change-v1"
DEFAULT_BURDEN_INCREASE_PCT = 10.0
NPR_PRIMARY_THRESHOLD = 1.571637
ML_PRIMARY_THRESHOLD = 0.50


class SummaryError(RuntimeError):
    """Raised when an input violates the frozen analysis contract."""


@dataclass(frozen=True)
class DidSummaryRow:
    detector: str
    sample_spec: str
    model_spec: str
    estimate: float
    std_error: float
    p_value: float
    conf_low: float
    conf_high: float
    issue_change_pct: float
    issue_change_ci_low_pct: float
    issue_change_ci_high_pct: float
    significant_05: bool
    outcome: str
    threshold: float
    comparison_operator: str


@dataclass(frozen=True)
class GmmSummaryRow:
    detector: str
    sample_spec: str
    estimate_gamma: float
    std_error: float
    p_value: float
    conf_low: float
    conf_high: float
    significant_05: bool
    burden_increase_pct: float
    velocity_change_pct_model_scale: float
    velocity_change_ci_low_pct_model_scale: float
    velocity_change_ci_high_pct_model_scale: float
    term: str
    interpretation_basis: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize combined RF+CM DiD issue changes and GMM velocity changes."
    )
    parser.add_argument("--npr-did", type=Path, help="run-x-i05 primary total static CSV")
    parser.add_argument("--ml-did", type=Path, help="run-x-i09 primary total static CSV")
    parser.add_argument("--npr-gmm", type=Path, help="run-x-k04 GMM coefficients CSV")
    parser.add_argument("--ml-gmm", type=Path, help="run-x-k08 GMM coefficients CSV")
    parser.add_argument("--output-dir", type=Path, help="Directory for run-y-a02 summary outputs")
    parser.add_argument(
        "--burden-increase-pct",
        type=float,
        default=DEFAULT_BURDEN_INCREASE_PCT,
        help=(
            "Percent increase in (1 + prior localized issue burden) used for the "
            "GMM model-scale interpretation (default: 10)."
        ),
    )
    parser.add_argument("--self-test", action="store_true", help="Run internal formula tests and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return args

    required = ["npr_did", "ml_did", "npr_gmm", "ml_gmm", "output_dir"]
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("Missing required arguments: " + ", ".join("--" + x.replace("_", "-") for x in missing))

    if args.burden_increase_pct <= -100.0:
        parser.error("--burden-increase-pct must be greater than -100")

    return args


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        raise SummaryError(f"Input file does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SummaryError(f"CSV has no header: {path}")
        return [dict(row) for row in reader]


def require_columns(rows: Sequence[Mapping[str, str]], columns: Iterable[str], source: str) -> None:
    if not rows:
        raise SummaryError(f"No rows found in {source}")
    available = set(rows[0].keys())
    missing = sorted(set(columns) - available)
    if missing:
        raise SummaryError(f"Missing columns in {source}: {', '.join(missing)}")


def to_float(value: str, field: str, source: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise SummaryError(f"Cannot parse {field}={value!r} as float in {source}") from exc
    if not math.isfinite(result):
        raise SummaryError(f"Non-finite {field}={value!r} in {source}")
    return result


def to_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def approx_equal(a: float, b: float, tol: float = 1e-8) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def back_transform_log1p_beta(beta: float) -> float:
    return 100.0 * math.expm1(beta)


def gmm_model_scale_change(gamma: float, burden_increase_pct: float) -> float:
    ratio = 1.0 + burden_increase_pct / 100.0
    if ratio <= 0.0:
        raise SummaryError("The burden-change ratio must be positive")
    return 100.0 * (math.exp(gamma * math.log(ratio)) - 1.0)


def select_did_rows(path: Path, detector: str, expected_threshold: float) -> List[DidSummaryRow]:
    source = f"{detector} DiD ({path})"
    rows = read_csv_rows(path)
    require_columns(
        rows,
        [
            "sample_spec",
            "term",
            "estimate",
            "std.error",
            "conf.low",
            "conf.high",
            "p_value",
            "exp_coefficient_change_pct",
            "exp_ci_low_pct",
            "exp_ci_high_pct",
            "threshold",
            "comparison_operator",
            "model_spec",
            "outcome",
        ],
        source,
    )

    selected = [
        row
        for row in rows
        if row.get("sample_spec") == "full_sample"
        and row.get("term") == "treat"
        and row.get("outcome") == "log1p_selected_issue_total"
        and row.get("model_spec") in {"adjusted_burden", "fe_only_burden"}
    ]

    if len(selected) != 2:
        raise SummaryError(
            f"Expected exactly two full-sample primary DiD rows in {source}; found {len(selected)}"
        )

    seen_models = {row["model_spec"] for row in selected}
    if seen_models != {"adjusted_burden", "fe_only_burden"}:
        raise SummaryError(f"Unexpected DiD model set in {source}: {sorted(seen_models)}")

    output: List[DidSummaryRow] = []
    for row in selected:
        estimate = to_float(row["estimate"], "estimate", source)
        std_error = to_float(row["std.error"], "std.error", source)
        p_value = to_float(row["p_value"], "p_value", source)
        conf_low = to_float(row["conf.low"], "conf.low", source)
        conf_high = to_float(row["conf.high"], "conf.high", source)
        threshold = to_float(row["threshold"], "threshold", source)

        if not approx_equal(threshold, expected_threshold, tol=1e-9):
            raise SummaryError(
                f"Unexpected {detector} primary threshold: {threshold}; expected {expected_threshold}"
            )
        if row["comparison_operator"].strip() != ">":
            raise SummaryError(f"Unexpected {detector} comparison operator: {row['comparison_operator']!r}")

        recomputed_change = back_transform_log1p_beta(estimate)
        reported_change = to_float(
            row["exp_coefficient_change_pct"], "exp_coefficient_change_pct", source
        )
        if not approx_equal(recomputed_change, reported_change, tol=1e-9):
            raise SummaryError(
                f"{detector} DiD percent-change mismatch for {row['model_spec']}: "
                f"recomputed={recomputed_change}, reported={reported_change}"
            )

        recomputed_low = back_transform_log1p_beta(conf_low)
        recomputed_high = back_transform_log1p_beta(conf_high)
        reported_low = to_float(row["exp_ci_low_pct"], "exp_ci_low_pct", source)
        reported_high = to_float(row["exp_ci_high_pct"], "exp_ci_high_pct", source)
        if not approx_equal(recomputed_low, reported_low, tol=1e-9):
            raise SummaryError(f"{detector} DiD lower-CI percent mismatch for {row['model_spec']}")
        if not approx_equal(recomputed_high, reported_high, tol=1e-9):
            raise SummaryError(f"{detector} DiD upper-CI percent mismatch for {row['model_spec']}")

        output.append(
            DidSummaryRow(
                detector=detector,
                sample_spec="full_sample",
                model_spec=row["model_spec"],
                estimate=estimate,
                std_error=std_error,
                p_value=p_value,
                conf_low=conf_low,
                conf_high=conf_high,
                issue_change_pct=recomputed_change,
                issue_change_ci_low_pct=recomputed_low,
                issue_change_ci_high_pct=recomputed_high,
                significant_05=p_value < 0.05,
                outcome=row["outcome"],
                threshold=threshold,
                comparison_operator=row["comparison_operator"].strip(),
            )
        )

    output.sort(key=lambda x: (x.detector, 0 if x.model_spec == "adjusted_burden" else 1))
    return output


def select_gmm_row(
    path: Path,
    detector: str,
    burden_increase_pct: float,
) -> GmmSummaryRow:
    source = f"{detector} GMM ({path})"
    rows = read_csv_rows(path)
    require_columns(
        rows,
        [
            "sample_spec",
            "term",
            "estimate",
            "std_error",
            "conf_low",
            "conf_high",
            "p_value",
            "is_primary_interaction_term",
        ],
        source,
    )

    selected = [
        row
        for row in rows
        if row.get("sample_spec") == "full_sample"
        and row.get("term") == "lag(log1p_selected_issue_total, 1)"
        and to_bool(row.get("is_primary_interaction_term", ""))
    ]
    if len(selected) != 1:
        raise SummaryError(
            f"Expected exactly one full-sample primary GMM interaction row in {source}; found {len(selected)}"
        )

    row = selected[0]
    gamma = to_float(row["estimate"], "estimate", source)
    std_error = to_float(row["std_error"], "std_error", source)
    p_value = to_float(row["p_value"], "p_value", source)
    conf_low = to_float(row["conf_low"], "conf_low", source)
    conf_high = to_float(row["conf_high"], "conf_high", source)

    return GmmSummaryRow(
        detector=detector,
        sample_spec="full_sample",
        estimate_gamma=gamma,
        std_error=std_error,
        p_value=p_value,
        conf_low=conf_low,
        conf_high=conf_high,
        significant_05=p_value < 0.05,
        burden_increase_pct=burden_increase_pct,
        velocity_change_pct_model_scale=gmm_model_scale_change(gamma, burden_increase_pct),
        velocity_change_ci_low_pct_model_scale=gmm_model_scale_change(conf_low, burden_increase_pct),
        velocity_change_ci_high_pct_model_scale=gmm_model_scale_change(conf_high, burden_increase_pct),
        term=row["term"],
        interpretation_basis=(
            "Percent change in (1 + subsequent velocity) for the specified percent change "
            "in (1 + prior localized issue burden); both model variables are log1p transformed."
        ),
    )


def write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise SummaryError(f"Refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_combined_json(
    did_rows: Sequence[DidSummaryRow],
    gmm_rows: Sequence[GmmSummaryRow],
    burden_increase_pct: float,
    inputs: Mapping[str, str],
) -> Dict[str, object]:
    did_by_detector: Dict[str, Dict[str, DidSummaryRow]] = {}
    for row in did_rows:
        did_by_detector.setdefault(row.detector, {})[row.model_spec] = row

    gmm_by_detector = {row.detector: row for row in gmm_rows}

    return {
        "script_version": SCRIPT_VERSION,
        "analysis_scope": "combined regular functions + class methods (RF+CM)",
        "sample_spec": "full_sample",
        "inputs": dict(inputs),
        "did": {
            detector: {
                model: asdict(row)
                for model, row in sorted(models.items())
            }
            for detector, models in sorted(did_by_detector.items())
        },
        "gmm": {detector: asdict(row) for detector, row in sorted(gmm_by_detector.items())},
        "paper_ready": {
            "did_adjusted_issue_change_range_pct": [
                min(did_by_detector[d]["adjusted_burden"].issue_change_pct for d in did_by_detector),
                max(did_by_detector[d]["adjusted_burden"].issue_change_pct for d in did_by_detector),
            ],
            "did_fe_only_issue_change_range_pct": [
                min(did_by_detector[d]["fe_only_burden"].issue_change_pct for d in did_by_detector),
                max(did_by_detector[d]["fe_only_burden"].issue_change_pct for d in did_by_detector),
            ],
            "gmm_burden_increase_pct_model_scale": burden_increase_pct,
            "gmm_velocity_change_pct_model_scale": {
                detector: row.velocity_change_pct_model_scale
                for detector, row in sorted(gmm_by_detector.items())
            },
            "gmm_coefficients": {
                detector: row.estimate_gamma for detector, row in sorted(gmm_by_detector.items())
            },
        },
        "interpretation_notes": [
            "DiD percent changes are 100*(exp(ATT)-1) on log1p selected-issue-burden outcomes.",
            "GMM percentage mappings are model-scale changes because both localized burden and velocity use log1p transforms.",
            "The GMM mapping should be stated as a change in (1 + velocity) associated with a change in (1 + localized burden), not as an exact raw-count elasticity.",
            "GMM coefficients are associations and should not be described as causal effects.",
        ],
    }


def print_report(did_rows: Sequence[DidSummaryRow], gmm_rows: Sequence[GmmSummaryRow]) -> None:
    did_lookup = {(r.detector, r.model_spec): r for r in did_rows}
    gmm_lookup = {r.detector: r for r in gmm_rows}

    print("=" * 86)
    print("Localized DiD issue change and GMM velocity change summary")
    print(f"Script version: {SCRIPT_VERSION}")
    print("Scope:          combined regular functions + class methods (RF+CM)")
    print("Sample:         full_sample")
    print("-" * 86)
    for detector in ("NPR", "ML"):
        adjusted = did_lookup[(detector, "adjusted_burden")]
        fe_only = did_lookup[(detector, "fe_only_burden")]
        print(
            f"{detector} DiD adjusted: ATT={adjusted.estimate:.6f}, "
            f"issue change={adjusted.issue_change_pct:+.2f}%, p={adjusted.p_value:.4g}"
        )
        print(
            f"{detector} DiD FE-only:  ATT={fe_only.estimate:.6f}, "
            f"issue change={fe_only.issue_change_pct:+.2f}%, p={fe_only.p_value:.4g}"
        )
        gmm = gmm_lookup[detector]
        print(
            f"{detector} GMM:          gamma={gmm.estimate_gamma:.6f}, p={gmm.p_value:.4g}; "
            f"for +{gmm.burden_increase_pct:g}% in (1+burden), "
            f"(1+velocity) change={gmm.velocity_change_pct_model_scale:+.2f}%"
        )
        print("-" * 86)
    print("Interpret GMM percentage mappings on the log1p model scale, not as raw-count elasticities.")
    print("=" * 86)


def run_self_test() -> None:
    # Known DiD back-transform checks from the frozen combined RF+CM results.
    npr_adjusted = back_transform_log1p_beta(0.160600236949446)
    ml_adjusted = back_transform_log1p_beta(0.170860227014737)
    if not approx_equal(npr_adjusted, 17.4215467018286, tol=1e-10):
        raise SummaryError("Self-test failed: NPR DiD back-transform")
    if not approx_equal(ml_adjusted, 18.6324921257124, tol=1e-10):
        raise SummaryError("Self-test failed: ML DiD back-transform")

    # Known GMM model-scale checks for a 10% increase in (1 + localized burden).
    npr_velocity = gmm_model_scale_change(-0.811895280403279, 10.0)
    ml_velocity = gmm_model_scale_change(-0.480656827839776, 10.0)
    if not approx_equal(npr_velocity, -7.4463662481, tol=1e-8):
        raise SummaryError(f"Self-test failed: NPR GMM mapping ({npr_velocity})")
    if not approx_equal(ml_velocity, -4.4777984623, tol=1e-8):
        raise SummaryError(f"Self-test failed: ML GMM mapping ({ml_velocity})")

    print(f"{SCRIPT_VERSION} self-test: PASS")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        run_self_test()
        return 0

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    did_rows: List[DidSummaryRow] = []
    did_rows.extend(select_did_rows(args.npr_did, "NPR", NPR_PRIMARY_THRESHOLD))
    did_rows.extend(select_did_rows(args.ml_did, "ML", ML_PRIMARY_THRESHOLD))

    gmm_rows = [
        select_gmm_row(args.npr_gmm, "NPR", args.burden_increase_pct),
        select_gmm_row(args.ml_gmm, "ML", args.burden_increase_pct),
    ]

    did_csv_rows = [asdict(row) for row in did_rows]
    gmm_csv_rows = [asdict(row) for row in gmm_rows]

    did_csv = output_dir / "did_issue_change_summary.csv"
    gmm_csv = output_dir / "gmm_velocity_change_summary.csv"
    summary_json = output_dir / "did_issue_change_gmm_velocity_change_summary.json"

    write_csv(did_csv, did_csv_rows)
    write_csv(gmm_csv, gmm_csv_rows)

    combined = build_combined_json(
        did_rows,
        gmm_rows,
        args.burden_increase_pct,
        inputs={
            "npr_did": str(args.npr_did),
            "ml_did": str(args.ml_did),
            "npr_gmm": str(args.npr_gmm),
            "ml_gmm": str(args.ml_gmm),
        },
    )
    with summary_json.open("w", encoding="utf-8") as handle:
        json.dump(combined, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print_report(did_rows, gmm_rows)
    print(f"DiD summary CSV: {did_csv}")
    print(f"GMM summary CSV: {gmm_csv}")
    print(f"Summary JSON:    {summary_json}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SummaryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
