#!/usr/bin/env python3
"""Summarize function-level AGC localization coverage for the manuscript.

This script produces descriptive occurrence-level statistics for the two frozen
AGC localization approaches used in the Python longitudinal study:

1. Perturbation-based NPR detection
   - Loads finalized A11 regular-function NPR scores.
   - Loads finalized A14 class-method NPR scores.
   - Reuses the A11 scores/exclusions for the A13-directed C_FUN/FUN overlap.
   - Streams the authoritative A05 primary code-unit manifest and counts
     regular-function and class-method occurrences above a frozen NPR threshold.

2. ML classification
   - Streams the finalized A03 regular-function occurrence predictions.
   - Streams the finalized A06 class-method occurrence predictions.
   - Counts occurrences classified as AGC using the frozen ``predicted_agc``
     label already produced upstream.

The script deliberately reports *historical function occurrences* rather than
pretending repeated source bodies are independent unique functions. It also
keeps regular functions and class methods separate in the output and then
reports their combined total, matching the manuscript convention that the term
"functions" collectively refers to both categories.

No quality outcome, SonarQube result, DiD estimate, or GMM estimate is read.
The output is descriptive detector-support information only.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, TextIO


SCRIPT_VERSION = "summarize-agc-function-localization-stats-v1"
DEFAULT_NPR_THRESHOLD = 1.571637
PRIMARY_ROLE = "primary"
FUN_TYPE = "function_body"
CFUN_TYPE = "method_body"

# Frozen project accounting used as hard QC by default.
EXPECTED_FUN_OCCURRENCES = 921_762
EXPECTED_CFUN_OCCURRENCES = 1_677_916
EXPECTED_PROCEDURE_OCCURRENCES = 2_599_678
EXPECTED_ML_AGC_OCCURRENCES = 817_836
EXPECTED_ML_HWC_OCCURRENCES = 1_781_842
EXPECTED_A13_REUSE_SHA = 3

NPR_SCORE_COLUMN = "code_unit_npr_space_by_token_weighted"


class DataContractError(RuntimeError):
    """Raised when an upstream frozen-data contract is violated."""


def clean(value: Any) -> str:
    """Return a stripped string, mapping None to an empty string."""
    return "" if value is None else str(value).strip()


def parse_boolish(value: Any, label: str) -> bool:
    """Parse common serialized Boolean representations."""
    text = clean(value).casefold()
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "no", "n", ""}:
        return False
    raise DataContractError(f"Unsupported Boolean value for {label}: {value!r}")


def parse_finite_float(value: Any, label: str) -> float:
    """Parse a finite floating-point value."""
    try:
        parsed = float(clean(value))
    except ValueError as exc:
        raise DataContractError(f"Invalid float for {label}: {value!r}") from exc
    if not math.isfinite(parsed):
        raise DataContractError(f"Non-finite float for {label}: {value!r}")
    return parsed


def open_text(path: Path) -> TextIO:
    """Open a plain or gzip-compressed UTF-8 text file."""
    if path.suffix.casefold() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def iter_csv(path: Path) -> Iterator[dict[str, str]]:
    """Stream a CSV or CSV.GZ file as dictionaries."""
    if not path.is_file():
        raise FileNotFoundError(path)
    with open_text(path) as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise DataContractError(f"CSV has no header: {path}")
        yield from reader


def read_header(path: Path) -> list[str]:
    """Read only the header of a CSV or CSV.GZ file."""
    if not path.is_file():
        raise FileNotFoundError(path)
    with open_text(path) as stream:
        reader = csv.reader(stream)
        return next(reader, [])


def require_columns(path: Path, required: Iterable[str], label: str) -> None:
    """Require a set of CSV columns before a long streaming pass."""
    header = set(read_header(path))
    missing = sorted(set(required) - header)
    if missing:
        raise DataContractError(f"{label} missing required columns {missing}: {path}")


def atomic_json(payload: Mapping[str, Any], path: Path) -> None:
    """Write JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")
    tmp.replace(path)


def atomic_csv(rows: list[Mapping[str, Any]], path: Path) -> None:
    """Write a compact key/value summary CSV atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    columns = ["section", "metric", "value"]
    with tmp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
    tmp.replace(path)


def discover_gpu_files(root: Path, filename: str) -> list[Path]:
    """Discover finalized per-GPU files under gpu-* directories."""
    paths = sorted(root.glob(f"gpu-*/{filename}"))
    if not paths:
        raise FileNotFoundError(f"No {filename} files found under {root}/gpu-*/")
    return paths


def load_npr_scores(root: Path, filename: str, label: str) -> dict[str, float]:
    """Load one finite NPR score per unique source SHA across finalized GPUs."""
    score_paths = discover_gpu_files(root, filename)
    scores: dict[str, float] = {}

    for path in score_paths:
        require_columns(
            path,
            {"code_unit_sha256", NPR_SCORE_COLUMN, "status", "partial_code_unit_score"},
            f"{label} unique NPR scores",
        )
        for row in iter_csv(path):
            sha = clean(row["code_unit_sha256"]).casefold()
            if not sha:
                raise DataContractError(f"Blank SHA in {path}")
            if sha in scores:
                raise DataContractError(f"Duplicate {label} finite SHA across GPU outputs: {sha}")
            if clean(row["status"]).casefold() != "scored":
                raise DataContractError(
                    f"Unexpected non-scored row in finite {label} output: {sha} status={row['status']!r}"
                )
            if parse_boolish(row["partial_code_unit_score"], f"{label}.{sha}.partial_code_unit_score"):
                raise DataContractError(f"Partial {label} NPR score is not eligible for this summary: {sha}")
            scores[sha] = parse_finite_float(row[NPR_SCORE_COLUMN], f"{label}.{sha}.{NPR_SCORE_COLUMN}")

    return scores


def load_exclusion_shas(root: Path, filename: str, label: str) -> set[str]:
    """Load unique SHA identities that have frozen expected NPR exclusions."""
    paths = discover_gpu_files(root, filename)
    excluded: set[str] = set()
    for path in paths:
        require_columns(path, {"code_unit_sha256"}, f"{label} NPR exclusions")
        for row in iter_csv(path):
            sha = clean(row["code_unit_sha256"]).casefold()
            if not sha:
                raise DataContractError(f"Blank exclusion SHA in {path}")
            excluded.add(sha)
    return excluded


def load_a13_reuse_shas(path: Path) -> set[str]:
    """Load the exact A13 C_FUN/FUN overlap identities that must reuse A11."""
    require_columns(path, {"code_unit_sha256"}, "A13 C_FUN A11 reuse plan")
    shas: set[str] = set()
    for row in iter_csv(path):
        sha = clean(row["code_unit_sha256"]).casefold()
        if not sha:
            raise DataContractError(f"Blank SHA in A13 reuse plan: {path}")
        if sha in shas:
            raise DataContractError(f"Duplicate SHA in A13 reuse plan: {sha}")
        shas.add(sha)
    return shas


def build_cfun_npr_maps(
    a14_scores: dict[str, float],
    a14_exclusions: set[str],
    a11_scores: dict[str, float],
    a11_exclusions: set[str],
    reuse_shas: set[str],
) -> tuple[dict[str, float], set[str]]:
    """Construct the C_FUN score/exclusion maps using the frozen A13 reuse contract."""
    if len(reuse_shas) != EXPECTED_A13_REUSE_SHA:
        raise DataContractError(
            f"A13 reuse SHA count {len(reuse_shas)} != frozen expected {EXPECTED_A13_REUSE_SHA}"
        )

    overlap = set(a14_scores) & reuse_shas
    if overlap:
        raise DataContractError(
            f"A14 new-score SHA unexpectedly overlaps A13 A11-reuse SHA: {sorted(overlap)[:5]}"
        )

    cfun_scores = dict(a14_scores)
    cfun_exclusions = set(a14_exclusions)

    for sha in reuse_shas:
        in_score = sha in a11_scores
        in_exclusion = sha in a11_exclusions
        if in_score == in_exclusion:
            raise DataContractError(
                f"A13 reuse SHA must resolve to exactly one A11 finite score or exclusion: {sha}; "
                f"finite={in_score}, excluded={in_exclusion}"
            )
        if in_score:
            cfun_scores[sha] = a11_scores[sha]
        else:
            cfun_exclusions.add(sha)

    if set(cfun_scores) & cfun_exclusions:
        raise DataContractError("C_FUN SHA appears in both finite-score and exclusion maps")
    return cfun_scores, cfun_exclusions


def empty_npr_counter() -> Counter[str]:
    """Create a counter with explicit NPR accounting fields."""
    return Counter(
        {
            "occurrences_total": 0,
            "occurrences_scored": 0,
            "occurrences_selected": 0,
            "occurrences_excluded": 0,
            "occurrences_missing": 0,
        }
    )


def scan_a05_npr_occurrences(
    manifest: Path,
    fun_scores: dict[str, float],
    fun_exclusions: set[str],
    cfun_scores: dict[str, float],
    cfun_exclusions: set[str],
    threshold: float,
) -> tuple[dict[str, Counter[str]], dict[str, set[str]]]:
    """Stream A05 and count primary function occurrences by NPR status and threshold."""
    require_columns(
        manifest,
        {"code_unit_type", "aggregation_role", "code_unit_sha256"},
        "A05 code-unit manifest",
    )

    counters = {
        "regular_function": empty_npr_counter(),
        "class_method": empty_npr_counter(),
    }
    unique_selected = {
        "regular_function": set(),
        "class_method": set(),
    }

    for row in iter_csv(manifest):
        if clean(row["aggregation_role"]).casefold() != PRIMARY_ROLE:
            continue
        code_type = clean(row["code_unit_type"])
        if code_type == FUN_TYPE:
            label = "regular_function"
            scores = fun_scores
            exclusions = fun_exclusions
        elif code_type == CFUN_TYPE:
            label = "class_method"
            scores = cfun_scores
            exclusions = cfun_exclusions
        else:
            continue

        sha = clean(row["code_unit_sha256"]).casefold()
        if not sha:
            raise DataContractError(f"Blank primary {code_type} SHA in A05 manifest")

        counter = counters[label]
        counter["occurrences_total"] += 1
        if sha in scores:
            counter["occurrences_scored"] += 1
            if scores[sha] > threshold:
                counter["occurrences_selected"] += 1
                unique_selected[label].add(sha)
        elif sha in exclusions:
            counter["occurrences_excluded"] += 1
        else:
            counter["occurrences_missing"] += 1

    return counters, unique_selected


def load_ml_i06_summary(path: Path) -> tuple[Counter[str], Counter[str]]:
    """Load authoritative ML occurrence accounting from the finalized I06 summary."""
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise DataContractError(f"I06 summary is not a JSON object: {path}")
    accounting = payload.get("accounting")
    if not isinstance(accounting, dict):
        raise DataContractError(f"I06 summary lacks an accounting object: {path}")

    required = {
        "fun_occurrences",
        "fun_agc_occurrences",
        "fun_hwc_occurrences",
        "cfun_occurrences",
        "cfun_agc_occurrences",
        "cfun_hwc_occurrences",
        "combined_occurrences",
        "combined_agc_occurrences",
        "combined_hwc_occurrences",
    }
    missing = sorted(required - set(accounting))
    if missing:
        raise DataContractError(f"I06 accounting missing keys {missing}: {path}")

    fun = Counter(
        occurrences_total=int(accounting["fun_occurrences"]),
        occurrences_agc=int(accounting["fun_agc_occurrences"]),
        occurrences_hwc=int(accounting["fun_hwc_occurrences"]),
    )
    cfun = Counter(
        occurrences_total=int(accounting["cfun_occurrences"]),
        occurrences_agc=int(accounting["cfun_agc_occurrences"]),
        occurrences_hwc=int(accounting["cfun_hwc_occurrences"]),
    )
    combined = combine_ml_counts(fun, cfun)
    expected_combined = {
        "occurrences_total": int(accounting["combined_occurrences"]),
        "occurrences_agc": int(accounting["combined_agc_occurrences"]),
        "occurrences_hwc": int(accounting["combined_hwc_occurrences"]),
    }
    for key, expected in expected_combined.items():
        if combined[key] != expected:
            raise DataContractError(
                f"I06 combined accounting mismatch for {key}: "
                f"components={combined[key]}, summary={expected}"
            )
    return fun, cfun


def scan_ml_occurrences(path: Path, expected_kind: str) -> Counter[str]:
    """Stream one finalized ML occurrence table and count AGC/HWC labels."""
    require_columns(path, {"predicted_agc"}, f"ML {expected_kind} occurrence predictions")
    header = set(read_header(path))
    counter: Counter[str] = Counter(
        {
            "occurrences_total": 0,
            "occurrences_agc": 0,
            "occurrences_hwc": 0,
        }
    )

    expected_type = FUN_TYPE if expected_kind == "regular_function" else CFUN_TYPE
    for row in iter_csv(path):
        if "aggregation_role" in header and clean(row.get("aggregation_role")).casefold() != PRIMARY_ROLE:
            raise DataContractError(
                f"ML {expected_kind} occurrence row is not aggregation_role=primary"
            )
        if "code_unit_type" in header and clean(row.get("code_unit_type")) != expected_type:
            raise DataContractError(
                f"ML {expected_kind} occurrence row has unexpected code_unit_type={row.get('code_unit_type')!r}"
            )

        predicted_agc = parse_boolish(row["predicted_agc"], f"ML {expected_kind}.predicted_agc")
        counter["occurrences_total"] += 1
        if predicted_agc:
            counter["occurrences_agc"] += 1
        else:
            counter["occurrences_hwc"] += 1

    return counter


def ratio(numerator: int, denominator: int) -> float | None:
    """Return a ratio or None when the denominator is zero."""
    return numerator / denominator if denominator else None


def combine_npr_counts(counters: dict[str, Counter[str]]) -> Counter[str]:
    """Sum regular-function and class-method NPR occurrence counts."""
    combined = empty_npr_counter()
    for counter in counters.values():
        combined.update(counter)
    return combined


def combine_ml_counts(fun: Counter[str], cfun: Counter[str]) -> Counter[str]:
    """Sum regular-function and class-method ML occurrence counts."""
    combined: Counter[str] = Counter()
    combined.update(fun)
    combined.update(cfun)
    return combined


def validate_frozen_accounting(
    npr_by_kind: dict[str, Counter[str]],
    ml_fun: Counter[str],
    ml_cfun: Counter[str],
    strict_expected_counts: bool,
) -> list[dict[str, Any]]:
    """Validate project-level accounting and return machine-readable QC rows."""
    qc: list[dict[str, Any]] = []

    def check(name: str, observed: Any, expected: Any, hard: bool = True) -> None:
        passed = observed == expected
        qc.append(
            {
                "check": name,
                "passed": passed,
                "observed": observed,
                "expected": expected,
                "hard": hard,
            }
        )
        if hard and strict_expected_counts and not passed:
            raise DataContractError(f"Frozen accounting check failed: {name}: {observed!r} != {expected!r}")

    check(
        "a05_regular_function_occurrences",
        npr_by_kind["regular_function"]["occurrences_total"],
        EXPECTED_FUN_OCCURRENCES,
    )
    check(
        "a05_class_method_occurrences",
        npr_by_kind["class_method"]["occurrences_total"],
        EXPECTED_CFUN_OCCURRENCES,
    )
    check(
        "ml_regular_function_occurrences",
        ml_fun["occurrences_total"],
        EXPECTED_FUN_OCCURRENCES,
    )
    check(
        "ml_class_method_occurrences",
        ml_cfun["occurrences_total"],
        EXPECTED_CFUN_OCCURRENCES,
    )

    ml_combined = combine_ml_counts(ml_fun, ml_cfun)
    check("ml_combined_occurrences", ml_combined["occurrences_total"], EXPECTED_PROCEDURE_OCCURRENCES)
    check("ml_agc_occurrences", ml_combined["occurrences_agc"], EXPECTED_ML_AGC_OCCURRENCES)
    check("ml_hwc_occurrences", ml_combined["occurrences_hwc"], EXPECTED_ML_HWC_OCCURRENCES)

    npr_combined = combine_npr_counts(npr_by_kind)
    check("a05_combined_function_occurrences", npr_combined["occurrences_total"], EXPECTED_PROCEDURE_OCCURRENCES)
    check(
        "npr_no_unexpected_missing_occurrences",
        npr_combined["occurrences_missing"],
        0,
    )
    check(
        "ml_and_a05_occurrence_universes_match",
        ml_combined["occurrences_total"],
        npr_combined["occurrences_total"],
    )
    return qc


def build_summary(
    threshold: float,
    npr_by_kind: dict[str, Counter[str]],
    npr_unique_selected: dict[str, set[str]],
    ml_fun: Counter[str],
    ml_cfun: Counter[str],
    qc: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the final manuscript-oriented summary object."""
    npr_combined = combine_npr_counts(npr_by_kind)
    ml_combined = combine_ml_counts(ml_fun, ml_cfun)

    npr_sections: dict[str, Any] = {}
    for label in ("regular_function", "class_method"):
        counter = npr_by_kind[label]
        npr_sections[label] = {
            **dict(counter),
            "selected_share_of_scored": ratio(counter["occurrences_selected"], counter["occurrences_scored"]),
            "scored_share_of_total": ratio(counter["occurrences_scored"], counter["occurrences_total"]),
            "selected_unique_sha_memberships": len(npr_unique_selected[label]),
        }
    npr_sections["combined"] = {
        **dict(npr_combined),
        "selected_share_of_scored": ratio(npr_combined["occurrences_selected"], npr_combined["occurrences_scored"]),
        "scored_share_of_total": ratio(npr_combined["occurrences_scored"], npr_combined["occurrences_total"]),
        "selected_unique_sha_memberships": len(npr_unique_selected["regular_function"])
        + len(npr_unique_selected["class_method"]),
    }

    def ml_section(counter: Counter[str]) -> dict[str, Any]:
        return {
            **dict(counter),
            "agc_share": ratio(counter["occurrences_agc"], counter["occurrences_total"]),
        }

    return {
        "script_version": SCRIPT_VERSION,
        "unit_of_analysis": "historical primary function occurrence",
        "function_definition": "regular functions + class methods",
        "npr_threshold": threshold,
        "npr_rule": f"{NPR_SCORE_COLUMN} > {threshold}",
        "npr": npr_sections,
        "ml": {
            "regular_function": ml_section(ml_fun),
            "class_method": ml_section(ml_cfun),
            "combined": ml_section(ml_combined),
        },
        "qc": qc,
    }


def summary_rows(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten headline statistics into a compact CSV."""
    rows: list[dict[str, Any]] = []
    for detector in ("npr", "ml"):
        section = summary[detector]
        for scope in ("regular_function", "class_method", "combined"):
            for metric, value in section[scope].items():
                rows.append({"section": f"{detector}.{scope}", "metric": metric, "value": value})
    return rows


def print_headline(summary: Mapping[str, Any]) -> None:
    """Print only the values needed to draft the Introduction finding paragraph."""
    npr = summary["npr"]["combined"]
    ml = summary["ml"]["combined"]
    print("=" * 78)
    print("Function-level AGC localization descriptive statistics")
    print(f"Script version:                    {summary['script_version']}")
    print(f"Historical function occurrences:   {npr['occurrences_total']:,}")
    print(f"NPR finite/scored occurrences:     {npr['occurrences_scored']:,}")
    print(f"NPR above-threshold occurrences:   {npr['occurrences_selected']:,}")
    print(f"NPR expected-excluded occurrences: {npr['occurrences_excluded']:,}")
    print(f"NPR unexpected-missing occurrences:{npr['occurrences_missing']:>10,}")
    print(f"ML classified occurrences:         {ml['occurrences_total']:,}")
    print(f"ML AGC-like occurrences:           {ml['occurrences_agc']:,}")
    print(f"ML HWC-like occurrences:           {ml['occurrences_hwc']:,}")
    print("=" * 78)


def run_self_test() -> None:
    """Exercise parsers and aggregation helpers without project data."""
    assert parse_boolish("1", "x") is True
    assert parse_boolish("false", "x") is False
    assert math.isclose(parse_finite_float("1.25", "x"), 1.25)

    npr = {
        "regular_function": Counter(
            occurrences_total=3,
            occurrences_scored=3,
            occurrences_selected=1,
            occurrences_excluded=0,
            occurrences_missing=0,
        ),
        "class_method": Counter(
            occurrences_total=2,
            occurrences_scored=1,
            occurrences_selected=1,
            occurrences_excluded=1,
            occurrences_missing=0,
        ),
    }
    combined = combine_npr_counts(npr)
    assert combined["occurrences_total"] == 5
    assert combined["occurrences_scored"] == 4
    assert combined["occurrences_selected"] == 2
    assert combined["occurrences_excluded"] == 1

    ml_fun = Counter(occurrences_total=3, occurrences_agc=1, occurrences_hwc=2)
    ml_cfun = Counter(occurrences_total=2, occurrences_agc=1, occurrences_hwc=1)
    ml_combined = combine_ml_counts(ml_fun, ml_cfun)
    assert ml_combined["occurrences_total"] == 5
    assert ml_combined["occurrences_agc"] == 2
    assert ml_combined["occurrences_hwc"] == 3
    assert math.isclose(ratio(2, 5) or 0.0, 0.4)

    print("summarize_agc_function_localization_stats self-test: PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize historical function-occurrence support for frozen NPR and ML AGC localization."
    )
    parser.add_argument(
        "--a05-code-manifest",
        type=Path,
        help="A05 python_code_unit_manifest.csv (or .csv.gz).",
    )
    parser.add_argument(
        "--a11-results-root",
        type=Path,
        help="A11 finalized root containing gpu-*/python_fun_unique_code_unit_npr_scores.csv.",
    )
    parser.add_argument(
        "--a13-reuse-file",
        type=Path,
        help="A13 python_cfun_reuse_from_a11.csv.",
    )
    parser.add_argument(
        "--a14-results-root",
        type=Path,
        help="A14 finalized root containing gpu-*/python_cfun_new_unique_code_unit_npr_scores.csv.",
    )
    parser.add_argument(
        "--ml-i06-summary",
        type=Path,
        help=(
            "Finalized I06 summary.json. This is the preferred lightweight ML input; "
            "if omitted, provide both --ml-fun-occurrences and --ml-cfun-occurrences."
        ),
    )
    parser.add_argument(
        "--ml-fun-occurrences",
        type=Path,
        help="A03 ml_fun_occurrence_predictions.csv (or .csv.gz).",
    )
    parser.add_argument(
        "--ml-cfun-occurrences",
        type=Path,
        help="A06 ml_cfun_occurrence_predictions.csv (or .csv.gz).",
    )
    parser.add_argument(
        "--npr-threshold",
        type=float,
        default=DEFAULT_NPR_THRESHOLD,
        help=f"Strict function-level NPR threshold; default {DEFAULT_NPR_THRESHOLD}.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("repo_x01/run-y-a01"),
        help="Directory for summary JSON/CSV outputs.",
    )
    parser.add_argument(
        "--no-strict-expected-counts",
        action="store_true",
        help="Report frozen-count mismatches in QC instead of failing immediately.",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def require_runtime_args(args: argparse.Namespace) -> None:
    """Require all production inputs unless running only the self-test."""
    required = {
        "--a05-code-manifest": args.a05_code_manifest,
        "--a11-results-root": args.a11_results_root,
        "--a13-reuse-file": args.a13_reuse_file,
        "--a14-results-root": args.a14_results_root,
    }
    missing = [flag for flag, value in required.items() if value is None]
    if missing:
        raise SystemExit("Missing required production arguments: " + ", ".join(missing))

    if args.ml_i06_summary is None:
        ml_missing = []
        if args.ml_fun_occurrences is None:
            ml_missing.append("--ml-fun-occurrences")
        if args.ml_cfun_occurrences is None:
            ml_missing.append("--ml-cfun-occurrences")
        if ml_missing:
            raise SystemExit(
                "Provide --ml-i06-summary, or provide both raw ML occurrence inputs: "
                + ", ".join(ml_missing)
            )


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return 0

    require_runtime_args(args)
    threshold = float(args.npr_threshold)
    if not math.isfinite(threshold):
        raise SystemExit("--npr-threshold must be finite")

    # Load finite NPR measurements and frozen expected exclusions.
    a11_scores = load_npr_scores(
        args.a11_results_root,
        "python_fun_unique_code_unit_npr_scores.csv",
        "A11 FUN",
    )
    a11_exclusions = load_exclusion_shas(
        args.a11_results_root,
        "python_fun_npr_exclusions.csv",
        "A11 FUN",
    )
    a14_scores = load_npr_scores(
        args.a14_results_root,
        "python_cfun_new_unique_code_unit_npr_scores.csv",
        "A14 C_FUN",
    )
    a14_exclusions = load_exclusion_shas(
        args.a14_results_root,
        "python_cfun_new_npr_exclusions.csv",
        "A14 C_FUN",
    )
    reuse_shas = load_a13_reuse_shas(args.a13_reuse_file)
    cfun_scores, cfun_exclusions = build_cfun_npr_maps(
        a14_scores,
        a14_exclusions,
        a11_scores,
        a11_exclusions,
        reuse_shas,
    )

    # Expand the content-level NPR measurements to exact historical occurrences.
    npr_by_kind, npr_unique_selected = scan_a05_npr_occurrences(
        args.a05_code_manifest,
        a11_scores,
        a11_exclusions,
        cfun_scores,
        cfun_exclusions,
        threshold,
    )

    # Prefer the finalized I06 accounting because it is a small, already-QC'd
    # artifact. Raw A03/A06 occurrence tables remain supported for independent
    # recomputation when desired.
    if args.ml_i06_summary is not None:
        ml_fun, ml_cfun = load_ml_i06_summary(args.ml_i06_summary)
    else:
        ml_fun = scan_ml_occurrences(args.ml_fun_occurrences, "regular_function")
        ml_cfun = scan_ml_occurrences(args.ml_cfun_occurrences, "class_method")

    qc = validate_frozen_accounting(
        npr_by_kind,
        ml_fun,
        ml_cfun,
        strict_expected_counts=not args.no_strict_expected_counts,
    )
    summary = build_summary(
        threshold,
        npr_by_kind,
        npr_unique_selected,
        ml_fun,
        ml_cfun,
        qc,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "function_localization_stats_summary.json"
    csv_path = args.output_dir / "function_localization_stats_summary.csv"
    atomic_json(summary, json_path)
    atomic_csv(summary_rows(summary), csv_path)

    print_headline(summary)
    print(f"Summary JSON: {json_path}")
    print(f"Summary CSV:  {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
