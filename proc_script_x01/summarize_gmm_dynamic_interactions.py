#!/usr/bin/env python3
"""Create the dynamic-panel GMM interaction table from analysis outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence


TRUE_VALUES = {"1", "true", "t", "yes", "y"}
FALSE_VALUES = {"0", "false", "f", "no", "n", ""}


@dataclass(frozen=True)
class TableRow:
    row_id: str
    detector: str
    scope: str
    quality_label: str
    direction_label: str
    estimate: float
    std_error: float
    p_value: float
    sargan_p: float
    ar1_p: float
    ar2_p: float
    source_coefficients: str
    source_diagnostics: str


class CheckRecorder:
    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []

    def add(self, check: str, observed: object, expected: object, passed: bool, note: str) -> None:
        self.rows.append(
            {
                "check": check,
                "observed": str(observed),
                "expected": str(expected),
                "status": "pass" if passed else "fail",
                "note": note,
            }
        )

    def require(self, condition: bool, check: str, observed: object, expected: object, note: str) -> None:
        self.add(check, observed, expected, condition, note)
        if not condition:
            raise ValueError(f"{check}: observed={observed}; expected={expected}. {note}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for prefix in ("whole", "npr", "ml-rf", "ml-cm", "ml-rf-cm"):
        parser.add_argument(f"--{prefix}-coefficients", required=True, type=Path)
        parser.add_argument(f"--{prefix}-diagnostics", required=True, type=Path)
    parser.add_argument("--output-tex", required=True, type=Path)
    parser.add_argument("--summary-csv", required=True, type=Path)
    parser.add_argument("--checks-csv", required=True, type=Path)
    parser.add_argument("--metadata-csv", required=True, type=Path)
    parser.add_argument("--implementation-version", default="v1")
    return parser.parse_args(argv)


def read_csv(path: Path, checks: CheckRecorder, label: str) -> list[dict[str, str]]:
    checks.require(path.is_file(), f"{label}_exists", path, "existing file", "The source CSV must exist.")
    checks.require(path.stat().st_size > 0, f"{label}_nonempty", path.stat().st_size, ">0", "The source CSV must not be empty.")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames or []
    checks.require(bool(fields), f"{label}_header", len(fields), ">0", "The source CSV must have a header.")
    checks.require(bool(rows), f"{label}_rows", len(rows), ">0", "The source CSV must contain data rows.")
    return rows


def parse_bool(value: object) -> bool:
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"Unrecognized Boolean value: {value!r}")


def parse_float(row: Mapping[str, str], field: str, context: str) -> float:
    if field not in row:
        raise ValueError(f"{context} is missing required field {field!r}")
    try:
        value = float(row[field])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} has a nonnumeric {field}: {row.get(field)!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{context} has a nonfinite {field}: {value}")
    return value


def primary_flag(row: Mapping[str, str]) -> bool:
    if "primary_analysis" in row:
        return parse_bool(row["primary_analysis"])
    return True


def select_one(rows: Iterable[dict[str, str]], predicate, context: str, checks: CheckRecorder) -> dict[str, str]:
    selected = [row for row in rows if predicate(row)]
    checks.require(len(selected) == 1, f"{context}_row_count", len(selected), 1, "Exactly one source row must identify the reported result.")
    return selected[0]


def is_primary_coefficient(row: Mapping[str, str]) -> bool:
    return parse_bool(row.get("is_primary_interaction_term", "false")) and primary_flag(row)


def full_sample(row: Mapping[str, str]) -> bool:
    return row.get("sample_spec", "full_sample").strip() == "full_sample"


def select_diagnostics(
    rows: list[dict[str, str]], model: str, context: str, checks: CheckRecorder
) -> dict[str, float]:
    result: dict[str, float] = {}
    for diagnostic in ("sargan", "ar1", "ar2"):
        row = select_one(
            rows,
            lambda item, diagnostic=diagnostic: (
                item.get("model", "").strip() == model
                and item.get("diagnostic", "").strip().lower() == diagnostic
                and full_sample(item)
                and primary_flag(item)
            ),
            f"{context}_{diagnostic}",
            checks,
        )
        result[diagnostic] = parse_float(row, "p_value", f"{context}/{diagnostic}")
    return result


def make_row(
    *, row_id: str, detector: str, scope: str, quality_label: str, direction_label: str,
    coefficient_row: dict[str, str], diagnostic_rows: list[dict[str, str]],
    coefficient_path: Path, diagnostic_path: Path, checks: CheckRecorder,
) -> TableRow:
    model = coefficient_row.get("model", "").strip()
    checks.require(bool(model), f"{row_id}_model", model, "nonempty", "A model identifier is required.")
    diagnostics = select_diagnostics(diagnostic_rows, model, row_id, checks)
    row = TableRow(
        row_id=row_id,
        detector=detector,
        scope=scope,
        quality_label=quality_label,
        direction_label=direction_label,
        estimate=parse_float(coefficient_row, "estimate", row_id),
        std_error=parse_float(coefficient_row, "std_error", row_id),
        p_value=parse_float(coefficient_row, "p_value", row_id),
        sargan_p=diagnostics["sargan"],
        ar1_p=diagnostics["ar1"],
        ar2_p=diagnostics["ar2"],
        source_coefficients=str(coefficient_path),
        source_diagnostics=str(diagnostic_path),
    )
    checks.require(row.std_error > 0, f"{row_id}_positive_se", row.std_error, ">0", "The reported standard error must be positive.")
    for name, value in (("p", row.p_value), ("sargan_p", row.sargan_p), ("ar1_p", row.ar1_p), ("ar2_p", row.ar2_p)):
        checks.require(0 <= value <= 1, f"{row_id}_{name}_range", value, "[0,1]", "Every p-value must be a probability.")
    reported_significant = parse_bool(coefficient_row.get("significant", str(row.p_value < 0.05)))
    checks.require(reported_significant == (row.p_value < 0.05), f"{row_id}_significance", reported_significant, row.p_value < 0.05, "The source significance flag must agree with p < 0.05.")
    if "conf_low" in coefficient_row and "conf_high" in coefficient_row:
        low = parse_float(coefficient_row, "conf_low", row_id)
        high = parse_float(coefficient_row, "conf_high", row_id)
        excludes_zero = low > 0 or high < 0
        checks.require(excludes_zero == (row.p_value < 0.05), f"{row_id}_ci_significance", excludes_zero, row.p_value < 0.05, "The 95% CI and two-sided p-value must agree at alpha=0.05.")
    return row


def load_rows(args: argparse.Namespace, checks: CheckRecorder) -> list[TableRow]:
    source_names = ("whole", "npr", "ml_rf", "ml_cm", "ml_rf_cm")
    data: dict[str, tuple[Path, Path, list[dict[str, str]], list[dict[str, str]]]] = {}
    for name in source_names:
        coefficient_path = getattr(args, f"{name}_coefficients")
        diagnostic_path = getattr(args, f"{name}_diagnostics")
        data[name] = (
            coefficient_path,
            diagnostic_path,
            read_csv(coefficient_path, checks, f"{name}_coefficients"),
            read_csv(diagnostic_path, checks, f"{name}_diagnostics"),
        )

    result: list[TableRow] = []
    whole_coef_path, whole_diag_path, whole_coef, whole_diag = data["whole"]
    for model, row_id, direction in (
        ("velocity_to_quality", "whole_velocity_to_quality", r"$V_t \rightarrow Q_t$"),
        ("quality_to_velocity", "whole_quality_to_velocity", r"$Q_{t-1} \rightarrow V_t$"),
    ):
        coefficient = select_one(
            whole_coef,
            lambda item, model=model: item.get("model", "").strip() == model and is_primary_coefficient(item),
            row_id,
            checks,
        )
        result.append(
            make_row(
                row_id=row_id, detector="all", scope="all", quality_label=r"$Q^{\mathrm{all}}$",
                direction_label=direction, coefficient_row=coefficient, diagnostic_rows=whole_diag,
                coefficient_path=whole_coef_path, diagnostic_path=whole_diag_path, checks=checks,
            )
        )

    npr_coef_path, npr_diag_path, npr_coef, npr_diag = data["npr"]
    for scope_id, scope_label in (("rf", "RF"), ("cm", "CM"), ("rf_cm", "RF{+}CM")):
        row_id = f"npr_{scope_id}"
        coefficient = select_one(
            npr_coef,
            lambda item, scope_id=scope_id: (
                full_sample(item) and item.get("scope_id", "").strip() == scope_id and is_primary_coefficient(item)
            ),
            row_id,
            checks,
        )
        result.append(
            make_row(
                row_id=row_id, detector="NPR", scope=scope_id,
                quality_label=rf"$Q^{{(\text{{\tiny NPR}},\text{{\tiny {scope_label}}})}}$",
                direction_label=r"$Q_{t-1} \rightarrow V_t$", coefficient_row=coefficient,
                diagnostic_rows=npr_diag, coefficient_path=npr_coef_path,
                diagnostic_path=npr_diag_path, checks=checks,
            )
        )

    for source_name, scope_id, scope_label in (
        ("ml_rf", "rf", "RF"),
        ("ml_cm", "cm", "CM"),
        ("ml_rf_cm", "rf_cm", "RF{+}CM"),
    ):
        coef_path, diag_path, coefficients, diagnostics = data[source_name]
        row_id = f"ml_{scope_id}"
        coefficient = select_one(
            coefficients,
            lambda item: full_sample(item) and is_primary_coefficient(item),
            row_id,
            checks,
        )
        result.append(
            make_row(
                row_id=row_id, detector="ML", scope=scope_id,
                quality_label=rf"$Q^{{(\text{{\tiny ML}},\text{{\tiny {scope_label}}})}}$",
                direction_label=r"$Q_{t-1} \rightarrow V_t$", coefficient_row=coefficient,
                diagnostic_rows=diagnostics, coefficient_path=coef_path,
                diagnostic_path=diag_path, checks=checks,
            )
        )

    checks.require(len(result) == 8, "table_row_count", len(result), 8, "The table must contain two whole-Python and six localized estimates.")
    checks.require(len({row.row_id for row in result}) == 8, "unique_row_ids", len({row.row_id for row in result}), 8, "Every table row must have a unique identifier.")
    return result


def format_number(value: float) -> str:
    return f"{value:.3f}"


def format_p(value: float) -> str:
    if value < 0.001:
        return r"$<.001$"
    return f"{value:.3f}".lstrip("0")


def emphasize(value: str, significant: bool) -> str:
    if not significant:
        return value
    if value.startswith("$") and value.endswith("$"):
        return rf"$\boldsymbol{{{value[1:-1]}}}$"
    return rf"\textbf{{{value}}}"


def render_tex(rows: list[TableRow]) -> str:
    lines = [
        r"\begin{table}[!t]",
        r"\centering",
        r"\scriptsize",
        r"\caption{Dynamic-panel GMM estimates of velocity--quality associations for $\Fpy$ and $\FpyLocalized{d}{s}{\tau_d}$. $p_{\mathrm{S}}$, $p_{\mathrm{AR1}}$, and $p_{\mathrm{AR2}}$ denote Sargan and Arellano--Bond test $p$-values.}",
        r"\label{tab:gmm-dynamic-interactions}",
        r"{\color{blue}",
        r"\begin{tabular}{@{}llrrrrrr@{}}",
        r"\textbf{Quality burden}",
        r"& \textbf{Direction}",
        r"& $\boldsymbol{\hat{\gamma}}$",
        r"& \textbf{SE}",
        r"& $\boldsymbol{p}$",
        r"& $\boldsymbol{p}_{\mathrm{S}}$",
        r"& $\boldsymbol{p}_{\mathrm{AR1}}$",
        r"& $\boldsymbol{p}_{\mathrm{AR2}}$ \\",
        r"\midrule",
        "",
    ]
    for index, row in enumerate(rows):
        if index in (2, 5):
            lines.append(r"\addlinespace")
        significant = row.p_value < 0.05
        estimate = emphasize(format_number(row.estimate), significant)
        p_value = emphasize(format_p(row.p_value), significant)
        lines.extend(
            [
                row.quality_label,
                f"& {row.direction_label}",
                f"& {estimate} & {format_number(row.std_error)} & {p_value} & {format_p(row.sargan_p)} & {format_p(row.ar1_p)} & {format_p(row.ar2_p)} \\\\",
            ]
        )
        if index != len(rows) - 1:
            lines.append("")
    lines.extend([r"\end{tabular}", r"}", r"\end{table}", ""])
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    checks = CheckRecorder()
    try:
        rows = load_rows(args, checks)
        tex = render_tex(rows)
        checks.require(r"\label{tab:gmm-dynamic-interactions}" in tex, "latex_label", "present", "present", "The requested table label must be preserved.")
        checks.require(r"\boldsymbol{p}_{\mathrm{S}}" in tex, "latex_sargan_header", "valid", "valid", "The Sargan p-value header must use a subscript.")
        checks.require("p*" not in tex, "latex_invalid_p_star", "absent", "absent", "The obsolete p* header notation must not appear.")

        args.output_tex.parent.mkdir(parents=True, exist_ok=True)
        args.output_tex.write_text(tex, encoding="utf-8")

        summary_rows = [
            {
                "row_id": row.row_id,
                "detector": row.detector,
                "scope": row.scope,
                "direction": row.direction_label.replace("$", ""),
                "estimate": f"{row.estimate:.15g}",
                "std_error": f"{row.std_error:.15g}",
                "p_value": f"{row.p_value:.15g}",
                "significant_05": str(row.p_value < 0.05).upper(),
                "sargan_p": f"{row.sargan_p:.15g}",
                "ar1_p": f"{row.ar1_p:.15g}",
                "ar2_p": f"{row.ar2_p:.15g}",
                "source_coefficients": row.source_coefficients,
                "source_diagnostics": row.source_diagnostics,
            }
            for row in rows
        ]
        write_csv(
            args.summary_csv,
            summary_rows,
            ["row_id", "detector", "scope", "direction", "estimate", "std_error", "p_value", "significant_05", "sargan_p", "ar1_p", "ar2_p", "source_coefficients", "source_diagnostics"],
        )

        checks.add("output_tex_sha256", sha256(args.output_tex), "recorded", True, "The generated table checksum is recorded.")
    except Exception as exc:
        checks.add("fatal_error", type(exc).__name__, "none", False, str(exc))
        write_csv(args.checks_csv, checks.rows, ["check", "observed", "expected", "status", "note"])
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_csv(args.checks_csv, checks.rows, ["check", "observed", "expected", "status", "note"])
    metadata = [
        {"key": "run_id", "value": "run-y-b10"},
        {"key": "implementation_version", "value": args.implementation_version},
        {"key": "generated_utc", "value": datetime.now(timezone.utc).isoformat()},
        {"key": "python_version", "value": sys.version.replace("\n", " ")},
        {"key": "table_rows", "value": str(len(rows))},
        {"key": "reconciliation_checks", "value": str(len(checks.rows))},
        {"key": "failed_checks", "value": str(sum(row["status"] == "fail" for row in checks.rows))},
        {"key": "output_tex", "value": str(args.output_tex)},
        {"key": "output_tex_sha256", "value": sha256(args.output_tex)},
    ]
    write_csv(args.metadata_csv, metadata, ["key", "value"])

    for row in rows:
        print(
            f"{row.row_id}: estimate={row.estimate:.3f}, SE={row.std_error:.3f}, "
            f"p={format_p(row.p_value).replace('$', '')}, "
            f"Sargan={format_p(row.sargan_p).replace('$', '')}, "
            f"AR1={format_p(row.ar1_p).replace('$', '')}, "
            f"AR2={format_p(row.ar2_p).replace('$', '')}"
        )
    print(f"PASS: {len(checks.rows)} reconciliation checks")
    print(f"Table: {args.output_tex}")
    print(f"Outputs: {args.summary_csv.parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
