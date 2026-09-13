#!/usr/bin/env python3
"""Create the whole-Python and detector-localized velocity DiD table.

The script reads the run-y-b02 whole-Python summary and the run-x-b08
detector-localized static effects. It retains the common primary outcome,
validates statistical quantities and sample counts, and writes the LaTeX
table plus machine-readable summary, reconciliation, and metadata files.

Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Iterable, Mapping, Sequence


RUN_LABEL = "run-y-b12-v1"
SPECIFICATIONS = ("FECS", "FEOS")
DETECTORS = ("NPR", "ML")
SCOPES = ("RF", "CM", "RF+CM")
PRIMARY_OUTCOME = "log_lines_added_py_source"


@dataclass(frozen=True)
class Estimate:
    file_set: str
    detector: str
    scope: str
    outcome: str
    specification: str
    estimate: float
    std_error: float
    p_value: float
    conf_low: float
    conf_high: float
    percent_change: float
    significance_marker: str
    ci_marker: str
    treated_observations: str
    first_stage_observations: str
    treatment_repositories: str
    control_repositories: str
    source_file: str


@dataclass(frozen=True)
class Check:
    check_name: str
    observed: str
    expected: str
    passed: bool


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize whole-Python and detector-localized velocity DiD effects."
    )
    parser.add_argument("--overall-summary-file", type=Path)
    parser.add_argument("--localized-static-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--table-output", type=Path)
    parser.add_argument("--implementation-version", default="v1")
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument("--strict-expected-counts", type=int, choices=(0, 1), default=1)
    parser.add_argument("--expected-overall-rows", type=int, default=8)
    parser.add_argument("--expected-localized-rows", type=int, default=12)
    parser.add_argument("--expected-treated-observations", type=int, default=363)
    parser.add_argument("--expected-first-stage-observations", type=int, default=1591)
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)

    if args.version:
        print(RUN_LABEL)
        raise SystemExit(0)
    if args.self_test:
        return args
    required = (
        "overall_summary_file",
        "localized_static_file",
        "output_dir",
        "table_output",
    )
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error(
            "required arguments: "
            + ", ".join("--" + name.replace("_", "-") for name in missing)
        )
    if not 0.0 < args.confidence_level < 1.0:
        parser.error("--confidence-level must be between zero and one")
    return args


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        return [dict(row) for row in reader]


def require_columns(
    rows: Sequence[Mapping[str, str]], columns: Iterable[str], path: Path
) -> None:
    if not rows:
        raise ValueError(f"CSV has no data rows: {path}")
    missing = [name for name in columns if name not in rows[0]]
    if missing:
        raise ValueError(f"Missing columns in {path}: {', '.join(missing)}")


def number(row: Mapping[str, str], column: str, context: str) -> float:
    raw = row.get(column, "")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {column} for {context}: {raw!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"Non-finite {column} for {context}: {raw!r}")
    return value


def integer(row: Mapping[str, str], column: str, context: str) -> int:
    value = number(row, column, context)
    if not value.is_integer():
        raise ValueError(f"Expected integer {column} for {context}, found {value}")
    return int(value)


def significance_marker(p_value: float) -> str:
    if p_value < 0.001:
        return "***"
    if p_value < 0.01:
        return "**"
    if p_value < 0.05:
        return "*"
    if p_value < 0.10:
        return r"\dagger"
    return ""


def add_check(
    checks: list[Check], name: str, observed: object, expected: object, passed: bool
) -> None:
    checks.append(Check(name, str(observed), str(expected), bool(passed)))


def validate_statistics(
    row: Mapping[str, str],
    context: str,
    confidence_level: float,
    checks: list[Check],
    columns: Mapping[str, str],
) -> tuple[float, float, float, float, float, float, str, str]:
    estimate = number(row, columns["estimate"], context)
    std_error = number(row, columns["std_error"], context)
    p_value = number(row, columns["p_value"], context)
    conf_low = number(row, columns["conf_low"], context)
    conf_high = number(row, columns["conf_high"], context)
    reported_percent = number(row, columns["percent_change"], context)
    if std_error <= 0.0:
        raise ValueError(f"Non-positive standard error for {context}: {std_error}")
    if not 0.0 <= p_value <= 1.0:
        raise ValueError(f"Invalid p-value for {context}: {p_value}")

    z_value = NormalDist().inv_cdf(0.5 + confidence_level / 2.0)
    derived_low = estimate - z_value * std_error
    derived_high = estimate + z_value * std_error
    derived_percent = 100.0 * math.expm1(estimate)
    derived_p = math.erfc(abs(estimate / std_error) / math.sqrt(2.0))
    ci_significant = conf_low > 0.0 or conf_high < 0.0
    marker = significance_marker(p_value)
    ci_marker = r"\checkmark" if ci_significant else r"\times"

    add_check(
        checks,
        f"{context}: confidence interval",
        f"[{conf_low:.12g}, {conf_high:.12g}]",
        f"[{derived_low:.12g}, {derived_high:.12g}]",
        math.isclose(conf_low, derived_low, abs_tol=5e-10)
        and math.isclose(conf_high, derived_high, abs_tol=5e-10),
    )
    add_check(
        checks,
        f"{context}: percentage change",
        f"{reported_percent:.12g}",
        f"{derived_percent:.12g}",
        math.isclose(reported_percent, derived_percent, abs_tol=5e-10),
    )
    add_check(
        checks,
        f"{context}: two-sided normal p-value",
        f"{p_value:.12g}",
        f"{derived_p:.12g}",
        math.isclose(p_value, derived_p, abs_tol=5e-10),
    )
    add_check(
        checks,
        f"{context}: p-value and confidence interval",
        p_value < 0.05,
        ci_significant,
        (p_value < 0.05) == ci_significant,
    )
    return (
        estimate,
        std_error,
        p_value,
        conf_low,
        conf_high,
        derived_percent,
        marker,
        ci_marker,
    )


def prepare_overall(
    rows: Sequence[Mapping[str, str]], path: Path, args: argparse.Namespace, checks: list[Check]
) -> list[Estimate]:
    required = (
        "outcome_id", "outcome", "specification", "estimate", "std_error",
        "p_value", "conf_low", "conf_high", "percent_change",
    )
    require_columns(rows, required, path)
    add_check(
        checks,
        "whole-Python source row count",
        len(rows),
        args.expected_overall_rows,
        len(rows) == args.expected_overall_rows,
    )
    selected = [
        row for row in rows
        if row["outcome_id"] == "O1" and row["outcome"] == PRIMARY_OUTCOME
    ]
    add_check(checks, "whole-Python O1 rows", len(selected), 2, len(selected) == 2)
    by_spec = {row["specification"]: row for row in selected}
    if set(by_spec) != set(SPECIFICATIONS) or len(selected) != len(by_spec):
        raise ValueError("Whole-Python O1 must contain one FECS and one FEOS row")

    results: list[Estimate] = []
    columns = {
        "estimate": "estimate", "std_error": "std_error", "p_value": "p_value",
        "conf_low": "conf_low", "conf_high": "conf_high",
        "percent_change": "percent_change",
    }
    for specification in SPECIFICATIONS:
        values = validate_statistics(
            by_spec[specification], f"Fpy/{specification}", args.confidence_level,
            checks, columns,
        )
        results.append(
            Estimate(
                file_set="Fpy", detector="ALL", scope="ALL",
                outcome=PRIMARY_OUTCOME, specification=specification,
                estimate=values[0], std_error=values[1], p_value=values[2],
                conf_low=values[3], conf_high=values[4], percent_change=values[5],
                significance_marker=values[6], ci_marker=values[7],
                treated_observations="", first_stage_observations="",
                treatment_repositories="", control_repositories="",
                source_file=str(path),
            )
        )
    return results


def prepare_localized(
    rows: Sequence[Mapping[str, str]], path: Path, args: argparse.Namespace, checks: list[Check]
) -> list[Estimate]:
    required = (
        "term", "estimate", "std.error", "conf.low", "conf.high", "p_value",
        "percent_change", "specification", "first_stage_formula", "outcome",
        "detector", "scope", "treated_observations", "first_stage_observations",
        "treatment_repositories", "control_repositories",
    )
    require_columns(rows, required, path)
    add_check(
        checks,
        "detector-localized source row count",
        len(rows),
        args.expected_localized_rows,
        len(rows) == args.expected_localized_rows,
    )
    selected = [
        row for row in rows
        if row["term"] == "treat"
        and row["detector"] in DETECTORS
        and row["scope"] in SCOPES
        and row["specification"] in SPECIFICATIONS
    ]
    keys = [(row["detector"], row["scope"], row["specification"]) for row in selected]
    expected_keys = {
        (detector, scope, specification)
        for detector in DETECTORS
        for scope in SCOPES
        for specification in SPECIFICATIONS
    }
    add_check(checks, "detector-localized model keys", len(set(keys)), 12, set(keys) == expected_keys)
    if len(keys) != len(set(keys)) or set(keys) != expected_keys:
        raise ValueError("Localized input does not contain the required unique model set")

    by_key = {
        (row["detector"], row["scope"], row["specification"]): row
        for row in selected
    }
    columns = {
        "estimate": "estimate", "std_error": "std.error", "p_value": "p_value",
        "conf_low": "conf.low", "conf_high": "conf.high",
        "percent_change": "percent_change",
    }
    results: list[Estimate] = []
    for detector in DETECTORS:
        for scope in SCOPES:
            expected_outcome = (
                f"log_lines_added_py_source_localized_{detector.lower()}_"
                f"{scope.lower().replace('+', '_')}"
            )
            for specification in SPECIFICATIONS:
                row = by_key[(detector, scope, specification)]
                context = f"{detector}/{scope}/{specification}"
                add_check(
                    checks, f"{context}: outcome", row["outcome"], expected_outcome,
                    row["outcome"] == expected_outcome,
                )
                expected_formula_prefix = "~ log_age" if specification == "FECS" else "~ 1 |"
                add_check(
                    checks, f"{context}: specification formula",
                    row["first_stage_formula"], expected_formula_prefix,
                    row["first_stage_formula"].startswith(expected_formula_prefix),
                )
                for column, expected in (
                    ("treated_observations", args.expected_treated_observations),
                    ("first_stage_observations", args.expected_first_stage_observations),
                    ("treatment_repositories", args.expected_treatment_repositories),
                    ("control_repositories", args.expected_control_repositories),
                ):
                    observed = integer(row, column, context)
                    add_check(checks, f"{context}: {column}", observed, expected, observed == expected)

                values = validate_statistics(row, context, args.confidence_level, checks, columns)
                results.append(
                    Estimate(
                        file_set="FpyLocalized", detector=detector, scope=scope,
                        outcome=row["outcome"], specification=specification,
                        estimate=values[0], std_error=values[1], p_value=values[2],
                        conf_low=values[3], conf_high=values[4], percent_change=values[5],
                        significance_marker=values[6], ci_marker=values[7],
                        treated_observations=row["treated_observations"],
                        first_stage_observations=row["first_stage_observations"],
                        treatment_repositories=row["treatment_repositories"],
                        control_repositories=row["control_repositories"],
                        source_file=str(path),
                    )
                )
    return results


EXPECTED_ROUNDED = {
    ("ALL", "ALL", "FECS"): (0.574, 0.308, 77.6, r"\dagger", r"\times"),
    ("ALL", "ALL", "FEOS"): (1.100, 0.383, 200.4, "**", r"\checkmark"),
    ("NPR", "RF", "FECS"): (0.525, 0.306, 69.1, r"\dagger", r"\times"),
    ("NPR", "RF", "FEOS"): (0.766, 0.292, 115.2, "**", r"\checkmark"),
    ("NPR", "CM", "FECS"): (0.117, 0.274, 12.4, "", r"\times"),
    ("NPR", "CM", "FEOS"): (0.338, 0.278, 40.2, "", r"\times"),
    ("NPR", "RF+CM", "FECS"): (0.419, 0.313, 52.1, "", r"\times"),
    ("NPR", "RF+CM", "FEOS"): (0.667, 0.311, 94.8, "*", r"\checkmark"),
    ("ML", "RF", "FECS"): (0.591, 0.285, 80.7, "*", r"\checkmark"),
    ("ML", "RF", "FEOS"): (0.791, 0.292, 120.6, "**", r"\checkmark"),
    ("ML", "CM", "FECS"): (0.262, 0.294, 29.9, "", r"\times"),
    ("ML", "CM", "FEOS"): (0.461, 0.278, 58.6, r"\dagger", r"\times"),
    ("ML", "RF+CM", "FECS"): (0.322, 0.314, 38.0, "", r"\times"),
    ("ML", "RF+CM", "FEOS"): (0.556, 0.306, 74.3, r"\dagger", r"\times"),
}


def verify_manuscript_rounding(estimates: Sequence[Estimate], checks: list[Check]) -> None:
    for item in estimates:
        key = (item.detector, item.scope, item.specification)
        expected = EXPECTED_ROUNDED[key]
        observed = (
            round(item.estimate, 3), round(item.std_error, 3),
            round(item.percent_change, 1), item.significance_marker, item.ci_marker,
        )
        add_check(checks, f"{key}: manuscript rounding", observed, expected, observed == expected)


def format_att(item: Estimate) -> str:
    star = f"^{{{item.significance_marker}}}" if item.significance_marker else ""
    return f"${item.estimate:.3f}{star}\\,({item.ci_marker})\\,({item.std_error:.3f})$"


def format_percent(value: float) -> str:
    return f"${value:+.1f}\\%$"


def index_estimates(estimates: Sequence[Estimate]) -> dict[tuple[str, str, str], Estimate]:
    return {(item.detector, item.scope, item.specification): item for item in estimates}


def render_table(estimates: Sequence[Estimate]) -> str:
    by_key = index_estimates(estimates)
    rows: list[str] = []

    def row(label: str, detector: str, key_scope: str) -> None:
        fecs = by_key[(detector, key_scope, "FECS")]
        feos = by_key[(detector, key_scope, "FEOS")]
        rows.append(
            f"{label} & {format_att(fecs)} & {format_percent(fecs.percent_change)} "
            f"& {format_att(feos)} & {format_percent(feos.percent_change)} \\\\"
        )

    row(r"$\Fpy$", "ALL", "ALL")
    rows.append(r"\addlinespace")
    row(r"$(\text{\tiny NPR},\text{\tiny RF})$", "NPR", "RF")
    row(r"$(\text{\tiny NPR},\text{\tiny CM})$", "NPR", "CM")
    row(r"$(\text{\tiny NPR},\text{\tiny RF{+}CM})$", "NPR", "RF+CM")
    rows.append(r"\addlinespace")
    row(r"$(\text{\tiny ML},\text{\tiny RF})$", "ML", "RF")
    row(r"$(\text{\tiny ML},\text{\tiny CM})$", "ML", "CM")
    row(r"$(\text{\tiny ML},\text{\tiny RF{+}CM})$", "ML", "RF+CM")

    body = "\n".join(rows)
    return rf"""\begin{{table}}[!t]
\centering
\scriptsize
\caption{{Effects of Cursor adoption on log-transformed monthly Python source additions across $\Fpy$ and $\FpyLocalized{{d}}{{s}}{{\tau_d}}$. Localized rows identify $(d,s)$. Percentage changes are $\Delta\%=100(e^{{\mathrm{{ATT}}}}-1)$. Parentheses report repository-clustered SEs; $\checkmark$ and $\times$ denote statistical significance and insignificance at the 5\% level, respectively.}}
\label{{tb:did-velocity-python}}
{{\setlength{{\tabcolsep}}{{1pt}}
\resizebox{{\columnwidth}}{{!}}{{%
\begin{{tabular}}{{@{{}}l|cc|cc@{{}}}}
\tableheader{{Files}} & \tableheader{{FECS ATT}} & \tableheader{{$\Delta\%$}}
& \tableheader{{FEOS ATT}} & \tableheader{{$\Delta\%$}} \\
\midrule
{body}
\end{{tabular}}
}}
}}
\vspace{{-.1in}}
\end{{table}}
"""


def write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write an empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def ensure_writable(paths: Sequence[Path], overwrite: bool) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Output files already exist; use --overwrite to replace them: "
            + ", ".join(existing)
        )


def execute(args: argparse.Namespace) -> tuple[list[Estimate], list[Check]]:
    overall_rows = read_csv(args.overall_summary_file)
    localized_rows = read_csv(args.localized_static_file)
    checks: list[Check] = []
    estimates = prepare_overall(overall_rows, args.overall_summary_file, args, checks)
    estimates.extend(
        prepare_localized(localized_rows, args.localized_static_file, args, checks)
    )
    verify_manuscript_rounding(estimates, checks)

    failures = [item for item in checks if not item.passed]
    if args.strict_expected_counts and failures:
        details = "; ".join(item.check_name for item in failures[:10])
        raise ValueError(f"Reconciliation failed: {details}")

    summary_path = args.output_dir / "python_velocity_localized_did_summary.csv"
    checks_path = args.output_dir / "python_velocity_localized_did_reconciliation_checks.csv"
    metadata_path = args.output_dir / "python_velocity_localized_did_run_metadata.csv"
    targets = (args.table_output, summary_path, checks_path, metadata_path)
    ensure_writable(targets, args.overwrite)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.table_output.parent.mkdir(parents=True, exist_ok=True)

    args.table_output.write_text(render_table(estimates), encoding="utf-8")
    write_csv(summary_path, [asdict(item) for item in estimates])
    write_csv(checks_path, [asdict(item) for item in checks])
    metadata = [
        {"section": "implementation", "metric": "run_label", "value": RUN_LABEL},
        {"section": "implementation", "metric": "version", "value": args.implementation_version},
        {"section": "implementation", "metric": "generated_utc", "value": datetime.now(timezone.utc).isoformat()},
        {"section": "definition", "metric": "outcome", "value": PRIMARY_OUTCOME},
        {"section": "definition", "metric": "confidence_level", "value": args.confidence_level},
        {"section": "input", "metric": "overall_summary_file", "value": args.overall_summary_file},
        {"section": "input", "metric": "localized_static_file", "value": args.localized_static_file},
        {"section": "output", "metric": "table", "value": args.table_output},
        {"section": "qc", "metric": "checks", "value": len(checks)},
        {"section": "qc", "metric": "failures", "value": len(failures)},
    ]
    write_csv(metadata_path, metadata)
    return estimates, checks


def synthetic_inputs(root: Path) -> tuple[Path, Path]:
    overall = root / "overall.csv"
    localized = root / "localized.csv"
    overall_rows: list[dict[str, object]] = []
    for outcome_id, outcome in (
        ("O1", PRIMARY_OUTCOME), ("O2", "o2"), ("O3", "o3"), ("O4", "o4")
    ):
        for specification in SPECIFICATIONS:
            key = ("ALL", "ALL", specification)
            expected_estimate, se, percent, _, _ = EXPECTED_ROUNDED[key]
            target = math.log1p(percent / 100.0)
            estimate = min(max(target, expected_estimate - 0.000499), expected_estimate + 0.000499)
            assert round(estimate, 3) == expected_estimate
            if outcome_id != "O1":
                estimate, se = 0.1, 0.2
            z = NormalDist().inv_cdf(0.975)
            p_value = math.erfc(abs(estimate / se) / math.sqrt(2.0))
            overall_rows.append({
                "outcome_id": outcome_id, "outcome": outcome,
                "specification": specification, "estimate": estimate,
                "std_error": se, "p_value": p_value,
                "conf_low": estimate - z * se, "conf_high": estimate + z * se,
                "percent_change": 100.0 * math.expm1(estimate),
            })
    write_csv(overall, overall_rows)

    localized_rows: list[dict[str, object]] = []
    for detector in DETECTORS:
        for scope in SCOPES:
            for specification in SPECIFICATIONS:
                expected_estimate, se, percent, _, _ = EXPECTED_ROUNDED[
                    (detector, scope, specification)
                ]
                target = math.log1p(percent / 100.0)
                estimate = min(max(target, expected_estimate - 0.000499), expected_estimate + 0.000499)
                assert round(estimate, 3) == expected_estimate
                z = NormalDist().inv_cdf(0.975)
                p_value = math.erfc(abs(estimate / se) / math.sqrt(2.0))
                localized_rows.append({
                    "term": "treat", "estimate": estimate, "std.error": se,
                    "conf.low": estimate - z * se, "conf.high": estimate + z * se,
                    "p_value": p_value, "percent_change": 100.0 * math.expm1(estimate),
                    "specification": specification,
                    "first_stage_formula": (
                        "~ log_age + ncloc + log_contributors + log_stars + log_issues | repo_id + time_index"
                        if specification == "FECS" else "~ 1 | repo_id + time_index"
                    ),
                    "outcome": (
                        f"log_lines_added_py_source_localized_{detector.lower()}_"
                        f"{scope.lower().replace('+', '_')}"
                    ),
                    "detector": detector, "scope": scope,
                    "treated_observations": 363, "first_stage_observations": 1591,
                    "treatment_repositories": 63, "control_repositories": 104,
                })
    write_csv(localized, localized_rows)
    return overall, localized


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="run-y-b12-self-test-") as tmp:
        root = Path(tmp)
        overall, localized = synthetic_inputs(root)
        args = argparse.Namespace(
            overall_summary_file=overall,
            localized_static_file=localized,
            output_dir=root / "output",
            table_output=root / "table.tex",
            implementation_version="v1",
            confidence_level=0.95,
            strict_expected_counts=1,
            expected_overall_rows=8,
            expected_localized_rows=12,
            expected_treated_observations=363,
            expected_first_stage_observations=1591,
            expected_treatment_repositories=63,
            expected_control_repositories=104,
            overwrite=False,
        )
        estimates, checks = execute(args)
        assert len(estimates) == 14
        assert checks and all(item.passed for item in checks)
        table = args.table_output.read_text(encoding="utf-8")
        assert r"\label{tb:did-velocity-python}" in table
        assert r"\FpyLocalized{d}{s}{\tau_d}" in table
        assert r"(\text{\tiny NPR},\text{\tiny RF})" in table
        assert r"(\text{\tiny ML},\text{\tiny RF})" in table
    print("SELF-TEST PASS: inputs, statistics, sample counts, manuscript rounding, and LaTeX output")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.self_test:
            run_self_test()
            return 0
        estimates, checks = execute(args)
        indexed = index_estimates(estimates)
        for detector, scope in (("ALL", "ALL"),) + tuple(
            (detector, scope) for detector in DETECTORS for scope in SCOPES
        ):
            label = "Fpy" if detector == "ALL" else f"{detector}/{scope}"
            fecs = indexed[(detector, scope, "FECS")]
            feos = indexed[(detector, scope, "FEOS")]
            print(
                f"{label}: FECS ATT={fecs.estimate:.3f}, SE={fecs.std_error:.3f}, "
                f"change={fecs.percent_change:+.1f}%; FEOS ATT={feos.estimate:.3f}, "
                f"SE={feos.std_error:.3f}, change={feos.percent_change:+.1f}%"
            )
        print(f"PASS: {sum(item.passed for item in checks)} reconciliation checks")
        print(f"Table: {args.table_output}")
        print(f"Outputs: {args.output_dir}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
