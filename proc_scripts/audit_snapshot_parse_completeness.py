#!/usr/bin/env python3
"""Audit Python snapshot parse failures before defining a method taxonomy.

This script is outcome-blind. It reads only run-py-9a raw scan outputs and
does not read run-py-7/run-py-8 panels, AGC/HWC labels, or DiD estimates.

The path classifier is deliberately conservative. Only paths with explicit
template, vendor, test/example, or archive/documentation evidence are marked
as clear ancillary code. Every unmatched failed path remains a
``source_candidate`` and is exported for manual review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Mapping, Sequence


SCRIPT_VERSION = "run-py-9b-parse-completeness-audit-v1"

CATEGORIES = (
    "template_or_generated",
    "vendor_or_third_party",
    "test_or_example",
    "archive_or_documentation",
    "source_candidate",
)

CLEAR_ANCILLARY_CATEGORIES = frozenset(
    {
        "template_or_generated",
        "vendor_or_third_party",
        "test_or_example",
        "archive_or_documentation",
    }
)

TEMPLATE_SEGMENTS = frozenset(
    {
        "template",
        "templates",
        "scaffold",
        "scaffolds",
        "scaffolding",
        "generated",
        "_generated",
    }
)
VENDOR_SEGMENTS = frozenset(
    {
        "vendor",
        "vendors",
        "third_party",
        "third-party",
        "thirdparty",
        "external",
        "externals",
        "bower_components",
        "node_modules",
        "site-packages",
    }
)
TEST_EXAMPLE_SEGMENTS = frozenset(
    {
        "test",
        "tests",
        "testing",
        "pytest",
        "fixture",
        "fixtures",
        "example",
        "examples",
        "sample",
        "samples",
        "demo",
        "demos",
        "benchmark",
        "benchmarks",
        "notebook",
        "notebooks",
        "exercise",
        "exercises",
        "tutorial",
        "tutorials",
    }
)
ARCHIVE_DOC_SEGMENTS = frozenset(
    {
        ".archive",
        "archive",
        "archives",
        "archived",
        "doc",
        "docs",
        "documentation",
        "backup",
        "backups",
        "reference",
        "references",
    }
)

RULE_ROWS = (
    {
        "priority": 1,
        "rule_id": "placeholder_or_cookiecutter",
        "category": "template_or_generated",
        "clear_ancillary": 1,
        "description": (
            "Path contains template placeholders or a cookiecutter-prefixed "
            "segment."
        ),
    },
    {
        "priority": 2,
        "rule_id": "template_or_generated_segment",
        "category": "template_or_generated",
        "clear_ancillary": 1,
        "description": (
            "Path contains an explicit template, scaffold, or generated "
            "directory segment."
        ),
    },
    {
        "priority": 3,
        "rule_id": "vendor_or_third_party_segment",
        "category": "vendor_or_third_party",
        "clear_ancillary": 1,
        "description": (
            "Path contains an explicit vendor, third-party, external, or "
            "dependency directory segment."
        ),
    },
    {
        "priority": 4,
        "rule_id": "test_or_example_segment",
        "category": "test_or_example",
        "clear_ancillary": 1,
        "description": (
            "Path contains an explicit test, fixture, example, benchmark, "
            "notebook, exercise, or tutorial segment."
        ),
    },
    {
        "priority": 5,
        "rule_id": "test_filename",
        "category": "test_or_example",
        "clear_ancillary": 1,
        "description": (
            "Filename uses a standard Python test naming convention."
        ),
    },
    {
        "priority": 6,
        "rule_id": "archive_or_documentation_segment",
        "category": "archive_or_documentation",
        "clear_ancillary": 1,
        "description": (
            "Path contains an explicit archive, documentation, backup, or "
            "reference segment."
        ),
    },
    {
        "priority": 7,
        "rule_id": "backup_filename",
        "category": "archive_or_documentation",
        "clear_ancillary": 1,
        "description": "Filename explicitly indicates a backup copy.",
    },
    {
        "priority": 99,
        "rule_id": "unmatched_source_candidate",
        "category": "source_candidate",
        "clear_ancillary": 0,
        "description": (
            "No clear ancillary-path evidence was found; retain for manual "
            "source review."
        ),
    },
)

MANIFEST_REQUIRED = frozenset(
    {
        "dataset_source",
        "repo_name",
        "month",
        "latest_commit",
        "commit_available",
        "tree_scan_status",
        "tracked_python_paths",
        "eligible_python_files",
        "parsed_python_files",
        "parse_failure_files",
    }
)
FAILURE_REQUIRED = frozenset(
    {
        "dataset_source",
        "repo_name",
        "latest_commit",
        "relative_path",
        "git_blob_sha",
        "stage",
        "error_type",
        "error_message",
    }
)
FILE_REQUIRED = frozenset(
    {
        "dataset_source",
        "repo_name",
        "latest_commit",
        "relative_path",
        "git_blob_sha",
        "scan_eligible",
        "selection_reason",
        "parse_status",
    }
)

FAILURE_CLASSIFICATION_FIELDS = (
    "dataset_source",
    "repo_name",
    "latest_commit",
    "relative_path",
    "git_blob_sha",
    "stage",
    "error_type",
    "error_message",
    "path_category",
    "classification_rule",
    "classification_reason",
    "clear_ancillary_path",
    "manual_review_required",
    "repository_month_occurrences",
    "months_json",
)

SNAPSHOT_FIELDS = (
    "dataset_source",
    "repo_name",
    "month",
    "latest_commit",
    "commit_available",
    "tree_scan_status",
    "tracked_python_paths",
    "eligible_python_files",
    "parsed_python_files",
    "manifest_parse_failure_files",
    "reconstructed_parse_failure_files",
    "parse_success_rate",
    "template_or_generated_eligible_files",
    "template_or_generated_failure_files",
    "vendor_or_third_party_eligible_files",
    "vendor_or_third_party_failure_files",
    "test_or_example_eligible_files",
    "test_or_example_failure_files",
    "archive_or_documentation_eligible_files",
    "archive_or_documentation_failure_files",
    "source_candidate_eligible_files",
    "source_candidate_parsed_files",
    "source_candidate_failure_files",
    "source_candidate_parse_success_rate",
    "clear_ancillary_failure_files",
    "parse_complete_all_eligible",
    "parse_complete_source_candidate",
    "has_only_clear_ancillary_failures",
    "sensitivity_keep_successfully_parsed_portion",
    "strict_repository_keep_all_complete",
    "strict_repository_keep_source_complete",
    "failure_paths_json",
    "source_candidate_failure_paths_json",
)

REPOSITORY_FIELDS = (
    "dataset_source",
    "repo_name",
    "repository_months",
    "unique_repository_commits",
    "months_with_any_parse_failure",
    "months_with_source_candidate_failure",
    "unique_failed_paths",
    "unique_failed_blobs",
    "parse_failure_file_month_occurrences",
    "source_candidate_failure_file_month_occurrences",
    "eligible_python_file_month_occurrences",
    "source_candidate_eligible_file_month_occurrences",
    "source_candidate_parsed_file_month_occurrences",
    "strict_repository_keep_all_complete",
    "strict_repository_keep_source_complete",
)

PATH_SUMMARY_FIELDS = (
    "dataset_source",
    "path_category",
    "repository_commit_file_occurrences",
    "eligible_repository_commit_file_occurrences",
    "parsed_repository_commit_file_occurrences",
    "failed_repository_commit_file_occurrences",
    "repository_month_eligible_file_occurrences",
    "repository_month_parsed_file_occurrences",
    "repository_month_failed_file_occurrences",
    "repositories",
    "repository_commits",
)

FAILURE_SUMMARY_FIELDS = (
    "dataset_source",
    "path_category",
    "failed_repository_commit_file_occurrences",
    "failed_repository_month_file_occurrences",
    "affected_repository_months",
    "repositories",
    "repository_commits",
    "unique_paths",
    "unique_failed_blobs",
    "clear_ancillary_path",
    "manual_review_required",
)

UNIQUE_BLOB_FIELDS = (
    "git_blob_sha",
    "path_categories_json",
    "category_consistent",
    "clear_ancillary_path",
    "manual_review_required",
    "repository_commit_file_occurrences",
    "repository_month_file_occurrences",
    "repositories",
    "repository_commits",
    "dataset_sources_json",
    "repo_names_json",
    "relative_paths_json",
    "error_types_json",
    "example_error_message",
)

MANUAL_REVIEW_FIELDS = (
    "dataset_source",
    "repo_name",
    "relative_path",
    "git_blob_sha",
    "error_type",
    "error_message",
    "repository_commit_occurrences",
    "repository_month_occurrences",
    "commits_json",
    "months_json",
    "review_decision",
    "review_note",
)

QC_FIELDS = (
    "check_name",
    "severity",
    "passed",
    "observed",
    "expected",
    "note",
)


def parse_int(value: Any, label: str) -> int:
    text = str(value).strip()
    if not re.fullmatch(r"-?\d+", text):
        raise ValueError(f"{label} must be an integer; found {value!r}")
    return int(text)


def safe_rate(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return ""
    return f"{numerator / denominator:.12f}"


def json_list(values: Iterable[str]) -> str:
    return json.dumps(sorted({str(value) for value in values}), ensure_ascii=False)


def stable_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_path(path: str) -> tuple[str, tuple[str, ...], str]:
    normalized = str(PurePosixPath(path.replace("\\", "/"))).lower()
    segments = tuple(part for part in normalized.split("/") if part not in {"", "."})
    filename = segments[-1] if segments else ""
    return normalized, segments, filename


def classify_path(path: str) -> dict[str, Any]:
    normalized, segments, filename = normalize_path(path)
    segment_set = set(segments)

    if (
        "{" in normalized
        or "}" in normalized
        or any(segment.startswith("cookiecutter") for segment in segments)
    ):
        rule_id = "placeholder_or_cookiecutter"
    elif segment_set & TEMPLATE_SEGMENTS:
        rule_id = "template_or_generated_segment"
    elif segment_set & VENDOR_SEGMENTS:
        rule_id = "vendor_or_third_party_segment"
    elif segment_set & TEST_EXAMPLE_SEGMENTS:
        rule_id = "test_or_example_segment"
    elif (
        filename == "conftest.py"
        or filename.startswith("test_")
        or filename.endswith("_test.py")
    ):
        rule_id = "test_filename"
    elif segment_set & ARCHIVE_DOC_SEGMENTS:
        rule_id = "archive_or_documentation_segment"
    elif (
        filename.endswith("_backup.py")
        or filename.endswith(".backup.py")
        or "_original_backup." in filename
    ):
        rule_id = "backup_filename"
    else:
        rule_id = "unmatched_source_candidate"

    rule = next(row for row in RULE_ROWS if row["rule_id"] == rule_id)
    return {
        "path_category": rule["category"],
        "classification_rule": rule["rule_id"],
        "classification_reason": rule["description"],
        "clear_ancillary_path": int(rule["clear_ancillary"]),
        "manual_review_required": int(rule["category"] == "source_candidate"),
    }


def csv_rows(path: Path, required: frozenset[str]) -> Iterator[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise ValueError(
                f"CSV is missing required columns {missing}: {path}"
            )
        for line_number, row in enumerate(reader, start=2):
            clean = {key: (value if value is not None else "") for key, value in row.items()}
            clean["_line_number"] = str(line_number)
            yield clean


def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


@dataclass
class FileCommitStats:
    rows: int = 0
    eligible: int = 0
    parsed: int = 0
    failed: int = 0
    category_rows: Counter[str] = field(default_factory=Counter)
    category_eligible: Counter[str] = field(default_factory=Counter)
    category_parsed: Counter[str] = field(default_factory=Counter)
    category_failed: Counter[str] = field(default_factory=Counter)


@dataclass
class RepoStats:
    months: int = 0
    commits: set[str] = field(default_factory=set)
    failure_months: int = 0
    source_failure_months: int = 0
    failed_paths: set[str] = field(default_factory=set)
    failed_blobs: set[str] = field(default_factory=set)
    failure_file_month_occurrences: int = 0
    source_failure_file_month_occurrences: int = 0
    eligible_file_month_occurrences: int = 0
    source_eligible_file_month_occurrences: int = 0
    source_parsed_file_month_occurrences: int = 0


def load_file_inventory(
    path: Path | None,
) -> tuple[
    dict[tuple[str, str, str], FileCommitStats],
    set[tuple[str, str, str, str]],
    dict[tuple[str, str], dict[str, Any]],
    int,
]:
    if path is None:
        return {}, set(), {}, 0

    by_commit: dict[tuple[str, str, str], FileCommitStats] = defaultdict(
        FileCommitStats
    )
    inventory_failure_keys: set[tuple[str, str, str, str]] = set()
    category_summary: dict[tuple[str, str], dict[str, Any]] = {}
    seen_keys: set[tuple[str, str, str, str]] = set()
    duplicate_keys = 0

    def ensure_summary(source: str, category: str) -> dict[str, Any]:
        summary_key = (source, category)
        if summary_key not in category_summary:
            category_summary[summary_key] = {
                "dataset_source": source,
                "path_category": category,
                "repository_commit_file_occurrences": 0,
                "eligible_repository_commit_file_occurrences": 0,
                "parsed_repository_commit_file_occurrences": 0,
                "failed_repository_commit_file_occurrences": 0,
                "repository_month_eligible_file_occurrences": 0,
                "repository_month_parsed_file_occurrences": 0,
                "repository_month_failed_file_occurrences": 0,
                "_repos": set(),
                "_commits": set(),
            }
        return category_summary[summary_key]

    for row in csv_rows(path, FILE_REQUIRED):
        source = row["dataset_source"].strip()
        repo = row["repo_name"].strip()
        commit = row["latest_commit"].strip()
        relative_path = row["relative_path"].strip()
        key = (source, repo, commit)
        file_key = (*key, relative_path)
        if file_key in seen_keys:
            duplicate_keys += 1
        seen_keys.add(file_key)

        classification = classify_path(relative_path)
        category = classification["path_category"]
        scan_eligible = parse_int(
            row["scan_eligible"],
            f"{path}:{row['_line_number']}:scan_eligible",
        )
        parse_status = row["parse_status"].strip().lower()

        stats = by_commit[key]
        stats.rows += 1
        stats.category_rows[category] += 1
        if scan_eligible == 1:
            stats.eligible += 1
            stats.category_eligible[category] += 1
            if parse_status == "success":
                stats.parsed += 1
                stats.category_parsed[category] += 1
            elif parse_status == "failure":
                stats.failed += 1
                stats.category_failed[category] += 1
                inventory_failure_keys.add(file_key)

        summary = ensure_summary(source, category)
        summary["repository_commit_file_occurrences"] += 1
        summary["_repos"].add(repo)
        summary["_commits"].add((repo, commit))
        if scan_eligible == 1:
            summary["eligible_repository_commit_file_occurrences"] += 1
            if parse_status == "success":
                summary["parsed_repository_commit_file_occurrences"] += 1
            elif parse_status == "failure":
                summary["failed_repository_commit_file_occurrences"] += 1

    for source in {key[0] for key in by_commit}:
        for category in CATEGORIES:
            ensure_summary(source, category)

    if duplicate_keys:
        raise ValueError(
            "Python file inventory has duplicate "
            f"dataset/repository/commit/path keys: {duplicate_keys}"
        )
    return by_commit, inventory_failure_keys, category_summary, len(seen_keys)


def load_failures(
    path: Path,
) -> tuple[
    list[dict[str, Any]],
    dict[tuple[str, str, str], list[dict[str, Any]]],
    set[tuple[str, str, str, str]],
]:
    rows: list[dict[str, Any]] = []
    by_commit: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    seen_keys: set[tuple[str, str, str, str]] = set()

    for raw in csv_rows(path, FAILURE_REQUIRED):
        row = {key: value for key, value in raw.items() if key != "_line_number"}
        row.update(classify_path(row["relative_path"]))
        key = (
            row["dataset_source"],
            row["repo_name"],
            row["latest_commit"],
        )
        file_key = (*key, row["relative_path"])
        if file_key in seen_keys:
            raise ValueError(
                "Parse-failure CSV has duplicate "
                f"dataset/repository/commit/path key: {file_key}"
            )
        seen_keys.add(file_key)
        rows.append(row)
        by_commit[key].append(row)
    return rows, by_commit, seen_keys


def add_qc(
    qc_rows: list[dict[str, Any]],
    check_name: str,
    severity: str,
    passed: bool,
    observed: Any,
    expected: Any,
    note: str,
) -> None:
    qc_rows.append(
        {
            "check_name": check_name,
            "severity": severity,
            "passed": str(bool(passed)),
            "observed": observed,
            "expected": expected,
            "note": note,
        }
    )


def run_audit(
    manifest_path: Path,
    failures_path: Path,
    file_inventory_path: Path | None,
    output_dir: Path,
    overwrite_output: bool,
) -> dict[str, Any]:
    output_names = {
        "classification": "run-py-9b-parse-failure-classification.csv",
        "unique_blobs": "run-py-9b-unique-failed-blobs.csv",
        "snapshot": "run-py-9b-snapshot-completeness.csv",
        "repository": "run-py-9b-repository-completeness.csv",
        "path_summary": "run-py-9b-path-category-summary.csv",
        "failure_summary": "run-py-9b-failure-category-summary.csv",
        "manual_review": "run-py-9b-source-candidate-manual-review.csv",
        "rules": "run-py-9b-path-classification-rules.csv",
        "qc": "run-py-9b-audit-qc.csv",
        "metadata": "run-py-9b-audit-metadata.json",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = [
        output_dir / name
        for name in output_names.values()
        if (output_dir / name).exists()
    ]
    if existing and not overwrite_output:
        raise FileExistsError(
            "Output files already exist. Use --overwrite-output to replace them: "
            + ", ".join(str(path) for path in existing)
        )

    file_by_commit, inventory_failure_keys, path_summary, inventory_rows = (
        load_file_inventory(file_inventory_path)
    )
    full_inventory_mode = file_inventory_path is not None
    failure_rows, failures_by_commit, failure_keys = load_failures(failures_path)

    manifest_rows: list[dict[str, str]] = []
    manifest_keys: set[tuple[str, str, str]] = set()
    commit_months: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    manifest_duplicate_keys = 0
    for raw in csv_rows(manifest_path, MANIFEST_REQUIRED):
        row = {key: value for key, value in raw.items() if key != "_line_number"}
        month_key = (row["dataset_source"], row["repo_name"], row["month"])
        if month_key in manifest_keys:
            manifest_duplicate_keys += 1
        manifest_keys.add(month_key)
        commit_key = (
            row["dataset_source"],
            row["repo_name"],
            row["latest_commit"],
        )
        commit_months[commit_key].add(row["month"])
        manifest_rows.append(row)

    if manifest_duplicate_keys:
        raise ValueError(
            "Manifest has duplicate dataset/repository/month keys: "
            f"{manifest_duplicate_keys}"
        )

    for row in failure_rows:
        key = (
            row["dataset_source"],
            row["repo_name"],
            row["latest_commit"],
        )
        months = commit_months.get(key, set())
        row["repository_month_occurrences"] = len(months)
        row["months_json"] = json_list(months)

    qc_rows: list[dict[str, Any]] = []
    manifest_commit_keys = set(commit_months)
    failure_commit_keys = set(failures_by_commit)
    add_qc(
        qc_rows,
        "manifest_repository_month_keys_unique",
        "critical",
        manifest_duplicate_keys == 0,
        manifest_duplicate_keys,
        0,
        "Every dataset/repository/month key must be unique.",
    )
    add_qc(
        qc_rows,
        "all_failure_commits_in_manifest",
        "critical",
        failure_commit_keys <= manifest_commit_keys,
        len(failure_commit_keys - manifest_commit_keys),
        0,
        "Every parse failure must map to at least one repository month.",
    )
    if full_inventory_mode:
        add_qc(
            qc_rows,
            "all_manifest_commits_in_file_inventory",
            "critical",
            manifest_commit_keys <= set(file_by_commit),
            len(manifest_commit_keys - set(file_by_commit)),
            0,
            "Every manifest repository commit must have file-inventory rows.",
        )
        add_qc(
            qc_rows,
            "failure_csv_matches_file_inventory_failures",
            "critical",
            failure_keys == inventory_failure_keys,
            len(failure_keys.symmetric_difference(inventory_failure_keys)),
            0,
            "Failure keys must agree across the two run-py-9a inventories.",
        )
    else:
        add_qc(
            qc_rows,
            "python_file_inventory_available",
            "warning",
            False,
            0,
            1,
            "Compact mode cannot produce category denominators for all files.",
        )

    repo_stats: dict[tuple[str, str], RepoStats] = defaultdict(RepoStats)
    snapshot_rows: list[dict[str, Any]] = []
    manifest_failure_mismatches = 0
    manifest_file_mismatches = 0

    for row in manifest_rows:
        source = row["dataset_source"]
        repo = row["repo_name"]
        month = row["month"]
        commit = row["latest_commit"]
        commit_key = (source, repo, commit)
        failures = failures_by_commit.get(commit_key, [])
        failure_category_counts = Counter(
            item["path_category"] for item in failures
        )
        reconstructed_failures = len(failures)
        manifest_failures = parse_int(
            row["parse_failure_files"],
            f"{manifest_path}:parse_failure_files",
        )
        eligible = parse_int(
            row["eligible_python_files"],
            f"{manifest_path}:eligible_python_files",
        )
        parsed = parse_int(
            row["parsed_python_files"],
            f"{manifest_path}:parsed_python_files",
        )
        if manifest_failures != reconstructed_failures:
            manifest_failure_mismatches += 1

        file_stats = file_by_commit.get(commit_key)
        if full_inventory_mode:
            if file_stats is None:
                file_stats = FileCommitStats()
            if (
                file_stats.eligible != eligible
                or file_stats.parsed != parsed
                or file_stats.failed != manifest_failures
            ):
                manifest_file_mismatches += 1
        else:
            file_stats = FileCommitStats()
            file_stats.eligible = eligible
            file_stats.parsed = parsed
            file_stats.failed = manifest_failures
            file_stats.category_failed.update(failure_category_counts)

        source_failures = failure_category_counts["source_candidate"]
        clear_failures = reconstructed_failures - source_failures
        failure_paths = [item["relative_path"] for item in failures]
        source_failure_paths = [
            item["relative_path"]
            for item in failures
            if item["path_category"] == "source_candidate"
        ]

        output: dict[str, Any] = {
            "dataset_source": source,
            "repo_name": repo,
            "month": month,
            "latest_commit": commit,
            "commit_available": row["commit_available"],
            "tree_scan_status": row["tree_scan_status"],
            "tracked_python_paths": row["tracked_python_paths"],
            "eligible_python_files": eligible,
            "parsed_python_files": parsed,
            "manifest_parse_failure_files": manifest_failures,
            "reconstructed_parse_failure_files": reconstructed_failures,
            "parse_success_rate": safe_rate(parsed, eligible),
            "clear_ancillary_failure_files": clear_failures,
            "parse_complete_all_eligible": int(reconstructed_failures == 0),
            "parse_complete_source_candidate": int(source_failures == 0),
            "has_only_clear_ancillary_failures": int(
                reconstructed_failures > 0 and source_failures == 0
            ),
            "sensitivity_keep_successfully_parsed_portion": int(
                row["commit_available"].strip() == "1"
                and row["tree_scan_status"].strip().lower() == "success"
            ),
            "failure_paths_json": json_list(failure_paths),
            "source_candidate_failure_paths_json": json_list(
                source_failure_paths
            ),
        }
        for category in CATEGORIES:
            output[f"{category}_eligible_files"] = (
                file_stats.category_eligible[category]
                if full_inventory_mode
                else ""
            )
            output[f"{category}_failure_files"] = failure_category_counts[
                category
            ]
        output["source_candidate_parsed_files"] = (
            file_stats.category_parsed["source_candidate"]
            if full_inventory_mode
            else ""
        )
        output["source_candidate_parse_success_rate"] = (
            safe_rate(
                file_stats.category_parsed["source_candidate"],
                file_stats.category_eligible["source_candidate"],
            )
            if full_inventory_mode
            else ""
        )
        snapshot_rows.append(output)

        stats = repo_stats[(source, repo)]
        stats.months += 1
        stats.commits.add(commit)
        stats.failure_months += int(reconstructed_failures > 0)
        stats.source_failure_months += int(source_failures > 0)
        stats.failed_paths.update(failure_paths)
        stats.failed_blobs.update(item["git_blob_sha"] for item in failures)
        stats.failure_file_month_occurrences += reconstructed_failures
        stats.source_failure_file_month_occurrences += source_failures
        stats.eligible_file_month_occurrences += eligible
        if full_inventory_mode:
            stats.source_eligible_file_month_occurrences += (
                file_stats.category_eligible["source_candidate"]
            )
            stats.source_parsed_file_month_occurrences += (
                file_stats.category_parsed["source_candidate"]
            )

        if full_inventory_mode:
            for category in CATEGORIES:
                summary = path_summary[(source, category)]
                summary["repository_month_eligible_file_occurrences"] += (
                    file_stats.category_eligible[category]
                )
                summary["repository_month_parsed_file_occurrences"] += (
                    file_stats.category_parsed[category]
                )
                summary["repository_month_failed_file_occurrences"] += (
                    file_stats.category_failed[category]
                )

    for snapshot in snapshot_rows:
        stats = repo_stats[(snapshot["dataset_source"], snapshot["repo_name"])]
        snapshot["strict_repository_keep_all_complete"] = int(
            stats.failure_months == 0
        )
        snapshot["strict_repository_keep_source_complete"] = int(
            stats.source_failure_months == 0
        )

    add_qc(
        qc_rows,
        "manifest_failure_counts_match_reconstructed_failures",
        "critical",
        manifest_failure_mismatches == 0,
        manifest_failure_mismatches,
        0,
        "Manifest failure counts must match the failure CSV after commit join.",
    )
    if full_inventory_mode:
        add_qc(
            qc_rows,
            "manifest_file_counts_match_file_inventory",
            "critical",
            manifest_file_mismatches == 0,
            manifest_file_mismatches,
            0,
            "Eligible, parsed, and failed file counts must agree per snapshot.",
        )

    repository_rows: list[dict[str, Any]] = []
    for (source, repo), stats in sorted(repo_stats.items()):
        repository_rows.append(
            {
                "dataset_source": source,
                "repo_name": repo,
                "repository_months": stats.months,
                "unique_repository_commits": len(stats.commits),
                "months_with_any_parse_failure": stats.failure_months,
                "months_with_source_candidate_failure": (
                    stats.source_failure_months
                ),
                "unique_failed_paths": len(stats.failed_paths),
                "unique_failed_blobs": len(stats.failed_blobs),
                "parse_failure_file_month_occurrences": (
                    stats.failure_file_month_occurrences
                ),
                "source_candidate_failure_file_month_occurrences": (
                    stats.source_failure_file_month_occurrences
                ),
                "eligible_python_file_month_occurrences": (
                    stats.eligible_file_month_occurrences
                ),
                "source_candidate_eligible_file_month_occurrences": (
                    stats.source_eligible_file_month_occurrences
                    if full_inventory_mode
                    else ""
                ),
                "source_candidate_parsed_file_month_occurrences": (
                    stats.source_parsed_file_month_occurrences
                    if full_inventory_mode
                    else ""
                ),
                "strict_repository_keep_all_complete": int(
                    stats.failure_months == 0
                ),
                "strict_repository_keep_source_complete": int(
                    stats.source_failure_months == 0
                ),
            }
        )

    path_summary_rows: list[dict[str, Any]] = []
    if full_inventory_mode:
        for summary in path_summary.values():
            output = dict(summary)
            output["repositories"] = len(output.pop("_repos"))
            output["repository_commits"] = len(output.pop("_commits"))
            path_summary_rows.append(output)
        path_summary_rows.sort(
            key=lambda row: (row["dataset_source"], row["path_category"])
        )

    failure_summary_groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in failure_rows:
        source = row["dataset_source"]
        category = row["path_category"]
        key = (source, category)
        if key not in failure_summary_groups:
            failure_summary_groups[key] = {
                "dataset_source": source,
                "path_category": category,
                "failed_repository_commit_file_occurrences": 0,
                "failed_repository_month_file_occurrences": 0,
                "_months": set(),
                "_repos": set(),
                "_commits": set(),
                "_paths": set(),
                "_blobs": set(),
                "clear_ancillary_path": int(
                    category in CLEAR_ANCILLARY_CATEGORIES
                ),
                "manual_review_required": int(category == "source_candidate"),
            }
        group = failure_summary_groups[key]
        group["failed_repository_commit_file_occurrences"] += 1
        months = commit_months[
            (source, row["repo_name"], row["latest_commit"])
        ]
        group["failed_repository_month_file_occurrences"] += len(months)
        group["_months"].update((row["repo_name"], month) for month in months)
        group["_repos"].add(row["repo_name"])
        group["_commits"].add((row["repo_name"], row["latest_commit"]))
        group["_paths"].add((row["repo_name"], row["relative_path"]))
        group["_blobs"].add(row["git_blob_sha"])

    failure_summary_rows: list[dict[str, Any]] = []
    for group in failure_summary_groups.values():
        output = dict(group)
        output["affected_repository_months"] = len(output.pop("_months"))
        output["repositories"] = len(output.pop("_repos"))
        output["repository_commits"] = len(output.pop("_commits"))
        output["unique_paths"] = len(output.pop("_paths"))
        output["unique_failed_blobs"] = len(output.pop("_blobs"))
        failure_summary_rows.append(output)
    failure_summary_rows.sort(
        key=lambda row: (row["dataset_source"], row["path_category"])
    )

    blob_groups: dict[str, dict[str, Any]] = {}
    for row in failure_rows:
        sha = row["git_blob_sha"]
        if sha not in blob_groups:
            blob_groups[sha] = {
                "git_blob_sha": sha,
                "_categories": set(),
                "_repos": set(),
                "_commits": set(),
                "_sources": set(),
                "_paths": set(),
                "_error_types": set(),
                "example_error_message": row["error_message"],
                "repository_commit_file_occurrences": 0,
                "repository_month_file_occurrences": 0,
            }
        group = blob_groups[sha]
        group["_categories"].add(row["path_category"])
        group["_repos"].add(row["repo_name"])
        group["_commits"].add((row["repo_name"], row["latest_commit"]))
        group["_sources"].add(row["dataset_source"])
        group["_paths"].add(row["relative_path"])
        group["_error_types"].add(row["error_type"])
        group["repository_commit_file_occurrences"] += 1
        group["repository_month_file_occurrences"] += len(
            commit_months[
                (
                    row["dataset_source"],
                    row["repo_name"],
                    row["latest_commit"],
                )
            ]
        )

    unique_blob_rows: list[dict[str, Any]] = []
    for group in blob_groups.values():
        categories = group.pop("_categories")
        output = dict(group)
        output["path_categories_json"] = json_list(categories)
        output["category_consistent"] = int(len(categories) == 1)
        output["clear_ancillary_path"] = int(
            bool(categories) and categories <= CLEAR_ANCILLARY_CATEGORIES
        )
        output["manual_review_required"] = int(
            "source_candidate" in categories
        )
        output["repositories"] = len(output.pop("_repos"))
        output["repository_commits"] = len(output.pop("_commits"))
        output["dataset_sources_json"] = json_list(output.pop("_sources"))
        output["repo_names_json"] = json_list(
            row["repo_name"]
            for row in failure_rows
            if row["git_blob_sha"] == output["git_blob_sha"]
        )
        output["relative_paths_json"] = json_list(output.pop("_paths"))
        output["error_types_json"] = json_list(output.pop("_error_types"))
        unique_blob_rows.append(output)
    unique_blob_rows.sort(key=lambda row: row["git_blob_sha"])

    review_groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in failure_rows:
        if row["path_category"] != "source_candidate":
            continue
        key = (
            row["dataset_source"],
            row["repo_name"],
            row["relative_path"],
            row["git_blob_sha"],
        )
        if key not in review_groups:
            review_groups[key] = {
                "dataset_source": row["dataset_source"],
                "repo_name": row["repo_name"],
                "relative_path": row["relative_path"],
                "git_blob_sha": row["git_blob_sha"],
                "error_type": row["error_type"],
                "error_message": row["error_message"],
                "_commits": set(),
                "_months": set(),
                "review_decision": "",
                "review_note": "",
            }
        group = review_groups[key]
        group["_commits"].add(row["latest_commit"])
        group["_months"].update(
            commit_months[
                (
                    row["dataset_source"],
                    row["repo_name"],
                    row["latest_commit"],
                )
            ]
        )

    manual_review_rows: list[dict[str, Any]] = []
    for group in review_groups.values():
        output = dict(group)
        commits = output.pop("_commits")
        months = output.pop("_months")
        output["repository_commit_occurrences"] = len(commits)
        output["repository_month_occurrences"] = len(months)
        output["commits_json"] = json_list(commits)
        output["months_json"] = json_list(months)
        manual_review_rows.append(output)
    manual_review_rows.sort(
        key=lambda row: (
            row["dataset_source"],
            row["repo_name"],
            row["relative_path"],
            row["git_blob_sha"],
        )
    )

    source_failure_occurrences = sum(
        1 for row in failure_rows if row["path_category"] == "source_candidate"
    )
    clear_failure_occurrences = len(failure_rows) - source_failure_occurrences
    add_qc(
        qc_rows,
        "all_failure_paths_classified",
        "critical",
        all(
            row["path_category"] in CATEGORIES
            for row in failure_rows
        ),
        sum(
            row["path_category"] not in CATEGORIES
            for row in failure_rows
        ),
        0,
        "Every failed path must receive exactly one audit category.",
    )
    add_qc(
        qc_rows,
        "source_candidate_failures_exported_for_manual_review",
        "critical",
        len(manual_review_rows) > 0 or source_failure_occurrences == 0,
        len(manual_review_rows),
        ">=1 when source candidates exist",
        "Unmatched failed paths must be retained for manual source review.",
    )

    write_csv(
        output_dir / output_names["classification"],
        FAILURE_CLASSIFICATION_FIELDS,
        failure_rows,
    )
    write_csv(
        output_dir / output_names["unique_blobs"],
        UNIQUE_BLOB_FIELDS,
        unique_blob_rows,
    )
    write_csv(
        output_dir / output_names["snapshot"],
        SNAPSHOT_FIELDS,
        snapshot_rows,
    )
    write_csv(
        output_dir / output_names["repository"],
        REPOSITORY_FIELDS,
        repository_rows,
    )
    write_csv(
        output_dir / output_names["path_summary"],
        PATH_SUMMARY_FIELDS,
        path_summary_rows,
    )
    write_csv(
        output_dir / output_names["failure_summary"],
        FAILURE_SUMMARY_FIELDS,
        failure_summary_rows,
    )
    write_csv(
        output_dir / output_names["manual_review"],
        MANUAL_REVIEW_FIELDS,
        manual_review_rows,
    )
    write_csv(
        output_dir / output_names["rules"],
        ("priority", "rule_id", "category", "clear_ancillary", "description"),
        RULE_ROWS,
    )
    write_csv(
        output_dir / output_names["qc"],
        QC_FIELDS,
        qc_rows,
    )

    critical_failures = [
        row
        for row in qc_rows
        if row["severity"] == "critical" and row["passed"] != "True"
    ]
    metadata = {
        "script_version": SCRIPT_VERSION,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "full_file_inventory" if full_inventory_mode else "compact",
        "inputs": {
            "history_snapshot_manifest": str(manifest_path),
            "history_snapshot_manifest_sha256": stable_sha256(manifest_path),
            "parse_failures": str(failures_path),
            "parse_failures_sha256": stable_sha256(failures_path),
            "python_file_inventory": (
                str(file_inventory_path) if file_inventory_path else None
            ),
            "python_file_inventory_sha256": (
                stable_sha256(file_inventory_path)
                if file_inventory_path
                else None
            ),
            "prior_run_py_7_or_8_outputs": None,
        },
        "counts": {
            "repository_months": len(snapshot_rows),
            "repositories": len(repository_rows),
            "unique_repository_commits": len(manifest_commit_keys),
            "python_file_inventory_rows": inventory_rows,
            "parse_failure_repository_commit_file_occurrences": len(
                failure_rows
            ),
            "parse_failure_repository_month_file_occurrences": sum(
                row["repository_month_occurrences"] for row in failure_rows
            ),
            "unique_failed_blobs": len(unique_blob_rows),
            "clear_ancillary_failure_repository_commit_occurrences": (
                clear_failure_occurrences
            ),
            "source_candidate_failure_repository_commit_occurrences": (
                source_failure_occurrences
            ),
            "source_candidate_manual_review_rows": len(manual_review_rows),
            "months_with_any_parse_failure": sum(
                row["reconstructed_parse_failure_files"] > 0
                for row in snapshot_rows
            ),
            "months_with_source_candidate_failure": sum(
                row["source_candidate_failure_files"] > 0
                for row in snapshot_rows
            ),
            "critical_qc_failures": len(critical_failures),
        },
        "category_policy": {
            "categories": list(CATEGORIES),
            "clear_ancillary_categories": sorted(
                CLEAR_ANCILLARY_CATEGORIES
            ),
            "source_candidate_policy": (
                "Unmatched paths are not assumed to be production source. "
                "They require manual review before final sample filtering."
            ),
        },
        "outputs": {
            key: str(output_dir / name)
            for key, name in output_names.items()
            if key != "metadata"
        },
        "status": "PASS" if not critical_failures else "FAIL",
    }
    with (output_dir / output_names["metadata"]).open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(metadata, handle, indent=2, sort_keys=True)
        handle.write("\n")

    if critical_failures:
        names = ", ".join(row["check_name"] for row in critical_failures)
        raise RuntimeError(f"Critical QC checks failed: {names}")
    return metadata


def run_self_test() -> None:
    classification_cases = {
        "templates/{name}/broken.py": "template_or_generated",
        "vendor/package/legacy.py": "vendor_or_third_party",
        "tests/test_parser.py": "test_or_example",
        "docs/conf.py": "archive_or_documentation",
        "src/package/parser.py": "source_candidate",
    }
    for test_path, expected_category in classification_cases.items():
        observed_category = classify_path(test_path)["path_category"]
        assert observed_category == expected_category, (
            test_path,
            observed_category,
            expected_category,
        )

    with tempfile.TemporaryDirectory(prefix="run-py-9b-self-test-") as temp:
        root = Path(temp)
        manifest = root / "manifest.csv"
        failures = root / "failures.csv"
        inventory = root / "files.csv"
        output = root / "output"

        write_csv(
            manifest,
            (
                "dataset_source",
                "repo_name",
                "month",
                "latest_commit",
                "commit_available",
                "tree_scan_status",
                "tracked_python_paths",
                "eligible_python_files",
                "parsed_python_files",
                "parse_failure_files",
            ),
            (
                {
                    "dataset_source": "control",
                    "repo_name": "example/ancillary",
                    "month": "2024-01",
                    "latest_commit": "c1",
                    "commit_available": 1,
                    "tree_scan_status": "success",
                    "tracked_python_paths": 2,
                    "eligible_python_files": 2,
                    "parsed_python_files": 1,
                    "parse_failure_files": 1,
                },
                {
                    "dataset_source": "control",
                    "repo_name": "example/ancillary",
                    "month": "2024-02",
                    "latest_commit": "c1",
                    "commit_available": 1,
                    "tree_scan_status": "success",
                    "tracked_python_paths": 2,
                    "eligible_python_files": 2,
                    "parsed_python_files": 1,
                    "parse_failure_files": 1,
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "example/source",
                    "month": "2024-01",
                    "latest_commit": "c2",
                    "commit_available": 1,
                    "tree_scan_status": "success",
                    "tracked_python_paths": 2,
                    "eligible_python_files": 2,
                    "parsed_python_files": 1,
                    "parse_failure_files": 1,
                },
            ),
        )
        write_csv(
            failures,
            (
                "dataset_source",
                "repo_name",
                "latest_commit",
                "relative_path",
                "git_blob_sha",
                "stage",
                "error_type",
                "error_message",
            ),
            (
                {
                    "dataset_source": "control",
                    "repo_name": "example/ancillary",
                    "latest_commit": "c1",
                    "relative_path": "templates/{name}/broken.py",
                    "git_blob_sha": "b1",
                    "stage": "python_ast_parse",
                    "error_type": "SyntaxError",
                    "error_message": "template placeholder",
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "example/source",
                    "latest_commit": "c2",
                    "relative_path": "src/broken.py",
                    "git_blob_sha": "b2",
                    "stage": "python_ast_parse",
                    "error_type": "SyntaxError",
                    "error_message": "actual source candidate",
                },
            ),
        )
        write_csv(
            inventory,
            (
                "dataset_source",
                "repo_name",
                "latest_commit",
                "relative_path",
                "git_blob_sha",
                "scan_eligible",
                "selection_reason",
                "parse_status",
            ),
            (
                {
                    "dataset_source": "control",
                    "repo_name": "example/ancillary",
                    "latest_commit": "c1",
                    "relative_path": "templates/{name}/broken.py",
                    "git_blob_sha": "b1",
                    "scan_eligible": 1,
                    "selection_reason": "eligible",
                    "parse_status": "failure",
                },
                {
                    "dataset_source": "control",
                    "repo_name": "example/ancillary",
                    "latest_commit": "c1",
                    "relative_path": "src/main.py",
                    "git_blob_sha": "b3",
                    "scan_eligible": 1,
                    "selection_reason": "eligible",
                    "parse_status": "success",
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "example/source",
                    "latest_commit": "c2",
                    "relative_path": "src/broken.py",
                    "git_blob_sha": "b2",
                    "scan_eligible": 1,
                    "selection_reason": "eligible",
                    "parse_status": "failure",
                },
                {
                    "dataset_source": "treatment",
                    "repo_name": "example/source",
                    "latest_commit": "c2",
                    "relative_path": "tests/test_ok.py",
                    "git_blob_sha": "b4",
                    "scan_eligible": 1,
                    "selection_reason": "eligible",
                    "parse_status": "success",
                },
            ),
        )

        metadata = run_audit(
            manifest,
            failures,
            inventory,
            output,
            overwrite_output=False,
        )
        assert metadata["status"] == "PASS"
        assert metadata["counts"]["repository_months"] == 3
        assert metadata["counts"]["months_with_any_parse_failure"] == 3
        assert metadata["counts"]["months_with_source_candidate_failure"] == 1
        assert (
            metadata["counts"][
                "source_candidate_failure_repository_commit_occurrences"
            ]
            == 1
        )

        with (output / "run-py-9b-snapshot-completeness.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        ancillary = [
            row for row in rows if row["repo_name"] == "example/ancillary"
        ]
        source = [row for row in rows if row["repo_name"] == "example/source"]
        assert all(row["has_only_clear_ancillary_failures"] == "1" for row in ancillary)
        assert source[0]["parse_complete_source_candidate"] == "0"

        with (
            output / "run-py-9b-source-candidate-manual-review.csv"
        ).open("r", encoding="utf-8", newline="") as handle:
            review_rows = list(csv.DictReader(handle))
        assert len(review_rows) == 1
        assert review_rows[0]["relative_path"] == "src/broken.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Classify run-py-9a parse-failure paths and audit repository-month "
            "snapshot completeness without reading outcomes."
        )
    )
    parser.add_argument("--history-snapshot-manifest", type=Path)
    parser.add_argument("--parse-failures", type=Path)
    parser.add_argument("--python-file-inventory", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--allow-missing-file-inventory", action="store_true")
    parser.add_argument("--self-test-only", action="store_true")
    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.self_test_only:
        return
    required = {
        "--history-snapshot-manifest": args.history_snapshot_manifest,
        "--parse-failures": args.parse_failures,
        "--output-dir": args.output_dir,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("Missing required arguments: " + ", ".join(missing))
    if args.python_file_inventory is None and not args.allow_missing_file_inventory:
        parser.error(
            "--python-file-inventory is required unless "
            "--allow-missing-file-inventory is used"
        )
    for label, path in (
        ("history snapshot manifest", args.history_snapshot_manifest),
        ("parse failures", args.parse_failures),
        ("Python file inventory", args.python_file_inventory),
    ):
        if path is not None and (not path.is_file() or path.stat().st_size == 0):
            parser.error(f"Missing or empty {label}: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(args, parser)

    if args.self_test_only:
        run_self_test()
        print("Self-test: PASS")
        return 0

    metadata = run_audit(
        args.history_snapshot_manifest,
        args.parse_failures,
        args.python_file_inventory,
        args.output_dir,
        args.overwrite_output,
    )
    counts = metadata["counts"]
    print(
        "Audit complete: "
        f"repository_months={counts['repository_months']}, "
        f"failure_commit_files="
        f"{counts['parse_failure_repository_commit_file_occurrences']}, "
        f"failure_month_files="
        f"{counts['parse_failure_repository_month_file_occurrences']}, "
        f"unique_failed_blobs={counts['unique_failed_blobs']}, "
        f"source_candidate_manual_review_rows="
        f"{counts['source_candidate_manual_review_rows']}, "
        f"critical_qc_failures={counts['critical_qc_failures']}"
    )
    print(f"Status: {metadata['status']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileExistsError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
