#!/usr/bin/env python3
"""Summarize NPR-localized issue-burden DiD estimates for the paper table.

This version retains the validated parsing, reconciliation, output, and
self-test patterns of the Python issue-burden summarizer. The NPR-specific
entry point below combines RF and CM estimates from run-x-l04 v2 with RF+CM
estimates from run-x-l02 v1 and writes the revised threshold table.

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


@dataclass
class Check:
    check: str
    status: str
    detail: str


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


# ---------------------------------------------------------------------------
# NPR threshold-table v1 implementation
# ---------------------------------------------------------------------------

NPR_SCOPE_ORDER = ("RF", "CM", "RF+CM")
NPR_MODEL_ORDER = ("FECS", "FEOS")
NPR_TABLE_NAME = "tb_did_quality_npr_static_thresholds-v3.tex"
NPR_SUMMARY_CSV = "python_quality_npr_threshold_did_summary.csv"
NPR_SUMMARY_JSON = "python_quality_npr_threshold_did_summary.json"
NPR_CHECKS_CSV = "python_quality_npr_threshold_did_summary_checks.csv"
NPR_OUTPUT_NAMES = (
    NPR_TABLE_NAME,
    NPR_SUMMARY_CSV,
    NPR_SUMMARY_JSON,
    NPR_CHECKS_CSV,
)
NPR_TABLE_ROLES = {"sensitivity_grid", "primary"}
NPR_ALL_ROLES = {
    "sensitivity_grid",
    "primary",
    "legacy_anchor",
    "prior_primary_anchor",
}
NPR_REQUIRED_COLUMNS = (
    "sample_spec",
    "threshold_id",
    "term",
    "estimate",
    "std.error",
    "conf.low",
    "conf.high",
    "p_value",
    "exp_coefficient_change_pct",
    "threshold_role",
    "grid_order",
    "delta_from_primary",
    "threshold",
    "comparison_operator",
    "model_spec",
    "outcome",
    "outcome_role",
    "term_type",
    "model_status",
)


@dataclass
class NprEstimate:
    scope: str
    threshold_id: str
    threshold_role: str
    grid_order: int
    delta_from_primary: float
    threshold: float
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
    included_in_table: bool


def parse_npr_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create the RF, CM, and RF+CM NPR threshold-sensitivity table "
            "from completed static-effect CSV files."
        )
    )
    parser.add_argument("--rf-input", type=Path)
    parser.add_argument("--cm-input", type=Path)
    parser.add_argument("--rf-cm-input", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--sample-spec", default="exclude_scope_mismatch_repos")
    parser.add_argument("--fecs-spec", default="adjusted_burden")
    parser.add_argument("--feos-spec", default="fe_only_burden")
    parser.add_argument("--primary-threshold", type=float, default=1.515059)
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument(
        "--omit-delta",
        type=float,
        default=0.50,
        help="Grid offset omitted from the paper table for compactness",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if not 0.0 < args.confidence_level < 1.0:
        parser.error("--confidence-level must be between zero and one")
    if not args.self_test:
        required = ("rf_input", "cm_input", "rf_cm_input", "output_dir")
        missing = [name for name in required if getattr(args, name) is None]
        if missing:
            parser.error(
                "required arguments: "
                + ", ".join("--" + name.replace("_", "-") for name in missing)
            )
    return args


def npr_expected_grid() -> list[float]:
    return [round(-0.50 + 0.05 * index, 2) for index in range(21)]


def prepare_npr_scope(
    scope: str,
    path: Path,
    expected_scope_id: str,
    args: argparse.Namespace,
    checks: list[Check],
) -> list[NprEstimate]:
    rows = read_csv(path)
    require_columns(rows, NPR_REQUIRED_COLUMNS, path)
    selected = [row for row in rows if row["sample_spec"] == args.sample_spec]
    add_check(
        checks,
        f"{scope}: selected sample contains 46 rows",
        len(selected) == 46,
        f"found {len(selected)} rows for {args.sample_spec}",
    )
    roles = {row["threshold_role"] for row in selected}
    add_check(
        checks,
        f"{scope}: threshold roles",
        roles == NPR_ALL_ROLES,
        f"observed={sorted(roles)}",
    )
    if "scope_id" in rows[0]:
        scope_ids = {row["scope_id"].strip().lower() for row in selected}
        add_check(
            checks,
            f"{scope}: scope identifier",
            scope_ids == {expected_scope_id},
            f"observed={sorted(scope_ids)}",
        )

    model_map = {args.fecs_spec: "FECS", args.feos_spec: "FEOS"}
    selected = [
        row
        for row in selected
        if row["model_spec"] in model_map
        and row["outcome"] == "log1p_selected_issue_total"
        and row["outcome_role"] == "primary_burden"
        and row["term"] == "treat"
        and row["term_type"] == "static_att"
    ]
    add_check(
        checks,
        f"{scope}: required total-burden estimates",
        len(selected) == 46,
        f"found {len(selected)} rows",
    )

    z_value = NormalDist().inv_cdf(0.5 + args.confidence_level / 2.0)
    seen: set[tuple[str, str]] = set()
    estimates: list[NprEstimate] = []
    for row in selected:
        key = (row["threshold_id"], row["model_spec"])
        if key in seen:
            raise ValueError(f"Duplicate threshold/model row in {path}: {key}")
        seen.add(key)
        specification = model_map[row["model_spec"]]
        context = f"{scope}/{row['threshold_id']}/{specification}"
        estimate = number(row, "estimate", context)
        std_error = number(row, "std.error", context)
        p_value = number(row, "p_value", context)
        conf_low = number(row, "conf.low", context)
        conf_high = number(row, "conf.high", context)
        reported_percent = number(
            row, "exp_coefficient_change_pct", context
        )
        delta = number(row, "delta_from_primary", context)
        threshold = number(row, "threshold", context)
        computed_percent = 100.0 * math.expm1(estimate)
        derived_low = estimate - z_value * std_error
        derived_high = estimate + z_value * std_error
        excludes_zero = conf_low > 0.0 or conf_high < 0.0

        add_check(
            checks,
            f"{context}: successful model",
            row["model_status"] == "success",
            f"status={row['model_status']!r}",
        )
        add_check(
            checks,
            f"{context}: strict comparison",
            row["comparison_operator"] == ">",
            f"operator={row['comparison_operator']!r}",
        )
        add_check(
            checks,
            f"{context}: threshold equals primary plus offset",
            math.isclose(
                threshold,
                args.primary_threshold + delta,
                rel_tol=0.0,
                abs_tol=5e-9,
            ),
            (
                f"threshold={threshold:.9f}; "
                f"expected={args.primary_threshold + delta:.9f}"
            ),
        )
        add_check(
            checks,
            f"{context}: confidence interval",
            math.isclose(conf_low, derived_low, rel_tol=0.0, abs_tol=5e-9)
            and math.isclose(
                conf_high, derived_high, rel_tol=0.0, abs_tol=5e-9
            ),
            (
                f"reported=[{conf_low:.12g}, {conf_high:.12g}]; "
                f"derived=[{derived_low:.12g}, {derived_high:.12g}]"
            ),
        )
        add_check(
            checks,
            f"{context}: percentage change",
            math.isclose(
                reported_percent,
                computed_percent,
                rel_tol=0.0,
                abs_tol=5e-9,
            ),
            (
                f"reported={reported_percent:.12g}; "
                f"computed={computed_percent:.12g}"
            ),
        )
        add_check(
            checks,
            f"{context}: p value and 95 percent interval",
            (p_value < 0.05) == excludes_zero,
            f"p={p_value:.12g}; CI=[{conf_low:.12g}, {conf_high:.12g}]",
        )

        role = row["threshold_role"]
        grid_order = (
            integer(row, "grid_order", context)
            if row["grid_order"].strip()
            else -1
        )
        estimates.append(
            NprEstimate(
                scope=scope,
                threshold_id=row["threshold_id"],
                threshold_role=role,
                grid_order=grid_order,
                delta_from_primary=delta,
                threshold=threshold,
                specification=specification,
                model_spec=row["model_spec"],
                estimate=estimate,
                std_error=std_error,
                p_value=p_value,
                conf_low=conf_low,
                conf_high=conf_high,
                percent_change=computed_percent,
                significance_marker=significance_marker(p_value),
                ci_marker=(r"\checkmark" if excludes_zero else r"\times"),
                included_in_table=(
                    role in NPR_TABLE_ROLES
                    and not math.isclose(
                        delta,
                        args.omit_delta,
                        rel_tol=0.0,
                        abs_tol=5e-9,
                    )
                ),
            )
        )

    grid = sorted(
        {
            round(item.delta_from_primary, 2)
            for item in estimates
            if item.threshold_role in NPR_TABLE_ROLES
            and item.specification == "FECS"
        }
    )
    add_check(
        checks,
        f"{scope}: complete prespecified threshold grid",
        grid == npr_expected_grid(),
        f"observed={grid}",
    )
    add_check(
        checks,
        f"{scope}: one primary threshold per specification",
        sum(item.threshold_role == "primary" for item in estimates) == 2,
        (
            "primary rows="
            f"{sum(item.threshold_role == 'primary' for item in estimates)}"
        ),
    )
    return estimates


def validate_npr_cross_scope(
    estimates: Sequence[NprEstimate], checks: list[Check]
) -> None:
    signatures: dict[str, set[tuple[str, str, int, float, float]]] = {}
    for scope in NPR_SCOPE_ORDER:
        signatures[scope] = {
            (
                item.threshold_id,
                item.threshold_role,
                item.grid_order,
                round(item.delta_from_primary, 9),
                round(item.threshold, 9),
            )
            for item in estimates
            if item.scope == scope and item.specification == "FECS"
        }
    reference = signatures["RF"]
    for scope in ("CM", "RF+CM"):
        add_check(
            checks,
            f"{scope}: threshold definitions match RF",
            signatures[scope] == reference,
            (
                f"RF definitions={len(reference)}; "
                f"{scope} definitions={len(signatures[scope])}"
            ),
        )


def npr_threshold_label(delta: float) -> str:
    base = r"\tau_{\text{\tiny NPR}}"
    if math.isclose(delta, 0.0, rel_tol=0.0, abs_tol=5e-9):
        return r"\textbf{$" + base + r"$}"
    operator = "+" if delta > 0.0 else "-"
    return "$" + base + operator + f"{abs(delta):.2f}" + "$"


def npr_att_cell(item: NprEstimate) -> str:
    marker = (
        f"^{{{item.significance_marker}}}"
        if item.significance_marker
        else ""
    )
    return (
        "$"
        + r"\substack{"
        + f"{item.estimate:.3f}{marker}"
        + rf"\,({item.ci_marker})\\({item.std_error:.3f})"
        + "}"
        + "$"
    )


def npr_percent_cell(item: NprEstimate) -> str:
    value = round(item.percent_change, 1)
    if value == 0.0:
        value = 0.0
    return "$" + f"{value:+.1f}" + r"\%$"


def npr_latex_table(
    estimates: Sequence[NprEstimate],
    omitted_delta: float,
) -> str:
    selected = [item for item in estimates if item.included_in_table]
    lookup = {
        (item.delta_from_primary, item.scope, item.specification): item
        for item in selected
    }
    deltas = sorted(
        {
            item.delta_from_primary
            for item in selected
            if item.scope == "RF" and item.specification == "FECS"
        }
    )
    omitted_operator = "+" if omitted_delta >= 0.0 else "-"
    omitted_label = (
        r"$\tau_{\text{\tiny NPR}}"
        + omitted_operator
        + f"{abs(omitted_delta):.2f}"
        + "$"
    )
    lines = [
        r"\begin{table*}[!t]",
        r"\centering",
        r"\tiny",
        r"\setlength{\tabcolsep}{1.1pt}",
        (
            r"\caption{Effects of Cursor adoption on log-transformed monthly "
            r"NPR-localized issue burden across localization scopes and "
            r"thresholds. Percentage changes are computed as "
            r"$100(e^{\mathrm{ATT}}-1)$. Parentheses report "
            r"repository-clustered standard errors; $\checkmark$ and "
            r"$\times$ indicate whether 95\% confidence intervals exclude "
            r"or include zero, respectively. Significance: "
            r"$^{***}p<0.001$, $^{**}p<0.01$, $^{*}p<0.05$, and "
            r"$^{\dagger}p<0.10$. The "
            + omitted_label
            + r" endpoint is omitted.}"
        ),
        r"\label{tb:did_quality_fun_npr_static}",
        r"\begin{tabular}{@{}c|cc|cc|cc|cc|cc|cc@{}}",
        (
            r"& \multicolumn{4}{c|}{\tableheader{RF}} "
            r"& \multicolumn{4}{c|}{\tableheader{CM}} "
            r"& \multicolumn{4}{c}{\tableheader{RF+CM}} \\"
        ),
        (
            r"\tableheader{$\tau'_{\text{\tiny NPR}}$} "
            r"& \tableheader{\FECS{} ATT} & \tableheader{$\Delta\%$} "
            r"& \tableheader{\FEOS{} ATT} & \tableheader{$\Delta\%$} "
            r"& \tableheader{\FECS{} ATT} & \tableheader{$\Delta\%$} "
            r"& \tableheader{\FEOS{} ATT} & \tableheader{$\Delta\%$} "
            r"& \tableheader{\FECS{} ATT} & \tableheader{$\Delta\%$} "
            r"& \tableheader{\FEOS{} ATT} & \tableheader{$\Delta\%$} \\"
        ),
        r"\midrule",
    ]
    for delta in deltas:
        if math.isclose(delta, 0.0, rel_tol=0.0, abs_tol=5e-9):
            lines.append(r"\midrule")
        cells = [npr_threshold_label(delta)]
        for scope in NPR_SCOPE_ORDER:
            for specification in NPR_MODEL_ORDER:
                item = lookup[(delta, scope, specification)]
                cells.extend([npr_att_cell(item), npr_percent_cell(item)])
        lines.append(" & ".join(cells) + r" \\")
    lines.extend(
        [
            r"\end{tabular}",
            r"\vspace{-.1in}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def write_npr_outputs(
    estimates: Sequence[NprEstimate],
    checks: Sequence[Check],
    args: argparse.Namespace,
) -> None:
    failed = [check for check in checks if check.status != "PASS"]
    if failed:
        details = "\n".join(
            f"- {check.check}: {check.detail}" for check in failed[:20]
        )
        raise ValueError(
            f"Reconciliation checks failed ({len(failed)}):\n{details}"
        )
    output_dir = args.output_dir
    if output_dir.exists() and not output_dir.is_dir():
        raise FileExistsError(f"Output path is not a directory: {output_dir}")
    existing = [
        output_dir / name
        for name in NPR_OUTPUT_NAMES
        if (output_dir / name).exists()
    ]
    if existing and not args.overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(
            f"Generated output files exist (use --overwrite): {joined}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="npr-threshold-summary-", dir=output_dir
    ) as temp_name:
        temp_dir = Path(temp_name)
        (temp_dir / NPR_TABLE_NAME).write_text(
            npr_latex_table(estimates, args.omit_delta),
            encoding="utf-8",
        )
        summary_rows = [asdict(item) for item in estimates]
        with (temp_dir / NPR_SUMMARY_CSV).open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(
                handle, fieldnames=list(summary_rows[0])
            )
            writer.writeheader()
            writer.writerows(summary_rows)
        with (temp_dir / NPR_CHECKS_CSV).open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(
                handle, fieldnames=("check", "status", "detail")
            )
            writer.writeheader()
            writer.writerows(asdict(check) for check in checks)
        payload = {
            "version": "v1",
            "table_file": NPR_TABLE_NAME,
            "sample_spec": args.sample_spec,
            "model_specs": {
                "FECS": args.fecs_spec,
                "FEOS": args.feos_spec,
            },
            "primary_threshold": args.primary_threshold,
            "confidence_level": args.confidence_level,
            "omitted_delta": args.omit_delta,
            "inputs": {
                "RF": str(args.rf_input),
                "CM": str(args.cm_input),
                "RF+CM": str(args.rf_cm_input),
            },
            "results": summary_rows,
            "checks_passed": len(checks),
        }
        (temp_dir / NPR_SUMMARY_JSON).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        for name in NPR_OUTPUT_NAMES:
            (temp_dir / name).replace(output_dir / name)


def run_npr(
    args: argparse.Namespace,
) -> tuple[list[NprEstimate], list[Check]]:
    sources = (
        ("RF", args.rf_input, "rf"),
        ("CM", args.cm_input, "cm"),
        ("RF+CM", args.rf_cm_input, "rf+cm"),
    )
    checks: list[Check] = []
    estimates: list[NprEstimate] = []
    for scope, path, scope_id in sources:
        estimates.extend(
            prepare_npr_scope(scope, path, scope_id, args, checks)
        )
    validate_npr_cross_scope(estimates, checks)
    write_npr_outputs(estimates, checks, args)
    return estimates, checks


def npr_fixture_rows(scope_id: str) -> list[dict[str, object]]:
    definitions: list[tuple[str, str, int, float]] = []
    for index, delta in enumerate(npr_expected_grid()):
        if delta == 0.0:
            threshold_id, role = "primary", "primary"
        else:
            sign = "m" if delta < 0.0 else "p"
            threshold_id = f"grid_{sign}{abs(int(round(delta * 100))):03d}"
            role = "sensitivity_grid"
        definitions.append((threshold_id, role, index, delta))
    definitions.extend(
        [
            ("legacy_15183", "legacy_anchor", 10, 0.003241),
            (
                "prior_primary_1571637",
                "prior_primary_anchor",
                10,
                0.056578,
            ),
        ]
    )
    rows: list[dict[str, object]] = []
    scope_shift = {"rf": 0.05, "cm": 0.02, "rf+cm": 0.03}[scope_id]
    z_value = NormalDist().inv_cdf(0.975)
    for threshold_id, role, grid_order, delta in definitions:
        for model_spec, model_shift in (
            ("adjusted_burden", 0.0),
            ("fe_only_burden", 0.10),
        ):
            estimate = 0.20 + scope_shift + model_shift - 0.10 * delta
            std_error = 0.10
            z_score = abs(estimate / std_error)
            p_value = 2.0 * (1.0 - NormalDist().cdf(z_score))
            row: dict[str, object] = {
                "sample_spec": "exclude_scope_mismatch_repos",
                "threshold_id": threshold_id,
                "term": "treat",
                "estimate": estimate,
                "std.error": std_error,
                "conf.low": estimate - z_value * std_error,
                "conf.high": estimate + z_value * std_error,
                "p_value": p_value,
                "exp_coefficient_change_pct": 100.0 * math.expm1(estimate),
                "threshold_role": role,
                "grid_order": grid_order,
                "delta_from_primary": delta,
                "threshold": 1.515059 + delta,
                "comparison_operator": ">",
                "model_spec": model_spec,
                "outcome": "log1p_selected_issue_total",
                "outcome_role": "primary_burden",
                "term_type": "static_att",
                "model_status": "success",
            }
            if scope_id != "rf+cm":
                row["scope_id"] = scope_id
            rows.append(row)
    return rows


def write_npr_fixture(
    path: Path, rows: Sequence[Mapping[str, object]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def npr_self_test() -> None:
    with tempfile.TemporaryDirectory(
        prefix="python-quality-npr-threshold-summary-test-"
    ) as temp_name:
        root = Path(temp_name)
        paths = {
            "rf": root / "inputs" / "rf.csv",
            "cm": root / "inputs" / "cm.csv",
            "rf+cm": root / "inputs" / "rf_cm.csv",
        }
        for scope_id, path in paths.items():
            write_npr_fixture(path, npr_fixture_rows(scope_id))
        args = argparse.Namespace(
            rf_input=paths["rf"],
            cm_input=paths["cm"],
            rf_cm_input=paths["rf+cm"],
            output_dir=root / "output",
            sample_spec="exclude_scope_mismatch_repos",
            fecs_spec="adjusted_burden",
            feos_spec="fe_only_burden",
            primary_threshold=1.515059,
            confidence_level=0.95,
            omit_delta=0.50,
            overwrite=False,
            self_test=True,
        )
        estimates, checks = run_npr(args)
        assert len(estimates) == 138
        assert checks and all(check.status == "PASS" for check in checks)
        latex = (args.output_dir / NPR_TABLE_NAME).read_text(
            encoding="utf-8"
        )
        assert r"\tau_{\text{\tiny NPR}}+0.45" in latex
        assert latex.count(r"\tau_{\text{\tiny NPR}}+0.50") == 1
        assert r"\FECS{} ATT" in latex
        assert r"\Delta\%" in latex
    print("PASS: internal end-to-end test")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_npr_args(argv)
    try:
        if args.self_test:
            npr_self_test()
            return 0
        estimates, checks = run_npr(args)
    except (FileNotFoundError, FileExistsError, ValueError, AssertionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    primary = {
        (item.scope, item.specification): item
        for item in estimates
        if item.threshold_role == "primary"
    }
    for scope in NPR_SCOPE_ORDER:
        left = primary[(scope, "FECS")]
        right = primary[(scope, "FEOS")]
        print(
            f"{scope}: FECS ATT={left.estimate:.3f}, "
            f"SE={left.std_error:.3f}, change={left.percent_change:+.1f}%; "
            f"FEOS ATT={right.estimate:.3f}, SE={right.std_error:.3f}, "
            f"change={right.percent_change:+.1f}%"
        )
    print(f"PASS: {len(checks)} reconciliation checks")
    print(f"Outputs: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
