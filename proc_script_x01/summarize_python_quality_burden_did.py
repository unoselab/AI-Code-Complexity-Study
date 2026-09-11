#!/usr/bin/env python3
"""Summarize Python issue-burden DiD estimates and write the paper table.

The script reads the run-x-b07 static-effects CSV, selects the FECS and FEOS
burden specifications, validates their study metadata, and writes:

* tb_did_quality_python_burden-v4.tex
* python_quality_burden_did_summary.csv
* python_quality_burden_did_summary.json
* python_quality_burden_did_summary_checks.csv

Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Iterable, Mapping, Sequence


OUTCOMES = (
    ("O1", "log_issue_total_py_sonarqube", "total issues"),
    ("O2", "log_issue_code_smell_py_sonarqube", "code smells"),
    ("O3", "log_issue_bug_py_sonarqube", "bugs"),
    ("O4", "log_issue_vulnerability_py_sonarqube", "vulnerabilities"),
    (
        "O5",
        "log_issue_maintainability_impact_py_sonarqube",
        "maintainability impact",
    ),
    ("O6", "log_issue_reliability_impact_py_sonarqube", "reliability impact"),
    ("O7", "log_issue_security_impact_py_sonarqube", "security impact"),
    ("O8", "log_issue_high_severity_py_sonarqube", "high-severity issues"),
)


@dataclass
class Estimate:
    outcome_id: str
    outcome: str
    outcome_description: str
    specification: str
    model_spec: str
    estimate: float
    std_error: float
    p_value: float
    conf_low: float
    conf_high: float
    percent_change: float
    significance_marker: str
    ci_marker: str


@dataclass
class Check:
    check: str
    status: str
    detail: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create the compact FECS/FEOS Python issue-burden table from the "
            "run-x-b07 static-effects CSV."
        )
    )
    parser.add_argument("--input", type=Path, help="run-x-b07 static-effects CSV")
    parser.add_argument("--output-dir", type=Path, help="Directory for generated outputs")
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument("--expected-fecs-spec", default="adjusted_burden")
    parser.add_argument("--expected-feos-spec", default="fe_only_burden")
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument("--expected-treated-observations", type=int, default=363)
    parser.add_argument("--expected-first-stage-observations", type=int, default=1591)
    parser.add_argument("--expected-panel-observations", type=int, default=1954)
    parser.add_argument(
        "--verify-manuscript-rounding",
        action="store_true",
        help="Check the rounded ATT, SE, percentage, and markers used in the manuscript",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the four generated files if they already exist",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run an internal end-to-end test and exit",
    )
    args = parser.parse_args(argv)
    if not args.self_test:
        missing = [
            name
            for name in ("input", "output_dir")
            if getattr(args, name) is None
        ]
        if missing:
            parser.error(
                "required arguments: "
                + ", ".join("--" + name.replace("_", "-") for name in missing)
            )
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


def boolean(row: Mapping[str, str], column: str, context: str) -> bool:
    value = row.get(column, "").strip().lower()
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    raise ValueError(f"Invalid Boolean {column} for {context}: {value!r}")


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


def prepare_specification(
    rows: Sequence[Mapping[str, str]],
    path: Path,
    specification_label: str,
    expected_model_spec: str,
    args: argparse.Namespace,
    checks: list[Check],
) -> dict[str, Estimate]:
    wanted_names = {item[1] for item in OUTCOMES}
    selected = [
        row
        for row in rows
        if row["model_spec"] == expected_model_spec
        and row["outcome"] in wanted_names
        and row["outcome_family"] == "burden"
        and row["term"] == "treat"
        and row["term_type"] == "static_att"
    ]
    add_check(
        checks,
        f"{specification_label}: eight required static ATT rows",
        len(selected) == len(OUTCOMES),
        f"found {len(selected)} rows in {path}",
    )

    by_outcome: dict[str, Mapping[str, str]] = {}
    for row in selected:
        name = row["outcome"]
        if name in by_outcome:
            raise ValueError(
                f"Duplicate static ATT row for {name}/{expected_model_spec} in {path}"
            )
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
        ci_marker = r"\checkmark" if ci_excludes_zero else r"\times"

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
        add_check(
            checks,
            f"{context}: significant field agrees with the 95 percent CI",
            boolean(row, "significant", context) == ci_excludes_zero,
            f"reported={row['significant']}; CI marker={ci_marker}",
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
            model_spec=expected_model_spec,
            estimate=estimate,
            std_error=std_error,
            p_value=p_value,
            conf_low=conf_low,
            conf_high=conf_high,
            percent_change=computed_percent,
            significance_marker=significance_marker(p_value),
            ci_marker=ci_marker,
        )
    return results


def manuscript_rounding_checks(
    fecs: Mapping[str, Estimate],
    feos: Mapping[str, Estimate],
    checks: list[Check],
) -> None:
    expected = {
        "O1": (0.283, 0.111, 32.7, "*", r"\checkmark", 0.443, 0.105, 55.8, "***", r"\checkmark"),
        "O2": (0.276, 0.110, 31.7, "*", r"\checkmark", 0.438, 0.104, 54.9, "***", r"\checkmark"),
        "O3": (0.281, 0.100, 32.4, "**", r"\checkmark", 0.369, 0.107, 44.6, "***", r"\checkmark"),
        "O4": (-0.005, 0.055, -0.5, "", r"\times", 0.021, 0.057, 2.1, "", r"\times"),
        "O5": (0.278, 0.110, 32.1, "*", r"\checkmark", 0.440, 0.104, 55.3, "***", r"\checkmark"),
        "O6": (0.187, 0.087, 20.6, "*", r"\checkmark", 0.296, 0.095, 34.4, "**", r"\checkmark"),
        "O7": (0.012, 0.054, 1.2, "", r"\times", 0.042, 0.057, 4.3, "", r"\times"),
        "O8": (0.194, 0.110, 21.4, r"\dagger", r"\times", 0.344, 0.102, 41.1, "***", r"\checkmark"),
    }
    for outcome_id, values in expected.items():
        left = fecs[outcome_id]
        right = feos[outcome_id]
        observed = (
            round(left.estimate, 3),
            round(left.std_error, 3),
            round(left.percent_change, 1),
            left.significance_marker,
            left.ci_marker,
            round(right.estimate, 3),
            round(right.std_error, 3),
            round(right.percent_change, 1),
            right.significance_marker,
            right.ci_marker,
        )
        add_check(
            checks,
            f"{outcome_id}: manuscript ATT/SE/percentage/markers",
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


def latex_table(
    fecs: Mapping[str, Estimate],
    feos: Mapping[str, Estimate],
    confidence_level: float,
) -> str:
    confidence_percent = 100.0 * confidence_level
    confidence_text = f"{confidence_percent:.0f}"
    descriptions = ", ".join(
        f"{outcome_id}: {description}" for outcome_id, _, description in OUTCOMES
    )
    lines = [
        r"\begin{table}[!t]",
        r"\centering",
        r"\scriptsize",
        (
            r"\caption{Effects of Cursor adoption on log-transformed monthly Python issue "
            f"burden. Outcomes are {descriptions}. Percentage changes are computed as "
            r"$100(e^{\mathrm{ATT}}-1)$. $\checkmark$ and $\times$ denote "
            f"{confidence_text}\\% confidence intervals excluding and including zero, "
            r"respectively. Standard errors are repository-clustered and shown in parentheses.}"
        ),
        r"\label{tb:did-quality-python-burden}",
        r"\begin{tabular}{@{}l|c@{\hspace{0.35em}}c|c@{\hspace{0.35em}}c@{}}",
        r"  \tableheader{O$_n$}",
        r"& \tableheader{\FECS{} ATT}",
        r"& \tableheader{$\Delta\%$}",
        r"& \tableheader{\FEOS{} ATT}",
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
        if index in {0, 3, 6}:
            lines.extend(["", r"\addlinespace"])
        elif index < len(OUTCOMES) - 1:
            lines.append("")
    lines.extend(["", r"\end{tabular}", r"\vspace{-.1in}", r"\end{table}", ""])
    return "\n".join(lines)


OUTPUT_NAMES = (
    "tb_did_quality_python_burden-v4.tex",
    "python_quality_burden_did_summary.csv",
    "python_quality_burden_did_summary.json",
    "python_quality_burden_did_summary_checks.csv",
)


def prepare_output_directory(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists() and not output_dir.is_dir():
        raise FileExistsError(f"Output path is not a directory: {output_dir}")
    existing = [output_dir / name for name in OUTPUT_NAMES if (output_dir / name).exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Generated output files exist (use --overwrite): {joined}")
    output_dir.mkdir(parents=True, exist_ok=True)


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
    prepare_output_directory(output_dir, args.overwrite)

    (output_dir / OUTPUT_NAMES[0]).write_text(
        latex_table(fecs, feos, args.confidence_level), encoding="utf-8"
    )

    fieldnames = [
        "outcome_id",
        "outcome",
        "outcome_description",
        "specification",
        "model_spec",
        "estimate",
        "std_error",
        "p_value",
        "conf_low",
        "conf_high",
        "percent_change",
        "significance_marker",
        "ci_marker",
    ]
    estimates = [
        value
        for outcome_id, _, _ in OUTCOMES
        for value in (fecs[outcome_id], feos[outcome_id])
    ]
    with (output_dir / OUTPUT_NAMES[1]).open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(value) for value in estimates)

    payload = {
        "method": {
            "percent_change": "100 * (exp(ATT) - 1)",
            "confidence_level": args.confidence_level,
            "ci_source": "reported run-x-b07 conf.low and conf.high",
            "standard_errors": "repository-clustered in run-x-b07",
        },
        "input": str(args.input),
        "model_specs": {
            "FECS": args.expected_fecs_spec,
            "FEOS": args.expected_feos_spec,
        },
        "results": [asdict(value) for value in estimates],
        "checks_passed": len(checks),
    }
    (output_dir / OUTPUT_NAMES[2]).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    with (output_dir / OUTPUT_NAMES[3]).open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=("check", "status", "detail"))
        writer.writeheader()
        writer.writerows(asdict(check) for check in checks)


def run(
    args: argparse.Namespace,
) -> tuple[dict[str, Estimate], dict[str, Estimate], list[Check]]:
    if not 0.0 < args.confidence_level < 1.0:
        raise ValueError("--confidence-level must be between zero and one")
    rows = read_csv(args.input)
    required = (
        "term",
        "estimate",
        "std.error",
        "conf.low",
        "conf.high",
        "outcome",
        "p_value",
        "exp_coefficient_change_pct",
        "significant",
        "model_spec",
        "outcome_family",
        "term_type",
        "treated_observations",
        "first_stage_observations",
        "treatment_repositories",
        "control_repositories",
    )
    require_columns(rows, required, args.input)

    checks: list[Check] = []
    fecs = prepare_specification(
        rows,
        args.input,
        "FECS",
        args.expected_fecs_spec,
        args,
        checks,
    )
    feos = prepare_specification(
        rows,
        args.input,
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


FIXTURE_VALUES = {
    "adjusted_burden": {
        "O1": (0.283131959228638, 0.110710529640128, 0.0661433084246336, 0.500120610032643, 0.0105455544520709),
        "O2": (0.275518351444509, 0.110193958241121, 0.0595421619780007, 0.491494540911017, 0.0124086912018211),
        "O3": (0.280793585316928, 0.100365134091593, 0.0840815371938724, 0.477505633439984, 0.00514646382240428),
        "O4": (-0.00497167891865876, 0.0549033737707436, -0.112580314139057, 0.10263695630174, 0.927847580516032),
        "O5": (0.278334419313168, 0.110383726960138, 0.0619862899919949, 0.49468254863434, 0.0116850103590321),
        "O6": (0.187280922115626, 0.087252163699788, 0.0162698236908481, 0.358292020540403, 0.0318384501118449),
        "O7": (0.0116106275571071, 0.0539358627307211, -0.0941017208702024, 0.117322975984417, 0.829558922586316),
        "O8": (0.193713562417393, 0.110222641905458, -0.0223188459981596, 0.409745970832947, 0.0788368410654342),
    },
    "fe_only_burden": {
        "O1": (0.443162879705867, 0.104809183781545, 0.237740654244999, 0.648585105166736, 2.35481585255617e-05),
        "O2": (0.437633983935839, 0.104073750262261, 0.23365318168579, 0.641614786185887, 2.61039301285915e-05),
        "O3": (0.368633336164091, 0.107430453007102, 0.158073517427347, 0.579193154900834, 0.000600547018373677),
        "O4": (0.0212210970609062, 0.0570750795697593, -0.0906440033105799, 0.133086197432392, 0.710034164727779),
        "O5": (0.440428741621211, 0.104222359490067, 0.236156670636894, 0.644700812605529, 2.38033587371664e-05),
        "O6": (0.295863901801165, 0.0952739065290155, 0.109130476337859, 0.48259732726447, 0.00190019754442064),
        "O7": (0.0419777557808154, 0.0569715017682786, -0.0696843358301707, 0.153639847391801, 0.461231671178969),
        "O8": (0.344164919287533, 0.102363661355875, 0.143535829704364, 0.544794008870702, 0.000773300685170297),
    },
}


def fixture_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    outcome_by_id = {outcome_id: outcome for outcome_id, outcome, _ in OUTCOMES}
    for model_spec, values in FIXTURE_VALUES.items():
        for outcome_id, (estimate, se, low, high, p_value) in values.items():
            rows.append(
                {
                    "term": "treat",
                    "estimate": estimate,
                    "std.error": se,
                    "conf.low": low,
                    "conf.high": high,
                    "outcome": outcome_by_id[outcome_id],
                    "p_value": p_value,
                    "exp_coefficient_change_pct": 100.0 * math.expm1(estimate),
                    "significant": str(low > 0.0 or high < 0.0).upper(),
                    "model_spec": model_spec,
                    "outcome_family": "burden",
                    "term_type": "static_att",
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
    with tempfile.TemporaryDirectory(prefix="quality-burden-did-summary-") as temp_name:
        temp = Path(temp_name)
        input_path = temp / "python_quality_static_effects.csv"
        output_dir = temp / "output"
        write_fixture(input_path, fixture_rows())
        args = parse_args(
            [
                "--input",
                str(input_path),
                "--output-dir",
                str(output_dir),
                "--verify-manuscript-rounding",
            ]
        )
        fecs, feos, checks = run(args)
        assert round(fecs["O1"].percent_change, 1) == 32.7
        assert round(feos["O2"].percent_change, 1) == 54.9
        assert fecs["O8"].significance_marker == r"\dagger"
        assert fecs["O8"].ci_marker == r"\times"
        assert all(check.status == "PASS" for check in checks)
        latex = (output_dir / OUTPUT_NAMES[0]).read_text(encoding="utf-8")
        for expected in (
            r"$+32.7\%$",
            r"$+55.8\%$",
            r"^{\dagger}",
            r"\checkmark",
            r"\FECS{} ATT",
            r"@{\hspace{0.35em}}",
        ):
            assert expected in latex
        assert latex.count(" \\\\") == len(OUTCOMES) + 1
    print("PASS: internal end-to-end test")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.self_test:
            self_test()
            return 0
        fecs, feos, checks = run(args)
    except (FileNotFoundError, FileExistsError, ValueError, AssertionError) as exc:
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
