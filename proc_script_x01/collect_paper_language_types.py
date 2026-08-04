#!/usr/bin/env python3
"""Collect the language taxonomy recorded in the paper replication repos.csv.

The script treats ``repo_languages`` as a source of language labels only. The
numeric values following each label are GitHub-reported byte counts and are
validated syntactically but are not used as NCLOC or as an analysis outcome.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

IMPLEMENTATION_VERSION = "v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect unique language labels from replication-package repos.csv."
    )
    parser.add_argument("--repos-file", required=True, type=Path)
    parser.add_argument("--language-types-output", required=True, type=Path)
    parser.add_argument("--primary-language-types-output", required=True, type=Path)
    parser.add_argument("--membership-output", required=True, type=Path)
    parser.add_argument("--qc-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument("--strict", type=int, choices=(0, 1), default=1)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def normalize_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def parse_repo_languages(value: str) -> tuple[list[str], list[str]]:
    """Return language labels and malformed entries from one repo_languages cell.

    Entries are separated by semicolons. Each valid entry is split from the
    right at the final colon so labels containing spaces, plus signs, hashes,
    or punctuation remain unchanged.
    """

    labels: list[str] = []
    malformed: list[str] = []
    for raw_entry in value.split(";"):
        entry = raw_entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            malformed.append(entry)
            continue
        label, numeric_value = entry.rsplit(":", 1)
        label = label.strip()
        numeric_value = numeric_value.strip()
        if not label:
            malformed.append(entry)
            continue
        try:
            parsed_value = int(numeric_value)
        except ValueError:
            malformed.append(entry)
            continue
        if parsed_value < 0:
            malformed.append(entry)
            continue
        labels.append(label)
    return labels, malformed


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not args.repos_file.is_file():
        raise FileNotFoundError(f"repos.csv not found: {args.repos_file}")

    with args.repos_file.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required_columns = {"repo_name", "repo_languages", "repo_primary_language"}
        missing_columns = sorted(required_columns - set(reader.fieldnames or []))
        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")
        input_rows = list(reader)

    repo_name_counts = Counter(normalize_text(row.get("repo_name")) for row in input_rows)
    duplicate_repo_names = sorted(
        repo_name for repo_name, count in repo_name_counts.items() if repo_name and count > 1
    )

    language_repo_sets: dict[str, set[str]] = defaultdict(set)
    primary_repo_sets: dict[str, set[str]] = defaultdict(set)
    membership_rows: list[dict[str, object]] = []
    malformed_rows: list[dict[str, object]] = []
    repositories_with_languages = 0
    repositories_without_languages = 0
    repositories_without_primary = 0
    primary_not_in_language_list: list[str] = []

    for row_index, row in enumerate(input_rows, start=2):
        repo_name = normalize_text(row.get("repo_name"))
        repo_languages = normalize_text(row.get("repo_languages"))
        primary_language = normalize_text(row.get("repo_primary_language"))

        labels, malformed_entries = parse_repo_languages(repo_languages)
        unique_labels = list(dict.fromkeys(labels))

        if unique_labels:
            repositories_with_languages += 1
        else:
            repositories_without_languages += 1

        if primary_language:
            primary_repo_sets[primary_language].add(repo_name)
        else:
            repositories_without_primary += 1

        if primary_language and primary_language not in unique_labels:
            primary_not_in_language_list.append(repo_name)

        for language_type in unique_labels:
            language_repo_sets[language_type].add(repo_name)
            membership_rows.append(
                {
                    "repo_name": repo_name,
                    "language_type": language_type,
                    "is_primary_language": language_type == primary_language,
                    "taxonomy_source": "repos.csv:repo_languages",
                }
            )

        for malformed_entry in malformed_entries:
            malformed_rows.append(
                {
                    "csv_row_number": row_index,
                    "repo_name": repo_name,
                    "malformed_entry": malformed_entry,
                }
            )

    language_type_rows: list[dict[str, object]] = []
    for language_type in sorted(language_repo_sets, key=str.casefold):
        repos = sorted(language_repo_sets[language_type], key=str.casefold)
        primary_repos = sorted(primary_repo_sets.get(language_type, set()), key=str.casefold)
        language_type_rows.append(
            {
                "language_type": language_type,
                "repositories_reporting_language": len(repos),
                "repositories_where_primary": len(primary_repos),
                "appears_as_primary_language": bool(primary_repos),
                "example_repositories": "; ".join(repos[:5]),
                "taxonomy_source": "repos.csv:repo_languages",
                "numeric_values_used_as_ncloc": False,
            }
        )

    primary_type_rows = [
        {
            "primary_language_type": language_type,
            "repository_count": len(repos),
            "also_present_in_repo_languages_taxonomy": language_type in language_repo_sets,
            "taxonomy_source": "repos.csv:repo_primary_language",
        }
        for language_type, repos in sorted(primary_repo_sets.items(), key=lambda item: item[0].casefold())
    ]

    membership_rows.sort(key=lambda row: (str(row["repo_name"]).casefold(), str(row["language_type"]).casefold()))

    exact_label_checks = {
        label: len(language_repo_sets.get(label, set()))
        for label in ("HTML", "MDX", "Markdown")
    }

    qc_rows = [
        {"check": "input_repository_rows", "observed": len(input_rows), "severity": "info", "status": "pass"},
        {"check": "unique_repository_names", "observed": len(repo_name_counts), "severity": "info", "status": "pass"},
        {"check": "duplicate_repository_names", "observed": len(duplicate_repo_names), "severity": "error" if args.strict else "warning", "status": "pass" if not duplicate_repo_names else "fail"},
        {"check": "repositories_with_repo_languages", "observed": repositories_with_languages, "severity": "info", "status": "pass"},
        {"check": "repositories_without_repo_languages", "observed": repositories_without_languages, "severity": "info", "status": "pass"},
        {"check": "repositories_without_primary_language", "observed": repositories_without_primary, "severity": "info", "status": "pass"},
        {"check": "unique_repo_language_types", "observed": len(language_repo_sets), "severity": "info", "status": "pass"},
        {"check": "unique_primary_language_types", "observed": len(primary_repo_sets), "severity": "info", "status": "pass"},
        {"check": "malformed_repo_language_entries", "observed": len(malformed_rows), "severity": "error" if args.strict else "warning", "status": "pass" if not malformed_rows else "fail"},
        {"check": "primary_language_not_in_repo_languages", "observed": len(primary_not_in_language_list), "severity": "error" if args.strict else "warning", "status": "pass" if not primary_not_in_language_list else "fail"},
        {"check": "exact_label_HTML_repository_count", "observed": exact_label_checks["HTML"], "severity": "info", "status": "pass"},
        {"check": "exact_label_MDX_repository_count", "observed": exact_label_checks["MDX"], "severity": "info", "status": "pass"},
        {"check": "exact_label_Markdown_repository_count", "observed": exact_label_checks["Markdown"], "severity": "info", "status": "pass"},
    ]

    hard_failures = sum(
        row["status"] == "fail" and row["severity"] == "error" for row in qc_rows
    )

    summary_rows = [
        {"metric": "implementation_version", "value": IMPLEMENTATION_VERSION},
        {"metric": "input_repository_rows", "value": len(input_rows)},
        {"metric": "unique_repo_language_types", "value": len(language_repo_sets)},
        {"metric": "unique_primary_language_types", "value": len(primary_repo_sets)},
        {"metric": "HTML_repositories", "value": exact_label_checks["HTML"]},
        {"metric": "MDX_repositories", "value": exact_label_checks["MDX"]},
        {"metric": "Markdown_repositories", "value": exact_label_checks["Markdown"]},
        {"metric": "hard_qc_failures", "value": hard_failures},
        {"metric": "taxonomy_definition", "value": "unique labels in repos.csv:repo_languages"},
        {"metric": "numeric_values_used_as_ncloc", "value": False},
    ]

    write_csv(
        args.language_types_output,
        [
            "language_type",
            "repositories_reporting_language",
            "repositories_where_primary",
            "appears_as_primary_language",
            "example_repositories",
            "taxonomy_source",
            "numeric_values_used_as_ncloc",
        ],
        language_type_rows,
    )
    write_csv(
        args.primary_language_types_output,
        [
            "primary_language_type",
            "repository_count",
            "also_present_in_repo_languages_taxonomy",
            "taxonomy_source",
        ],
        primary_type_rows,
    )
    write_csv(
        args.membership_output,
        ["repo_name", "language_type", "is_primary_language", "taxonomy_source"],
        membership_rows,
    )
    write_csv(args.qc_output, ["check", "observed", "severity", "status"], qc_rows)
    write_csv(args.summary_output, ["metric", "value"], summary_rows)

    logging.info(
        "Completed run-x-c04a-%s: repos=%d; language_types=%d; primary_types=%d; "
        "HTML=%d; MDX=%d; Markdown=%d; hard_qc_failures=%d",
        IMPLEMENTATION_VERSION,
        len(input_rows),
        len(language_repo_sets),
        len(primary_repo_sets),
        exact_label_checks["HTML"],
        exact_label_checks["MDX"],
        exact_label_checks["Markdown"],
        hard_failures,
    )

    if malformed_rows:
        logging.error("Malformed repo_languages examples: %s", malformed_rows[:5])
    if primary_not_in_language_list:
        logging.error(
            "Primary language missing from repo_languages examples: %s",
            primary_not_in_language_list[:5],
        )

    return 2 if hard_failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - top-level reporting
        logging.exception("run-x-c04a-v1 failed: %s", exc)
        raise
