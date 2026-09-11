#!/usr/bin/env python3
"""Summarize Python issue-density DiD estimates and write the paper table.

The script reads the run-x-b07-v2 static-effects CSV, selects the FECS and FEOS
density specifications, validates their study metadata, and writes:

* tb_did_quality_python_density-v1.tex
* python_quality_density_did_summary.csv
* python_quality_density_did_summary.json
* python_quality_density_did_summary_checks.csv

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
    ("O1", "log_issues_per_kloc_py_sonarqube", "total issues"),
    ("O2", "log_issue_code_smell_per_kloc_py_sonarqube", "code smells"),
    ("O3", "log_issue_bug_per_kloc_py_sonarqube", "bugs"),
    ("O4", "log_issue_vulnerability_per_kloc_py_sonarqube", "vulnerabilities"),
    (
        "O5",
        "log_issue_maintainability_impact_per_kloc_py_sonarqube",
        "maintainability impact",
    ),
    (
        "O6",
        "log_issue_reliability_impact_per_kloc_py_sonarqube",
        "reliability impact",
    ),
    ("O7", "log_issue_security_impact_per_kloc_py_sonarqube", "security impact"),
    (
        "O8",
        "log_issue_high_severity_per_kloc_py_sonarqube",
        "high-severity issues",
    ),
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
            "Create the compact FECS/FEOS Python issue-density table from the "
            "run-x-b07-v2 static-effects CSV."
        )
    )
    parser.add_argument("--input", type=Path, help="run-x-b07-v2 static-effects CSV")
    parser.add_argument("--output-dir", type=Path, help="Directory for generated outputs")
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument("--expected-fecs-spec", default="adjusted_density")
    parser.add_argument("--expected-feos-spec", default="fe_only_density")
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
            name for name in ("input", "output_dir") if getattr(args, name) is None
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
        and row["outcome_family"] == "density"
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
        "O1": (0.016, 0.066, 1.6, "", r"\times", 0.011, 0.067, 1.1, "", r"\times"),
        "O2": (0.010, 0.066, 1.0, "", r"\times", 0.006, 0.068, 0.6, "", r"\times"),
        "O3": (0.022, 0.037, 2.3, "", r"\times", 0.012, 0.038, 1.2, "", r"\times"),
        "O4": (-0.024, 0.022, -2.4, "", r"\times", -0.033, 0.023, -3.3, "", r"\times"),
        "O5": (0.012, 0.066, 1.2, "", r"\times", 0.008, 0.068, 0.8, "", r"\times"),
        "O6": (-0.055, 0.052, -5.4, "", r"\times", -0.056, 0.055, -5.4, "", r"\times"),
        "O7": (-0.032, 0.023, -3.1, "", r"\times", -0.042, 0.024, -4.1, r"\dagger", r"\times"),
        "O8": (-0.047, 0.057, -4.6, "", r"\times", -0.047, 0.059, -4.6, "", r"\times"),
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
    confidence_text = f"{100.0 * confidence_level:.0f}"
    description_items = [
        f"{outcome_id}: {description}" for outcome_id, _, description in OUTCOMES
    ]
    descriptions = ", ".join(description_items[:-1]) + ", and " + description_items[-1]
    lines = [
        r"\begin{table}[!t]",
        r"\centering",
        r"\scriptsize",
        (
            r"\caption{Effects of Cursor adoption on log-transformed monthly Python issue "
            f"density per KLOC. Outcomes are {descriptions}. Percentage changes are computed "
            r"as $100(e^{\mathrm{ATT}}-1)$. $\checkmark$ and $\times$ denote "
            f"{confidence_text}\\% confidence intervals excluding and including zero, "
            r"respectively. Standard errors are repository-clustered and shown in parentheses.}"
        ),
        r"\label{tb:did-quality-python-density}",
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
    "tb_did_quality_python_density-v1.tex",
    "python_quality_density_did_summary.csv",
    "python_quality_density_did_summary.json",
    "python_quality_density_did_summary_checks.csv",
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
            "ci_source": "reported run-x-b07-v2 conf.low and conf.high",
            "standard_errors": "repository-clustered in run-x-b07-v2",
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
    "adjusted_density": {
        "O1": (0.0158423215565816, 0.0656548177803232, -0.112838756704392, 0.144523399817555, 0.80932480612904),
        "O2": (0.0100063421206538, 0.0664870098291148, -0.120305802584172, 0.140318486825479, 0.880369591383303),
        "O3": (0.0223698590915522, 0.037208915382352, -0.050558274961656, 0.0952979931447605, 0.547709305188012),
        "O4": (-0.0241531897143284, 0.0219130153520347, -0.0671019105969897, 0.0187955311683329, 0.270361557774145),
        "O5": (0.012129322203453, 0.0664431483068265, -0.11809685549738, 0.142355499904286, 0.855149637239844),
        "O6": (-0.0552514641026508, 0.0515518737705221, -0.156291280028429, 0.0457883518231275, 0.283825857750505),
        "O7": (-0.0319271607922683, 0.0225183945763357, -0.0760624031515483, 0.0122080815670117, 0.156241629892602),
        "O8": (-0.0468925450971453, 0.0571116023851868, -0.158829228871483, 0.0650441386771927, 0.411607177617289),
    },
    "fe_only_density": {
        "O1": (0.0106956322980864, 0.0671622251037035, -0.120939910026744, 0.142331174622917, 0.873471349683477),
        "O2": (0.00608691957529786, 0.067983239335265, -0.127157781074188, 0.139331620224784, 0.928656268888313),
        "O3": (0.0116743310873434, 0.0383054338134378, -0.0634029395991774, 0.0867516017738641, 0.760541649378523),
        "O4": (-0.0332803011806606, 0.023377734666683, -0.0790998191674927, 0.0125392168061715, 0.15456529282345),
        "O5": (0.00835868609234746, 0.0679211400549957, -0.124764302204345, 0.14148167438904, 0.902055964708974),
        "O6": (-0.0559211823745475, 0.0547394481161479, -0.163208529215796, 0.0513661644667012, 0.306975774794966),
        "O7": (-0.041560221645396, 0.0235008928396917, -0.087621125215727, 0.00450068192493494, 0.0769852227905605),
        "O8": (-0.046582752345481, 0.0586423567746256, -0.161519659592296, 0.0683541549013337, 0.426989755934427),
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
                    "outcome_family": "density",
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
    with tempfile.TemporaryDirectory(prefix="quality-density-did-summary-") as temp_name:
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
        assert round(fecs["O1"].percent_change, 1) == 1.6
        assert round(feos["O7"].percent_change, 1) == -4.1
        assert feos["O7"].significance_marker == r"\dagger"
        assert feos["O7"].ci_marker == r"\times"
        assert all(value.ci_marker == r"\times" for value in fecs.values())
        assert all(value.ci_marker == r"\times" for value in feos.values())
        assert all(check.status == "PASS" for check in checks)
        latex = (output_dir / OUTPUT_NAMES[0]).read_text(encoding="utf-8")
        for expected in (
            r"$+1.6\%$",
            r"$-4.1\%$",
            r"^{\dagger}",
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
