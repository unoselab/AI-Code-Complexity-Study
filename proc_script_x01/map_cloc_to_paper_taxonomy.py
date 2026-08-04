#!/usr/bin/env python3
"""Map C04 cloc language rows to the paper-observed repository taxonomy.

The paper taxonomy is the set of unique labels observed in
``repos.csv:repo_languages`` and produced by run-x-c04a. The numeric byte values
from repos.csv are never used. This script maps cloc labels to those observed
labels, preserves every language-level row, and computes two repository NCLOC
metrics:

1. all cloc-recognized code lines from C04; and
2. code lines whose cloc language maps to at least one paper-observed label.

The mapping is deliberately conservative. Exact and case-normalized matches are
accepted automatically. A small explicit alias table handles known naming
mismatches between cloc and GitHub Linguist. All other cloc labels remain
unmapped and are excluded only from the paper-taxonomy-aligned metric.
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

IMPLEMENTATION_VERSION = "v1"
TAXONOMY_VERSION = "repos_csv_repo_languages_v1"
COUNT_BACKEND_ALL = "cloc_whole_repository_all_recognized_languages"
COUNT_BACKEND_TAXONOMY = "cloc_whole_repository_paper_observed_taxonomy"

# Explicit cloc-to-GitHub-Linguist naming aliases. Each target must exist in
# the C04a paper taxonomy. Multi-target aliases are used only for inclusion;
# code is counted once, never duplicated across targets.
MANUAL_ALIASES: dict[str, tuple[tuple[str, ...], str]] = {
    "ANTLR Grammar": (("ANTLR",), "cloc grammar label maps to GitHub Linguist ANTLR"),
    "Bourne Again Shell": (("Shell",), "cloc shell subtype maps to GitHub Linguist Shell"),
    "Bourne Shell": (("Shell",), "cloc shell subtype maps to GitHub Linguist Shell"),
    "Fish Shell": (("Shell",), "cloc shell subtype maps to GitHub Linguist Shell"),
    "C/C++ Header": (("C", "C++"), "shared C/C++ header family maps to accepted C and C++ labels"),
    "CUDA": (("Cuda",), "case and naming form used by GitHub Linguist"),
    "Cucumber": (("Gherkin",), "Cucumber feature files map to GitHub Linguist Gherkin"),
    "DOS Batch": (("Batchfile",), "cloc DOS Batch maps to GitHub Linguist Batchfile"),
    "JSX": (("JavaScript",), "JSX source maps to GitHub Linguist JavaScript"),
    "Jinja Template": (("Jinja",), "cloc template label maps to GitHub Linguist Jinja"),
    "LESS": (("Less",), "case and naming form used by GitHub Linguist"),
    "LLVM IR": (("LLVM",), "cloc IR label maps to GitHub Linguist LLVM"),
    "Vuejs Component": (("Vue",), "cloc component label maps to GitHub Linguist Vue"),
    "make": (("Makefile",), "cloc make label maps to GitHub Linguist Makefile"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Map C04 cloc language rows to the C04a paper-observed taxonomy."
    )
    parser.add_argument("--language-results-file", required=True, type=Path)
    parser.add_argument("--snapshot-results-file", required=True, type=Path)
    parser.add_argument("--repo-month-results-file", required=True, type=Path)
    parser.add_argument("--paper-language-types-file", required=True, type=Path)
    parser.add_argument("--mapping-output", required=True, type=Path)
    parser.add_argument("--mapped-language-results-output", required=True, type=Path)
    parser.add_argument("--snapshot-aggregates-output", required=True, type=Path)
    parser.add_argument("--repo-month-aggregates-output", required=True, type=Path)
    parser.add_argument("--excluded-language-summary-output", required=True, type=Path)
    parser.add_argument("--qc-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument("--strict-expected-counts", type=int, choices=(0, 1), default=1)
    parser.add_argument("--expected-language-rows", type=int, default=16815)
    parser.add_argument("--expected-cloc-language-types", type=int, default=76)
    parser.add_argument("--expected-paper-language-types", type=int, default=252)
    parser.add_argument("--expected-mapped-cloc-language-types", type=int, default=54)
    parser.add_argument("--expected-unmapped-cloc-language-types", type=int, default=22)
    parser.add_argument("--expected-snapshots", type=int, default=1828)
    parser.add_argument("--expected-repo-month-rows", type=int, default=2411)
    parser.add_argument("--expected-all-recognized-snapshot-code", type=int, default=190937444)
    parser.add_argument("--expected-paper-taxonomy-snapshot-code", type=int, default=117309450)
    parser.add_argument("--expected-all-recognized-repo-month-code", type=int, default=205349581)
    parser.add_argument("--expected-paper-taxonomy-repo-month-code", type=int, default=127617394)
    parser.add_argument("--expected-zero-ncloc-snapshots", type=int, default=5)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def require_columns(fieldnames: list[str], required: set[str], label: str) -> None:
    missing = sorted(required - set(fieldnames))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def as_int(value: object, *, field: str) -> int:
    text = "" if value is None else str(value).strip()
    if not text:
        return 0
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric value for {field}: {value!r}") from exc
    if not math.isfinite(number) or not number.is_integer():
        raise ValueError(f"Expected integer-compatible value for {field}: {value!r}")
    return int(number)


def bool_text(value: bool) -> str:
    return "True" if value else "False"


def add_qc(
    rows: list[dict[str, object]],
    check: str,
    observed: object,
    expected: object,
    passed: bool,
    severity: str = "error",
    note: str = "",
) -> None:
    rows.append(
        {
            "check": check,
            "observed": observed,
            "expected": expected,
            "severity": severity,
            "status": "pass" if passed else "fail",
            "note": note,
        }
    )


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    language_fields, language_rows = read_csv(args.language_results_file)
    snapshot_fields, snapshot_rows = read_csv(args.snapshot_results_file)
    repo_month_fields, repo_month_rows = read_csv(args.repo_month_results_file)
    paper_fields, paper_rows = read_csv(args.paper_language_types_file)

    require_columns(
        language_fields,
        {"repo_snapshot_key", "scope_role", "repo_name", "language", "files", "code"},
        "C04 language results",
    )
    require_columns(
        snapshot_fields,
        {"repo_snapshot_key", "scope_role", "repo_name", "ncloc_local_cloc_whole_repo", "status"},
        "C04 snapshot results",
    )
    require_columns(
        repo_month_fields,
        {"repo_snapshot_key", "scope_role", "repo_name", "time", "ncloc_local_cloc_whole_repo"},
        "C04 repo-month results",
    )
    require_columns(paper_fields, {"language_type"}, "C04a paper language types")

    paper_language_types = [row["language_type"].strip() for row in paper_rows if row["language_type"].strip()]
    paper_set = set(paper_language_types)
    if len(paper_set) != len(paper_language_types):
        raise ValueError("Duplicate language_type values found in the paper taxonomy")

    casefold_index: dict[str, str] = {}
    casefold_collisions: dict[str, list[str]] = defaultdict(list)
    for label in paper_language_types:
        casefold_collisions[label.casefold()].append(label)
    ambiguous_casefolds = {key: values for key, values in casefold_collisions.items() if len(values) > 1}
    if ambiguous_casefolds:
        raise ValueError(f"Case-insensitive taxonomy collisions found: {ambiguous_casefolds}")
    casefold_index = {label.casefold(): label for label in paper_language_types}

    invalid_alias_targets = sorted(
        {
            target
            for targets, _reason in MANUAL_ALIASES.values()
            for target in targets
            if target not in paper_set
        }
    )
    if invalid_alias_targets:
        raise ValueError(
            "Manual alias targets absent from the paper taxonomy: "
            + ", ".join(invalid_alias_targets)
        )

    label_stats: dict[str, dict[str, object]] = {}
    for row in language_rows:
        language = row["language"].strip()
        stats = label_stats.setdefault(
            language,
            {
                "language_rows": 0,
                "snapshot_keys": set(),
                "repo_names": set(),
                "files": 0,
                "code": 0,
            },
        )
        stats["language_rows"] = int(stats["language_rows"]) + 1
        cast_snapshot_keys = stats["snapshot_keys"]
        cast_repo_names = stats["repo_names"]
        assert isinstance(cast_snapshot_keys, set)
        assert isinstance(cast_repo_names, set)
        cast_snapshot_keys.add(row["repo_snapshot_key"])
        cast_repo_names.add(row["repo_name"])
        stats["files"] = int(stats["files"]) + as_int(row["files"], field="files")
        stats["code"] = int(stats["code"]) + as_int(row["code"], field="code")

    mapping_by_label: dict[str, dict[str, object]] = {}
    mapping_rows: list[dict[str, object]] = []
    for cloc_language in sorted(label_stats, key=str.casefold):
        if cloc_language in paper_set:
            targets = (cloc_language,)
            mapping_status = "exact"
            mapping_rule = "exact_label_match"
            rationale = "cloc label exactly matches a paper-observed repos.csv language label"
        elif cloc_language.casefold() in casefold_index:
            targets = (casefold_index[cloc_language.casefold()],)
            mapping_status = "case_normalized"
            mapping_rule = "case_insensitive_label_match"
            rationale = "cloc label differs only by case from a paper-observed label"
        elif cloc_language in MANUAL_ALIASES:
            targets, rationale = MANUAL_ALIASES[cloc_language]
            mapping_status = "manual_alias"
            mapping_rule = "explicit_cloc_to_linguist_alias"
        else:
            targets = ()
            mapping_status = "unmapped"
            mapping_rule = "no_paper_taxonomy_match"
            rationale = "no exact, case-normalized, or approved alias match in the 252 paper-observed labels"

        included = bool(targets)
        stats = label_stats[cloc_language]
        mapping = {
            "cloc_language": cloc_language,
            "paper_language_types": ";".join(targets),
            "mapping_status": mapping_status,
            "mapping_rule": mapping_rule,
            "mapping_rationale": rationale,
            "included_in_paper_taxonomy_ncloc": included,
            "language_rows": stats["language_rows"],
            "snapshot_count": len(stats["snapshot_keys"]),
            "repository_count": len(stats["repo_names"]),
            "files": stats["files"],
            "code": stats["code"],
            "paper_taxonomy_version": TAXONOMY_VERSION,
            "mapping_implementation_version": IMPLEMENTATION_VERSION,
        }
        mapping_by_label[cloc_language] = mapping
        mapping_rows.append(mapping)

    mapped_language_rows: list[dict[str, object]] = []
    snapshot_language_stats: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "mapped_code": 0,
            "unmapped_code": 0,
            "mapped_files": 0,
            "unmapped_files": 0,
            "mapped_labels": set(),
            "unmapped_labels": set(),
        }
    )

    for row in language_rows:
        mapping = mapping_by_label[row["language"].strip()]
        included = bool(mapping["included_in_paper_taxonomy_ncloc"])
        code = as_int(row["code"], field="code")
        files = as_int(row["files"], field="files")
        key = row["repo_snapshot_key"]
        stats = snapshot_language_stats[key]
        if included:
            stats["mapped_code"] = int(stats["mapped_code"]) + code
            stats["mapped_files"] = int(stats["mapped_files"]) + files
            cast_labels = stats["mapped_labels"]
            assert isinstance(cast_labels, set)
            cast_labels.add(row["language"].strip())
        else:
            stats["unmapped_code"] = int(stats["unmapped_code"]) + code
            stats["unmapped_files"] = int(stats["unmapped_files"]) + files
            cast_labels = stats["unmapped_labels"]
            assert isinstance(cast_labels, set)
            cast_labels.add(row["language"].strip())

        enriched = dict(row)
        enriched.update(
            {
                "paper_language_types": mapping["paper_language_types"],
                "paper_taxonomy_mapping_status": mapping["mapping_status"],
                "paper_taxonomy_mapping_rule": mapping["mapping_rule"],
                "included_in_paper_taxonomy_ncloc": bool_text(included),
                "paper_taxonomy_version": TAXONOMY_VERSION,
                "taxonomy_mapping_implementation_version": IMPLEMENTATION_VERSION,
            }
        )
        mapped_language_rows.append(enriched)

    snapshot_keys = [row["repo_snapshot_key"] for row in snapshot_rows]
    duplicate_snapshot_keys = [key for key, count in Counter(snapshot_keys).items() if count > 1]
    if duplicate_snapshot_keys:
        raise ValueError(f"Duplicate snapshot keys found: {duplicate_snapshot_keys[:5]}")

    snapshot_aggregate_by_key: dict[str, dict[str, object]] = {}
    snapshot_output_rows: list[dict[str, object]] = []
    snapshot_reconciliation_failures = 0
    zero_ncloc_snapshots = 0
    all_recognized_snapshot_code = 0
    paper_taxonomy_snapshot_code = 0

    for row in snapshot_rows:
        key = row["repo_snapshot_key"]
        all_code = as_int(row["ncloc_local_cloc_whole_repo"], field="ncloc_local_cloc_whole_repo")
        stats = snapshot_language_stats.get(
            key,
            {
                "mapped_code": 0,
                "unmapped_code": 0,
                "mapped_files": 0,
                "unmapped_files": 0,
                "mapped_labels": set(),
                "unmapped_labels": set(),
            },
        )
        mapped_code = int(stats["mapped_code"])
        unmapped_code = int(stats["unmapped_code"])
        reconciles = mapped_code + unmapped_code == all_code
        if not reconciles:
            snapshot_reconciliation_failures += 1
        if all_code == 0:
            zero_ncloc_snapshots += 1
            share: object = ""
        else:
            share = mapped_code / all_code

        mapped_labels = stats["mapped_labels"]
        unmapped_labels = stats["unmapped_labels"]
        assert isinstance(mapped_labels, set)
        assert isinstance(unmapped_labels, set)

        aggregate = {
            "ncloc_local_cloc_all_recognized": all_code,
            "ncloc_local_cloc_paper_taxonomy": mapped_code,
            "ncloc_local_cloc_not_in_paper_taxonomy": unmapped_code,
            "paper_taxonomy_code_share": share,
            "mapped_cloc_language_count": len(mapped_labels),
            "unmapped_cloc_language_count": len(unmapped_labels),
            "mapped_cloc_file_count": int(stats["mapped_files"]),
            "unmapped_cloc_file_count": int(stats["unmapped_files"]),
            "taxonomy_code_reconciles_all_recognized": bool_text(reconciles),
            "paper_taxonomy_version": TAXONOMY_VERSION,
            "taxonomy_mapping_implementation_version": IMPLEMENTATION_VERSION,
            "paper_taxonomy_count_backend": COUNT_BACKEND_TAXONOMY,
            "paper_taxonomy_metric_definition": (
                "sum of C04 cloc language-level code lines whose cloc language maps "
                "to at least one label observed in repos.csv:repo_languages"
            ),
        }
        snapshot_aggregate_by_key[key] = aggregate
        output_row = dict(row)
        output_row.update(aggregate)
        snapshot_output_rows.append(output_row)
        all_recognized_snapshot_code += all_code
        paper_taxonomy_snapshot_code += mapped_code

    repo_month_missing_snapshot_keys = 0
    repo_month_output_rows: list[dict[str, object]] = []
    all_recognized_repo_month_code = 0
    paper_taxonomy_repo_month_code = 0
    repo_month_reconciliation_failures = 0
    for row in repo_month_rows:
        key = row["repo_snapshot_key"]
        aggregate = snapshot_aggregate_by_key.get(key)
        if aggregate is None:
            repo_month_missing_snapshot_keys += 1
            aggregate = {
                "ncloc_local_cloc_all_recognized": "",
                "ncloc_local_cloc_paper_taxonomy": "",
                "ncloc_local_cloc_not_in_paper_taxonomy": "",
                "paper_taxonomy_code_share": "",
                "mapped_cloc_language_count": "",
                "unmapped_cloc_language_count": "",
                "mapped_cloc_file_count": "",
                "unmapped_cloc_file_count": "",
                "taxonomy_code_reconciles_all_recognized": "False",
                "paper_taxonomy_version": TAXONOMY_VERSION,
                "taxonomy_mapping_implementation_version": IMPLEMENTATION_VERSION,
                "paper_taxonomy_count_backend": COUNT_BACKEND_TAXONOMY,
                "paper_taxonomy_metric_definition": "",
            }
        else:
            original_all = as_int(
                row["ncloc_local_cloc_whole_repo"],
                field="repo_month.ncloc_local_cloc_whole_repo",
            )
            if original_all != int(aggregate["ncloc_local_cloc_all_recognized"]):
                repo_month_reconciliation_failures += 1
            all_recognized_repo_month_code += int(aggregate["ncloc_local_cloc_all_recognized"])
            paper_taxonomy_repo_month_code += int(aggregate["ncloc_local_cloc_paper_taxonomy"])
        output_row = dict(row)
        output_row.update(aggregate)
        repo_month_output_rows.append(output_row)

    all_language_code = sum(as_int(row["code"], field="language.code") for row in language_rows)
    mapped_language_code = sum(
        as_int(row["code"], field="language.code")
        for row in language_rows
        if bool(mapping_by_label[row["language"].strip()]["included_in_paper_taxonomy_ncloc"])
    )
    unmapped_language_code = all_language_code - mapped_language_code

    mapped_label_count = sum(
        bool(row["included_in_paper_taxonomy_ncloc"]) for row in mapping_rows
    )
    unmapped_label_count = len(mapping_rows) - mapped_label_count

    excluded_rows = [row for row in mapping_rows if not row["included_in_paper_taxonomy_ncloc"]]
    for row in excluded_rows:
        code = int(row["code"])
        row["share_of_all_recognized_code"] = code / all_language_code if all_language_code else ""
        row["share_of_excluded_code"] = code / unmapped_language_code if unmapped_language_code else ""
    excluded_rows.sort(key=lambda row: (-int(row["code"]), str(row["cloc_language"]).casefold()))

    qc_rows: list[dict[str, object]] = []
    strict = bool(args.strict_expected_counts)

    def expected_check(check: str, observed: int, expected: int, note: str = "") -> None:
        add_qc(
            qc_rows,
            check,
            observed,
            expected,
            observed == expected if strict else True,
            "error" if strict else "info",
            note,
        )

    expected_check("input_language_rows", len(language_rows), args.expected_language_rows)
    expected_check("unique_cloc_language_types", len(mapping_rows), args.expected_cloc_language_types)
    expected_check("paper_observed_language_types", len(paper_set), args.expected_paper_language_types)
    expected_check("mapped_cloc_language_types", mapped_label_count, args.expected_mapped_cloc_language_types)
    expected_check("unmapped_cloc_language_types", unmapped_label_count, args.expected_unmapped_cloc_language_types)
    expected_check("snapshot_rows", len(snapshot_rows), args.expected_snapshots)
    expected_check("repo_month_rows", len(repo_month_rows), args.expected_repo_month_rows)
    expected_check("zero_ncloc_snapshots", zero_ncloc_snapshots, args.expected_zero_ncloc_snapshots)
    expected_check(
        "all_recognized_snapshot_code",
        all_recognized_snapshot_code,
        args.expected_all_recognized_snapshot_code,
    )
    expected_check(
        "paper_taxonomy_snapshot_code",
        paper_taxonomy_snapshot_code,
        args.expected_paper_taxonomy_snapshot_code,
    )
    expected_check(
        "all_recognized_repo_month_code",
        all_recognized_repo_month_code,
        args.expected_all_recognized_repo_month_code,
    )
    expected_check(
        "paper_taxonomy_repo_month_code",
        paper_taxonomy_repo_month_code,
        args.expected_paper_taxonomy_repo_month_code,
    )

    add_qc(qc_rows, "invalid_manual_alias_targets", len(invalid_alias_targets), 0, not invalid_alias_targets)
    add_qc(qc_rows, "duplicate_snapshot_keys", len(duplicate_snapshot_keys), 0, not duplicate_snapshot_keys)
    add_qc(
        qc_rows,
        "snapshot_taxonomy_reconciliation_failures",
        snapshot_reconciliation_failures,
        0,
        snapshot_reconciliation_failures == 0,
    )
    add_qc(
        qc_rows,
        "repo_month_missing_snapshot_keys",
        repo_month_missing_snapshot_keys,
        0,
        repo_month_missing_snapshot_keys == 0,
    )
    add_qc(
        qc_rows,
        "repo_month_all_recognized_reconciliation_failures",
        repo_month_reconciliation_failures,
        0,
        repo_month_reconciliation_failures == 0,
    )
    add_qc(
        qc_rows,
        "language_code_equals_snapshot_all_recognized_code",
        all_language_code,
        all_recognized_snapshot_code,
        all_language_code == all_recognized_snapshot_code,
    )
    add_qc(
        qc_rows,
        "mapped_language_code_equals_snapshot_taxonomy_code",
        mapped_language_code,
        paper_taxonomy_snapshot_code,
        mapped_language_code == paper_taxonomy_snapshot_code,
    )
    add_qc(
        qc_rows,
        "mapped_plus_unmapped_language_code",
        mapped_language_code + unmapped_language_code,
        all_language_code,
        mapped_language_code + unmapped_language_code == all_language_code,
    )
    add_qc(
        qc_rows,
        "mapped_language_rows_preserved",
        len(mapped_language_rows),
        len(language_rows),
        len(mapped_language_rows) == len(language_rows),
    )
    add_qc(
        qc_rows,
        "snapshot_output_rows_preserved",
        len(snapshot_output_rows),
        len(snapshot_rows),
        len(snapshot_output_rows) == len(snapshot_rows),
    )
    add_qc(
        qc_rows,
        "repo_month_output_rows_preserved",
        len(repo_month_output_rows),
        len(repo_month_rows),
        len(repo_month_output_rows) == len(repo_month_rows),
    )

    hard_failures = sum(
        row["status"] == "fail" and row["severity"] == "error" for row in qc_rows
    )

    mapping_status_counts = Counter(str(row["mapping_status"]) for row in mapping_rows)
    summary_rows = [
        {"metric": "implementation_version", "value": IMPLEMENTATION_VERSION},
        {"metric": "paper_taxonomy_version", "value": TAXONOMY_VERSION},
        {"metric": "paper_observed_language_types", "value": len(paper_set)},
        {"metric": "cloc_language_types", "value": len(mapping_rows)},
        {"metric": "exact_mapping_types", "value": mapping_status_counts["exact"]},
        {"metric": "case_normalized_mapping_types", "value": mapping_status_counts["case_normalized"]},
        {"metric": "manual_alias_mapping_types", "value": mapping_status_counts["manual_alias"]},
        {"metric": "mapped_cloc_language_types", "value": mapped_label_count},
        {"metric": "unmapped_cloc_language_types", "value": unmapped_label_count},
        {"metric": "language_rows", "value": len(language_rows)},
        {"metric": "snapshot_rows", "value": len(snapshot_rows)},
        {"metric": "repo_month_rows", "value": len(repo_month_rows)},
        {"metric": "all_recognized_snapshot_code", "value": all_recognized_snapshot_code},
        {"metric": "paper_taxonomy_snapshot_code", "value": paper_taxonomy_snapshot_code},
        {"metric": "excluded_snapshot_code", "value": unmapped_language_code},
        {
            "metric": "paper_taxonomy_share_of_snapshot_code",
            "value": paper_taxonomy_snapshot_code / all_recognized_snapshot_code
            if all_recognized_snapshot_code
            else "",
        },
        {"metric": "all_recognized_repo_month_code", "value": all_recognized_repo_month_code},
        {"metric": "paper_taxonomy_repo_month_code", "value": paper_taxonomy_repo_month_code},
        {
            "metric": "paper_taxonomy_share_of_repo_month_code",
            "value": paper_taxonomy_repo_month_code / all_recognized_repo_month_code
            if all_recognized_repo_month_code
            else "",
        },
        {"metric": "zero_ncloc_snapshots", "value": zero_ncloc_snapshots},
        {"metric": "hard_qc_failures", "value": hard_failures},
        {
            "metric": "taxonomy_definition",
            "value": "unique labels observed in data_baseline_backup/repos.csv:repo_languages",
        },
        {
            "metric": "numeric_repo_language_values_used_as_ncloc",
            "value": False,
        },
        {
            "metric": "mapping_policy",
            "value": "exact, case-normalized, explicit alias; otherwise unmapped",
        },
    ]

    mapping_fields = [
        "cloc_language",
        "paper_language_types",
        "mapping_status",
        "mapping_rule",
        "mapping_rationale",
        "included_in_paper_taxonomy_ncloc",
        "language_rows",
        "snapshot_count",
        "repository_count",
        "files",
        "code",
        "paper_taxonomy_version",
        "mapping_implementation_version",
    ]
    language_extra_fields = [
        "paper_language_types",
        "paper_taxonomy_mapping_status",
        "paper_taxonomy_mapping_rule",
        "included_in_paper_taxonomy_ncloc",
        "paper_taxonomy_version",
        "taxonomy_mapping_implementation_version",
    ]
    aggregate_extra_fields = [
        "ncloc_local_cloc_all_recognized",
        "ncloc_local_cloc_paper_taxonomy",
        "ncloc_local_cloc_not_in_paper_taxonomy",
        "paper_taxonomy_code_share",
        "mapped_cloc_language_count",
        "unmapped_cloc_language_count",
        "mapped_cloc_file_count",
        "unmapped_cloc_file_count",
        "taxonomy_code_reconciles_all_recognized",
        "paper_taxonomy_version",
        "taxonomy_mapping_implementation_version",
        "paper_taxonomy_count_backend",
        "paper_taxonomy_metric_definition",
    ]
    excluded_fields = mapping_fields + [
        "share_of_all_recognized_code",
        "share_of_excluded_code",
    ]

    write_csv(args.mapping_output, mapping_fields, mapping_rows)
    write_csv(
        args.mapped_language_results_output,
        language_fields + language_extra_fields,
        mapped_language_rows,
    )
    write_csv(
        args.snapshot_aggregates_output,
        snapshot_fields + aggregate_extra_fields,
        snapshot_output_rows,
    )
    write_csv(
        args.repo_month_aggregates_output,
        repo_month_fields + aggregate_extra_fields,
        repo_month_output_rows,
    )
    write_csv(args.excluded_language_summary_output, excluded_fields, excluded_rows)
    write_csv(args.qc_output, ["check", "observed", "expected", "severity", "status", "note"], qc_rows)
    write_csv(args.summary_output, ["metric", "value"], summary_rows)

    logging.info(
        "Completed run-x-c04b-%s: paper_types=%d; cloc_types=%d; mapped=%d; "
        "unmapped=%d; language_rows=%d; snapshots=%d; repo_months=%d; "
        "snapshot_code_all=%d; snapshot_code_taxonomy=%d; hard_qc_failures=%d",
        IMPLEMENTATION_VERSION,
        len(paper_set),
        len(mapping_rows),
        mapped_label_count,
        unmapped_label_count,
        len(language_rows),
        len(snapshot_rows),
        len(repo_month_rows),
        all_recognized_snapshot_code,
        paper_taxonomy_snapshot_code,
        hard_failures,
    )

    if excluded_rows:
        logging.info(
            "Largest excluded cloc labels by code: %s",
            "; ".join(
                f"{row['cloc_language']}={row['code']}" for row in excluded_rows[:8]
            ),
        )

    return 2 if hard_failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - command-line safety boundary
        logging.exception("run-x-c04b failed: %s", exc)
        raise SystemExit(1)
