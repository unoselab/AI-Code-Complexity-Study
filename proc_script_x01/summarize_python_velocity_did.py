#!/usr/bin/env python3
"""Summarize static Python-velocity DiD estimates and write the paper table.

The script reads the FECS and FEOS static-effects CSV files produced by
run-x-b03, validates their study metadata, and writes:

* tb_did_velocity_python-v1.latex
* python_velocity_did_summary.csv
* python_velocity_did_summary.json
* python_velocity_did_summary_checks.csv

Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Iterable, Mapping, Sequence


OUTCOMES = (
    ("O1", "log_lines_added_py_source", "source additions (SA)"),
    ("O2", "log_lines_added_py_no_merge", "non-merge additions"),
    ("O3", "log_lines_added_py_source_no_tests", "SA excluding tests"),
    ("O4", "log_lines_added_py_all", "all additions"),
)


@dataclass(frozen=True)
class Estimate:
    outcome_id: str
    outcome: str
    outcome_description: str
    specification: str
    estimate: float
    std_error: float
    p_value: float
    conf_low: float
    conf_high: float
    percent_change: float
    significance_marker: str
    ci_marker: str


@dataclass(frozen=True)
class Check:
    check: str
    status: str
    detail: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create the compact FECS/FEOS Python-velocity DiD table from "
            "run-x-b03 static-effects CSV files."
        )
    )
    parser.add_argument("--fecs-input", type=Path, help="FECS static-effects CSV")
    parser.add_argument("--feos-input", type=Path, help="FEOS static-effects CSV")
    parser.add_argument("--output-dir", type=Path, help="Directory for generated outputs")
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument("--expected-backend", default="sonarqube")
    parser.add_argument("--expected-fecs-spec", default="python_ncloc_adjusted")
    parser.add_argument("--expected-feos-spec", default="no_covariates")
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument("--expected-treated-observations", type=int, default=363)
    parser.add_argument("--expected-first-stage-observations", type=int, default=1591)
    parser.add_argument("--expected-panel-observations", type=int, default=1954)
    parser.add_argument(
        "--verify-manuscript-rounding",
        action="store_true",
        help="Check the rounded ATT, SE, p-value marker, and CI marker used in the manuscript",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run an internal end-to-end test and exit",
    )
    args = parser.parse_args(argv)
    if not args.self_test:
        missing = [
            name
            for name in ("fecs_input", "feos_input", "output_dir")
            if getattr(args, name) is None
        ]
        if missing:
            parser.error("required arguments: " + ", ".join("--" + x.replace("_", "-") for x in missing))
    return args


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        return [dict(row) for row in reader]


def require_columns(rows: Sequence[Mapping[str, str]], columns: Iterable[str], path: Path) -> None:
    if not rows:
        raise ValueError(f"CSV has no data rows: {path}")
    missing = [column for column in columns if column not in rows[0]]
    if missing:
        raise ValueError(f"Missing columns in {path}: {', '.join(missing)}")


def number(row: Mapping[str, str], column: str, context: str) -> float:
    value = row.get(column, "")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {column} for {context}: {value!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"Non-finite {column} for {context}: {value!r}")
    return parsed


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


def add_check(checks: list[Check], name: str, condition: bool, detail: str) -> None:
    checks.append(Check(name, "PASS" if condition else "FAIL", detail))


def prepare_rows(
    path: Path,
    specification_label: str,
    expected_spec: str,
    args: argparse.Namespace,
    checks: list[Check],
) -> dict[str, Estimate]:
    rows = read_csv(path)
    required = (
        "ncloc_backend",
        "covariate_spec",
        "outcome",
        "term",
        "term_type",
        "estimate",
        "std.error",
        "conf.low",
        "conf.high",
        "p_value",
        "exp_coefficient_change_pct",
        "treated_observations",
        "first_stage_observations",
        "treatment_repositories",
        "control_repositories",
    )
    require_columns(rows, required, path)
    wanted_names = {item[1] for item in OUTCOMES}
    selected = [
        row
        for row in rows
        if row["outcome"] in wanted_names
        and row["term"] == "treat"
        and row["term_type"] == "static_att"
    ]
    add_check(
        checks,
        f"{specification_label}: four required static ATT rows",
        len(selected) == 4,
        f"found {len(selected)} rows in {path}",
    )
    by_outcome: dict[str, Mapping[str, str]] = {}
    for row in selected:
        name = row["outcome"]
        if name in by_outcome:
            raise ValueError(f"Duplicate static ATT row for {name} in {path}")
        by_outcome[name] = row
    missing = wanted_names - set(by_outcome)
    if missing:
        raise ValueError(f"Missing required outcomes in {path}: {', '.join(sorted(missing))}")

    z_value = NormalDist().inv_cdf(0.5 + args.confidence_level / 2.0)
    results: dict[str, Estimate] = {}
    for outcome_id, outcome, description in OUTCOMES:
        row = by_outcome[outcome]
        context = f"{specification_label}/{outcome_id}"
        estimate = number(row, "estimate", context)
        std_error = number(row, "std.error", context)
        p_value = number(row, "p_value", context)
        conf_low = number(row, "conf.low", context)
        conf_high = number(row, "conf.high", context)
        reported_percent = number(row, "exp_coefficient_change_pct", context)
        computed_percent = 100.0 * math.expm1(estimate)
        derived_low = estimate - z_value * std_error
        derived_high = estimate + z_value * std_error
        ci_excludes_zero = conf_low > 0.0 or conf_high < 0.0
        marker = r"\checkmark" if ci_excludes_zero else r"\times"

        add_check(
            checks,
            f"{context}: backend",
            row["ncloc_backend"] == args.expected_backend,
            f"observed={row['ncloc_backend']}; expected={args.expected_backend}",
        )
        add_check(
            checks,
            f"{context}: covariate specification",
            row["covariate_spec"] == expected_spec,
            f"observed={row['covariate_spec']}; expected={expected_spec}",
        )
        add_check(
            checks,
            f"{context}: reported CI matches estimate and SE",
            math.isclose(conf_low, derived_low, rel_tol=0.0, abs_tol=5e-10)
            and math.isclose(conf_high, derived_high, rel_tol=0.0, abs_tol=5e-10),
            (
                f"reported=[{conf_low:.12g}, {conf_high:.12g}]; "
                f"derived=[{derived_low:.12g}, {derived_high:.12g}]"
            ),
        )
        add_check(
            checks,
            f"{context}: reported percentage",
            math.isclose(reported_percent, computed_percent, rel_tol=0.0, abs_tol=5e-10),
            f"reported={reported_percent:.12g}; computed={computed_percent:.12g}",
        )
        add_check(
            checks,
            f"{context}: p value and CI agree at 95 percent",
            (p_value < 0.05) == ci_excludes_zero,
            f"p={p_value:.12g}; CI=[{conf_low:.12g}, {conf_high:.12g}]",
        )
        expected_counts = (
            ("treatment_repositories", args.expected_treatment_repositories),
            ("control_repositories", args.expected_control_repositories),
            ("treated_observations", args.expected_treated_observations),
            ("first_stage_observations", args.expected_first_stage_observations),
        )
        for column, expected in expected_counts:
            observed = integer(row, column, context)
            add_check(
                checks,
                f"{context}: {column}",
                observed == expected,
                f"observed={observed}; expected={expected}",
            )

        results[outcome_id] = Estimate(
            outcome_id=outcome_id,
            outcome=outcome,
            outcome_description=description,
            specification=specification_label,
            estimate=estimate,
            std_error=std_error,
            p_value=p_value,
            conf_low=conf_low,
            conf_high=conf_high,
            percent_change=computed_percent,
            significance_marker=significance_marker(p_value),
            ci_marker=marker,
        )
    return results


def manuscript_rounding_checks(
    fecs: Mapping[str, Estimate], feos: Mapping[str, Estimate], checks: list[Check]
) -> None:
    expected = {
        "O1": (0.574, 0.308, r"\dagger", r"\times", 1.100, 0.383, "**", r"\checkmark"),
        "O2": (0.547, 0.317, r"\dagger", r"\times", 1.104, 0.388, "**", r"\checkmark"),
        "O3": (0.582, 0.296, "*", r"\checkmark", 1.092, 0.369, "**", r"\checkmark"),
        "O4": (0.587, 0.311, r"\dagger", r"\times", 1.178, 0.395, "**", r"\checkmark"),
    }
    for outcome_id, values in expected.items():
        left = fecs[outcome_id]
        right = feos[outcome_id]
        observed = (
            round(left.estimate, 3),
            round(left.std_error, 3),
            left.significance_marker,
            left.ci_marker,
            round(right.estimate, 3),
            round(right.std_error, 3),
            right.significance_marker,
            right.ci_marker,
        )
        add_check(
            checks,
            f"{outcome_id}: manuscript ATT/SE/markers",
            observed == values,
            f"observed={observed}; expected={values}",
        )


def att_cell(value: Estimate) -> str:
    superscript = f"^{{{value.significance_marker}}}" if value.significance_marker else ""
    return (
        f"${value.estimate:.3f}{superscript}"
        rf"\;({value.ci_marker})\;({value.std_error:.3f})$"
    )


def percent_cell(value: Estimate) -> str:
    sign = "+" if value.percent_change >= 0 else ""
    return f"${sign}{value.percent_change:.1f}\\%$"


def latex_table(fecs: Mapping[str, Estimate], feos: Mapping[str, Estimate]) -> str:
    lines = [
        r"\begin{table}[!t]",
        r"\centering",
        r"\scriptsize",
        (
            r"\caption{Effects of Cursor adoption on log-transformed monthly Python code "
            r"additions. Outcomes are O1: source additions (SA), O2: non-merge additions, "
            r"O3: SA excluding tests, and O4: all additions. Percentage changes are computed "
            r"as $100(e^{\mathrm{ATT}}-1)$. $\checkmark$ and $\times$ denote 95\% confidence "
            r"intervals excluding and including zero, respectively. Standard errors are "
            r"repository-clustered and shown in parentheses.}"
        ),
        r"\label{tb:did-velocity-python}",
        r"\begin{tabular}{@{}l|cc|cc@{}}",
        r"  \tableheader{O$_n$}",
        r"& \tableheader{FECS ATT}",
        r"& \tableheader{$\Delta\%$}",
        r"& \tableheader{FEOS ATT}",
        r"& \tableheader{$\Delta\%$} \\",
        r"\midrule",
        "",
    ]
    for index, (outcome_id, _, _) in enumerate(OUTCOMES):
        lines.extend(
            [
                rf"\tableheader{{{outcome_id}}}",
                f"& {att_cell(fecs[outcome_id])}",
                f"& {percent_cell(fecs[outcome_id])}",
                f"& {att_cell(feos[outcome_id])}",
                f"& {percent_cell(feos[outcome_id])}" + r" \\",
            ]
        )
        if index < len(OUTCOMES) - 1:
            lines.append("")
    lines.extend([r"\end{tabular}", r"\vspace{-.1in}", r"\end{table}", ""])
    return "\n".join(lines)


def write_outputs(
    output_dir: Path,
    fecs: Mapping[str, Estimate],
    feos: Mapping[str, Estimate],
    checks: Sequence[Check],
    args: argparse.Namespace,
) -> None:
    failed = [check for check in checks if check.status != "PASS"]
    if failed:
        details = "\n".join(f"- {check.check}: {check.detail}" for check in failed)
        raise ValueError(f"Reconciliation checks failed:\n{details}")
    if output_dir.exists():
        if not args.overwrite:
            raise FileExistsError(f"Output directory exists (use --overwrite): {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    (output_dir / "tb_did_velocity_python-v1.latex").write_text(
        latex_table(fecs, feos), encoding="utf-8"
    )

    fieldnames = [
        "outcome_id",
        "outcome",
        "outcome_description",
        "specification",
        "estimate",
        "std_error",
        "p_value",
        "conf_low",
        "conf_high",
        "percent_change",
        "significance_marker",
        "ci_marker",
    ]
    estimates = [value for outcome_id, _, _ in OUTCOMES for value in (fecs[outcome_id], feos[outcome_id])]
    with (output_dir / "python_velocity_did_summary.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(value) for value in estimates)

    payload = {
        "method": {
            "percent_change": "100 * (exp(ATT) - 1)",
            "confidence_level": args.confidence_level,
            "ci_source": "reported run-x-b03 conf.low and conf.high",
            "standard_errors": "repository-clustered in run-x-b03",
        },
        "inputs": {"FECS": str(args.fecs_input), "FEOS": str(args.feos_input)},
        "results": [asdict(value) for value in estimates],
        "checks_passed": len(checks),
    }
    (output_dir / "python_velocity_did_summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    with (output_dir / "python_velocity_did_summary_checks.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=("check", "status", "detail"))
        writer.writeheader()
        writer.writerows(asdict(check) for check in checks)


def run(args: argparse.Namespace) -> tuple[dict[str, Estimate], dict[str, Estimate], list[Check]]:
    if not 0.0 < args.confidence_level < 1.0:
        raise ValueError("--confidence-level must be between zero and one")
    checks: list[Check] = []
    fecs = prepare_rows(
        args.fecs_input,
        "FECS",
        args.expected_fecs_spec,
        args,
        checks,
    )
    feos = prepare_rows(
        args.feos_input,
        "FEOS",
        args.expected_feos_spec,
        args,
        checks,
    )
    add_check(
        checks,
        "panel observation accounting",
        args.expected_treated_observations + args.expected_first_stage_observations
        == args.expected_panel_observations,
        (
            f"{args.expected_treated_observations} + "
            f"{args.expected_first_stage_observations} = "
            f"{args.expected_panel_observations}"
        ),
    )
    if args.verify_manuscript_rounding:
        manuscript_rounding_checks(fecs, feos, checks)
    write_outputs(args.output_dir, fecs, feos, checks, args)
    return fecs, feos, checks


def fixture_rows(spec: str) -> list[dict[str, object]]:
    values = {
        "python_ncloc_adjusted": (
            (0.574311671449486, 0.307706340865462, -0.0287816744614244, 1.1774050173604, 0.0619815354955579),
            (0.546883691585263, 0.316676184261006, -0.0737902243278797, 1.1675576074984, 0.084176782430522),
            (0.581689381108043, 0.296025557033314, 0.00148995081933978, 1.16188881139675, 0.0494145653694338),
            (0.58731997857174, 0.311055028258811, -0.0223366740256173, 1.1969766311691, 0.0590052003490784),
        ),
        "no_covariates": (
            (1.09979212045782, 0.382612132693905, 0.34988612032971, 1.84969812058594, 0.00404756383264601),
            (1.10449340207938, 0.387998852939599, 0.344029624274912, 1.86495717988385, 0.00441831723205239),
            (1.09233701502416, 0.369441547796904, 0.368244886949496, 1.81642914309883, 0.00310925412039979),
            (1.1777426151795, 0.394822516346816, 0.403904702854264, 1.95158052750474, 0.00285468587652211),
        ),
    }
    rows: list[dict[str, object]] = []
    for (_, outcome, _), (estimate, se, low, high, p_value) in zip(OUTCOMES, values[spec]):
        rows.append(
            {
                "ncloc_backend": "sonarqube",
                "covariate_spec": spec,
                "outcome": outcome,
                "term": "treat",
                "term_type": "static_att",
                "estimate": estimate,
                "std.error": se,
                "conf.low": low,
                "conf.high": high,
                "p_value": p_value,
                "exp_coefficient_change_pct": 100.0 * math.expm1(estimate),
                "treated_observations": 363,
                "first_stage_observations": 1591,
                "treatment_repositories": 63,
                "control_repositories": 104,
            }
        )
    return rows


def write_fixture(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="velocity-did-summary-") as temp_name:
        temp = Path(temp_name)
        fecs_input = temp / "fecs.csv"
        feos_input = temp / "feos.csv"
        output_dir = temp / "output"
        write_fixture(fecs_input, fixture_rows("python_ncloc_adjusted"))
        write_fixture(feos_input, fixture_rows("no_covariates"))
        args = parse_args(
            [
                "--fecs-input",
                str(fecs_input),
                "--feos-input",
                str(feos_input),
                "--output-dir",
                str(output_dir),
                "--verify-manuscript-rounding",
            ]
        )
        fecs, feos, checks = run(args)
        assert round(fecs["O1"].percent_change, 1) == 77.6
        assert round(feos["O2"].percent_change, 1) == 201.8
        assert round(fecs["O3"].percent_change, 1) == 78.9
        assert round(feos["O4"].percent_change, 1) == 224.7
        assert all(check.status == "PASS" for check in checks)
        latex = (output_dir / "tb_did_velocity_python-v1.latex").read_text(encoding="utf-8")
        for expected in (r"$+77.6\%$", r"$+201.8\%$", r"^{\dagger}", r"\checkmark"):
            assert expected in latex
        assert latex.count(r" \\") == 5
    print("PASS: internal end-to-end test")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.self_test:
            self_test()
            return 0
        fecs, feos, checks = run(args)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    for outcome_id, _, _ in OUTCOMES:
        left = fecs[outcome_id]
        right = feos[outcome_id]
        print(
            f"{outcome_id}: FECS ATT={left.estimate:.3f}, SE={left.std_error:.3f}, "
            f"change={left.percent_change:+.1f}%; FEOS ATT={right.estimate:.3f}, "
            f"SE={right.std_error:.3f}, change={right.percent_change:+.1f}%"
        )
    print(f"PASS: {len(checks)} reconciliation checks")
    print(f"Outputs: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
