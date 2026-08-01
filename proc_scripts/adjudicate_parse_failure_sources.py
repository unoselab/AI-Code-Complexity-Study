#!/usr/bin/env python3
"""Freeze outcome-blind manual adjudications for run-py-7f04 sources.

This stage reads only the source-evidence table produced by run-py-7f04. It
does not read AGC/HWC labels, function-role outcomes, DiD panels, ATT results,
or confidence intervals. The locked adjudications were completed by direct
source inspection on 2026-07-31.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import tempfile
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


SCHEMA_VERSION = "run-py-7f05-v1"
MANUAL_REVIEW_DATE = "2026-07-31"
PRIMARY_INVENTORY_ACTION = "exclude_from_python3_ast_inventory"
ROBUSTNESS_MONTH_ACTION = "exclude_repository_month"


class ValidationError(RuntimeError):
    """Raised when the evidence does not match the locked adjudication set."""


@dataclass(frozen=True)
class Adjudication:
    review_id: str
    dataset_source: str
    repo_name: str
    relative_path: str
    git_blob_sha: str
    final_source_class: str
    source_completeness: str
    parser_scope_status: str
    manual_rationale: str
    regular_module_function_count_if_known: Optional[int]
    regular_module_function_note: str


LOCKED_ADJUDICATIONS = (
    Adjudication(
        "source-review-001",
        "control",
        "MalevichAI/malevich",
        "malevich/_analytics/models/__init__.py",
        "9c7e9e864c64a78e2b8fc351e07e7a092159bc27",
        "malformed_incomplete",
        "incomplete",
        "invalid_source",
        "The file ends after an incomplete 'from ' import statement.",
        None,
        "No valid module AST exists, so regular module functions are not recoverable without changing the source.",
    ),
    Adjudication(
        "source-review-002",
        "control",
        "adelatour11/androidtvbackground",
        "TMDB.py",
        "49c68655de86aae1d92bc29dee8f5b2bdf8b3a94",
        "malformed_incomplete",
        "incomplete",
        "invalid_source",
        "The Bearer authorization string has no closing quotation mark.",
        None,
        "No valid module AST exists, so regular module functions are not recoverable without changing the source.",
    ),
    Adjudication(
        "source-review-003",
        "treatment",
        "Multi-V-VM/MVVM",
        "artifact/ckpt_restore_latency.py",
        "ef0f3d8923572b48b3d3f300ee4b63218d801747",
        "malformed_incomplete",
        "incomplete",
        "invalid_source",
        "A function header was commented out while its indented body remained active.",
        None,
        "No valid module AST exists, so regular module functions are not recoverable without changing the source.",
    ),
    Adjudication(
        "source-review-004",
        "treatment",
        "Multi-V-VM/MVVM",
        "artifact/ckpt_restore_latency.py",
        "fa6018cdf7993d91cb381535895840693aae0e27",
        "malformed_incomplete",
        "incomplete",
        "invalid_source",
        "The four-line file is truncated at an incomplete import and function declaration.",
        None,
        "No valid module AST exists, so regular module functions are not recoverable without changing the source.",
    ),
    Adjudication(
        "source-review-005",
        "treatment",
        "TextGeneratorio/text-generator.io",
        "gameon/facebook.py",
        "2ba249dc73be5fe5b7c7269cfac79e776197edb5",
        "valid_python2",
        "complete",
        "unsupported_python2_dialect",
        "The complete file parses as Python 2 and uses Python 2 exception syntax.",
        5,
        "Manual Python 2 review identified five top-level regular functions; they remain excluded from the Python 3 AST inventory.",
    ),
    Adjudication(
        "source-review-006",
        "treatment",
        "TextGeneratorio/text-generator.io",
        "questions/inference_server/inference_server.py",
        "b38d7e9ef42aec6e966bbc2e7bde666148e0df00",
        "malformed_incomplete",
        "incomplete",
        "invalid_source",
        "A nested if statement has only commented lines and therefore no executable body.",
        None,
        "No valid module AST exists, so regular module functions are not recoverable without changing the source.",
    ),
    Adjudication(
        "source-review-007",
        "treatment",
        "TextGeneratorio/text-generator.io",
        "questions/inference_server/inference_server.py",
        "c6a8736c5f3cf0631e0de6e2605b9cf0c3621312",
        "malformed_incomplete",
        "incomplete",
        "invalid_source",
        "The file ends at an if __name__ == '__main__' guard with no body.",
        None,
        "No valid module AST exists, so regular module functions are not recoverable without changing the source.",
    ),
    Adjudication(
        "source-review-008",
        "treatment",
        "TextGeneratorio/text-generator.io",
        "scripts/onnx_compile.py",
        "2d8d97d8e96759ec947588ae6e1ca3c89c98bef0",
        "ipython_style",
        "complete",
        "unsupported_ipython_magic",
        "The file is an IPython-style script; removing the '% time' magic line permits Python 3 parsing.",
        0,
        "Manual inspection found no top-level regular functions; the raw source remains excluded without rewriting notebook magic.",
    ),
    Adjudication(
        "source-review-009",
        "treatment",
        "TextGeneratorio/text-generator.io",
        "scripts/onnx_compile.py",
        "a88a802881591ffe94f2336a5444380fcd79d4f9",
        "ipython_style",
        "complete",
        "unsupported_ipython_magic",
        "The file is an IPython-style script; removing the '% time' magic line permits Python 3 parsing.",
        0,
        "Manual inspection found no top-level regular functions; the raw source remains excluded without rewriting notebook magic.",
    ),
    Adjudication(
        "source-review-010",
        "treatment",
        "ericyuegu/hal",
        "hal/training/models/gpt_cached.py",
        "9512baaad8dfb8bf7e2bd89be5378d2ce4c09df4",
        "malformed_incomplete",
        "incomplete",
        "invalid_source",
        "The update method declaration is missing its colon and body.",
        None,
        "No valid module AST exists, so regular module functions are not recoverable without changing the source.",
    ),
    Adjudication(
        "source-review-011",
        "treatment",
        "terryyin/lizard",
        "profile.py",
        "7d387ec7d9b8a479ac66ac8da118c9c2fe7bc899",
        "valid_python2",
        "complete",
        "unsupported_python2_dialect",
        "The complete file parses as Python 2 and uses a Python 2 print statement.",
        0,
        "Manual Python 2 review found no top-level regular functions; the file remains excluded from the Python 3 AST inventory.",
    ),
)

LOCKED_BY_ID = {item.review_id: item for item in LOCKED_ADJUDICATIONS}

EXPECTED_CLASS_COUNTS = {
    "valid_python2": {"blobs": 2, "commit_occurrences": 25, "repo_month_memberships": 37},
    "ipython_style": {"blobs": 2, "commit_occurrences": 15, "repo_month_memberships": 20},
    "malformed_incomplete": {"blobs": 7, "commit_occurrences": 11, "repo_month_memberships": 28},
}

REQUIRED_INPUT_COLUMNS = {
    "review_id",
    "dataset_source",
    "repo_name",
    "relative_path",
    "git_blob_sha",
    "fresh_parse_status",
    "fresh_parse_mode",
    "git_object_hash_matches",
    "verified_commit_occurrences",
    "expected_commit_occurrences",
    "repository_month_occurrences",
    "commits_json",
    "months_json",
    "review_decision",
    "review_note",
}

ADJUDICATION_OUTPUT_COLUMNS = (
    "adjudication_schema_version",
    "manual_review_date",
    "final_source_class",
    "source_completeness",
    "parser_scope_status",
    "primary_inventory_action",
    "robustness_month_action",
    "regular_module_function_count_if_known",
    "regular_module_function_note",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_nonnegative_int(value: Any, label: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} must be an integer; got {value!r}") from exc
    if parsed < 0:
        raise ValidationError(f"{label} must be non-negative; got {parsed}")
    return parsed


def parse_true(value: Any, label: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValidationError(f"{label} must be a boolean-like value; got {value!r}")


def parse_json_string_list(value: str, label: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise ValidationError(f"{label} must be a JSON array of strings")
    return parsed


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValidationError(f"Missing or empty input CSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValidationError(f"Input CSV has no header: {path}")
        rows = list(reader)
        return list(reader.fieldnames), rows


def write_csv(path: Path, fieldnames: Iterable[str], rows: Iterable[dict[str, Any]]) -> None:
    names = list(fieldnames)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in names})


def validate_and_adjudicate(
    fieldnames: list[str],
    rows: list[dict[str, str]],
    expected_review_rows: int,
    expected_commit_occurrences: int,
) -> list[dict[str, Any]]:
    missing_columns = sorted(REQUIRED_INPUT_COLUMNS - set(fieldnames))
    if missing_columns:
        raise ValidationError(f"Input is missing required columns: {missing_columns}")
    if len(rows) != expected_review_rows:
        raise ValidationError(
            f"Expected {expected_review_rows} manual-review rows; found {len(rows)}"
        )

    review_ids = [row["review_id"].strip() for row in rows]
    if len(review_ids) != len(set(review_ids)):
        raise ValidationError("Input review_id values are not unique")
    expected_ids = set(LOCKED_BY_ID)
    observed_ids = set(review_ids)
    if observed_ids != expected_ids:
        raise ValidationError(
            "Input review IDs do not match the locked adjudication set; "
            f"missing={sorted(expected_ids - observed_ids)}, "
            f"unexpected={sorted(observed_ids - expected_ids)}"
        )

    total_commit_occurrences = 0
    adjudicated_rows: list[dict[str, Any]] = []
    for input_row in sorted(rows, key=lambda item: item["review_id"]):
        review_id = input_row["review_id"].strip()
        locked = LOCKED_BY_ID[review_id]
        for identity_column in (
            "dataset_source",
            "repo_name",
            "relative_path",
            "git_blob_sha",
        ):
            observed = input_row[identity_column].strip()
            expected = str(getattr(locked, identity_column))
            if observed != expected:
                raise ValidationError(
                    f"{review_id}: {identity_column} changed; expected {expected!r}, "
                    f"found {observed!r}"
                )

        if input_row["review_decision"].strip() or input_row["review_note"].strip():
            raise ValidationError(
                f"{review_id}: run-py-7f04 evidence must retain blank manual-review fields"
            )
        if input_row["fresh_parse_status"].strip() != "failure":
            raise ValidationError(f"{review_id}: fresh_parse_status must be 'failure'")
        if input_row["fresh_parse_mode"].strip() != "type_comments_true_and_false_failed":
            raise ValidationError(f"{review_id}: unexpected fresh_parse_mode")
        if not parse_true(
            input_row["git_object_hash_matches"],
            f"{review_id}.git_object_hash_matches",
        ):
            raise ValidationError(f"{review_id}: extracted Git object hash was not verified")

        verified_commits = parse_nonnegative_int(
            input_row["verified_commit_occurrences"],
            f"{review_id}.verified_commit_occurrences",
        )
        expected_commits = parse_nonnegative_int(
            input_row["expected_commit_occurrences"],
            f"{review_id}.expected_commit_occurrences",
        )
        if verified_commits != expected_commits:
            raise ValidationError(f"{review_id}: verified and expected commit counts differ")
        commits = parse_json_string_list(input_row["commits_json"], f"{review_id}.commits_json")
        if len(commits) != verified_commits or len(commits) != len(set(commits)):
            raise ValidationError(f"{review_id}: commits_json does not match the verified count")

        month_count = parse_nonnegative_int(
            input_row["repository_month_occurrences"],
            f"{review_id}.repository_month_occurrences",
        )
        months = parse_json_string_list(input_row["months_json"], f"{review_id}.months_json")
        if len(months) != month_count or len(months) != len(set(months)):
            raise ValidationError(f"{review_id}: months_json does not match the month count")
        invalid_months = [month for month in months if not re.fullmatch(r"\d{4}-\d{2}", month)]
        if invalid_months:
            raise ValidationError(f"{review_id}: invalid YYYY-MM values: {invalid_months}")

        total_commit_occurrences += verified_commits
        output_row: dict[str, Any] = dict(input_row)
        output_row["review_decision"] = locked.final_source_class
        output_row["review_note"] = locked.manual_rationale
        output_row.update(
            {
                "adjudication_schema_version": SCHEMA_VERSION,
                "manual_review_date": MANUAL_REVIEW_DATE,
                "final_source_class": locked.final_source_class,
                "source_completeness": locked.source_completeness,
                "parser_scope_status": locked.parser_scope_status,
                "primary_inventory_action": PRIMARY_INVENTORY_ACTION,
                "robustness_month_action": ROBUSTNESS_MONTH_ACTION,
                "regular_module_function_count_if_known": (
                    ""
                    if locked.regular_module_function_count_if_known is None
                    else locked.regular_module_function_count_if_known
                ),
                "regular_module_function_note": locked.regular_module_function_note,
            }
        )
        adjudicated_rows.append(output_row)

    if total_commit_occurrences != expected_commit_occurrences:
        raise ValidationError(
            f"Expected {expected_commit_occurrences} commit occurrences; "
            f"found {total_commit_occurrences}"
        )
    return adjudicated_rows


def aggregate_affected_months(adjudicated_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"review_ids": set(), "blob_shas": set(), "classes": set(), "paths": set()}
    )
    for row in adjudicated_rows:
        months = parse_json_string_list(str(row["months_json"]), f"{row['review_id']}.months_json")
        for month in months:
            key = (str(row["dataset_source"]), str(row["repo_name"]), month)
            grouped[key]["review_ids"].add(str(row["review_id"]))
            grouped[key]["blob_shas"].add(str(row["git_blob_sha"]))
            grouped[key]["classes"].add(str(row["final_source_class"]))
            grouped[key]["paths"].add(str(row["relative_path"]))

    output: list[dict[str, Any]] = []
    for (dataset_source, repo_name, month), values in sorted(grouped.items()):
        classes = sorted(values["classes"])
        output.append(
            {
                "dataset_source": dataset_source,
                "repo_name": repo_name,
                "time": month,
                "source_candidate_blob_count": len(values["blob_shas"]),
                "review_ids_json": json.dumps(sorted(values["review_ids"])),
                "git_blob_shas_json": json.dumps(sorted(values["blob_shas"])),
                "relative_paths_json": json.dumps(sorted(values["paths"])),
                "final_source_classes_json": json.dumps(classes),
                "contains_valid_python2": int("valid_python2" in classes),
                "contains_ipython_style": int("ipython_style" in classes),
                "contains_malformed_incomplete": int("malformed_incomplete" in classes),
                "python3_ast_inventory_complete": 0,
                "robustness_month_action": ROBUSTNESS_MONTH_ACTION,
            }
        )
    return output


def aggregate_affected_repositories(
    affected_month_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"months": set(), "review_ids": set(), "blob_shas": set(), "classes": set()}
    )
    for row in affected_month_rows:
        key = (str(row["dataset_source"]), str(row["repo_name"]))
        grouped[key]["months"].add(str(row["time"]))
        grouped[key]["review_ids"].update(json.loads(str(row["review_ids_json"])))
        grouped[key]["blob_shas"].update(json.loads(str(row["git_blob_shas_json"])))
        grouped[key]["classes"].update(json.loads(str(row["final_source_classes_json"])))

    output: list[dict[str, Any]] = []
    for (dataset_source, repo_name), values in sorted(grouped.items()):
        output.append(
            {
                "dataset_source": dataset_source,
                "repo_name": repo_name,
                "affected_month_count": len(values["months"]),
                "affected_blob_count": len(values["blob_shas"]),
                "months_json": json.dumps(sorted(values["months"])),
                "review_ids_json": json.dumps(sorted(values["review_ids"])),
                "git_blob_shas_json": json.dumps(sorted(values["blob_shas"])),
                "final_source_classes_json": json.dumps(sorted(values["classes"])),
                "strong_robustness_action": "exclude_repository_all_months",
            }
        )
    return output


def build_class_summary(adjudicated_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"blobs": 0, "commit_occurrences": 0, "repo_month_memberships": 0, "repos": set()}
    )
    for row in adjudicated_rows:
        source_class = str(row["final_source_class"])
        grouped[source_class]["blobs"] += 1
        grouped[source_class]["commit_occurrences"] += int(row["verified_commit_occurrences"])
        grouped[source_class]["repo_month_memberships"] += int(row["repository_month_occurrences"])
        grouped[source_class]["repos"].add((row["dataset_source"], row["repo_name"]))

    return [
        {
            "final_source_class": source_class,
            "blobs": values["blobs"],
            "commit_occurrences": values["commit_occurrences"],
            "repository_month_memberships": values["repo_month_memberships"],
            "affected_repositories": len(values["repos"]),
            "primary_inventory_action": PRIMARY_INVENTORY_ACTION,
            "robustness_month_action": ROBUSTNESS_MONTH_ACTION,
        }
        for source_class, values in sorted(grouped.items())
    ]


def check_class_summary(summary_rows: list[dict[str, Any]]) -> bool:
    observed = {
        row["final_source_class"]: {
            "blobs": int(row["blobs"]),
            "commit_occurrences": int(row["commit_occurrences"]),
            "repo_month_memberships": int(row["repository_month_memberships"]),
        }
        for row in summary_rows
    }
    return observed == EXPECTED_CLASS_COUNTS


def qc_row(
    check_name: str,
    passed: bool,
    observed: Any,
    expected: Any,
    note: str,
    severity: str = "critical",
) -> dict[str, Any]:
    return {
        "check_name": check_name,
        "severity": severity,
        "passed": str(bool(passed)),
        "observed": observed,
        "expected": expected,
        "note": note,
    }


def publish_output(staging_dir: Path, output_dir: Path, overwrite_output: bool) -> None:
    if output_dir.exists() and not overwrite_output:
        raise ValidationError(
            f"Output directory already exists; set --overwrite-output to replace it: {output_dir}"
        )
    if not output_dir.exists():
        staging_dir.replace(output_dir)
        return

    backup_dir = output_dir.with_name(f".{output_dir.name}.backup-{uuid.uuid4().hex}")
    output_dir.replace(backup_dir)
    try:
        staging_dir.replace(output_dir)
    except Exception:
        backup_dir.replace(output_dir)
        raise
    shutil.rmtree(backup_dir)


def run_self_test() -> None:
    if len(LOCKED_ADJUDICATIONS) != 11 or len(LOCKED_BY_ID) != 11:
        raise AssertionError("Locked adjudication IDs must contain 11 unique rows")
    if Counter(item.final_source_class for item in LOCKED_ADJUDICATIONS) != Counter(
        {"valid_python2": 2, "ipython_style": 2, "malformed_incomplete": 7}
    ):
        raise AssertionError("Locked class counts changed")
    parsed = parse_json_string_list('["2025-01", "2025-02"]', "self_test")
    if parsed != ["2025-01", "2025-02"]:
        raise AssertionError("JSON list parsing failed")
    synthetic = [
        {
            "review_id": "a",
            "dataset_source": "treatment",
            "repo_name": "owner/repo",
            "relative_path": "a.py",
            "git_blob_sha": "a" * 40,
            "months_json": '["2025-01", "2025-02"]',
            "final_source_class": "valid_python2",
        },
        {
            "review_id": "b",
            "dataset_source": "treatment",
            "repo_name": "owner/repo",
            "relative_path": "b.py",
            "git_blob_sha": "b" * 40,
            "months_json": '["2025-02"]',
            "final_source_class": "ipython_style",
        },
    ]
    aggregated = aggregate_affected_months(synthetic)
    if len(aggregated) != 2 or int(aggregated[1]["source_candidate_blob_count"]) != 2:
        raise AssertionError("Repository-month overlap was not deduplicated correctly")
    print("Self-test: PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze manual adjudications for run-py-7f04 source evidence."
    )
    parser.add_argument("--manual-review-evidence", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-review-rows", type=int, default=11)
    parser.add_argument("--expected-commit-occurrences", type=int, default=51)
    parser.add_argument("--expected-affected-repository-months", type=int, default=66)
    parser.add_argument("--expected-affected-repositories", type=int, default=6)
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--self-test-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test_only:
        run_self_test()
        return 0
    if args.manual_review_evidence is None or args.output_dir is None:
        raise ValidationError(
            "Production mode requires --manual-review-evidence and --output-dir"
        )
    for name in (
        "expected_review_rows",
        "expected_commit_occurrences",
        "expected_affected_repository_months",
        "expected_affected_repositories",
    ):
        if getattr(args, name) < 0:
            raise ValidationError(f"--{name.replace('_', '-')} must be non-negative")

    input_path = args.manual_review_evidence.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir == output_dir.parent:
        raise ValidationError(f"Refusing broad output directory: {output_dir}")
    if output_dir.exists() and not args.overwrite_output:
        raise ValidationError(
            f"Output directory already exists; set --overwrite-output to replace it: {output_dir}"
        )

    fieldnames, input_rows = read_csv(input_path)
    adjudicated_rows = validate_and_adjudicate(
        fieldnames,
        input_rows,
        args.expected_review_rows,
        args.expected_commit_occurrences,
    )
    affected_month_rows = aggregate_affected_months(adjudicated_rows)
    affected_repository_rows = aggregate_affected_repositories(affected_month_rows)
    summary_rows = build_class_summary(adjudicated_rows)

    dataset_source_counts = Counter(row["dataset_source"] for row in affected_month_rows)
    qc_rows = [
        qc_row(
            "manual_adjudication_row_count",
            len(adjudicated_rows) == args.expected_review_rows,
            len(adjudicated_rows),
            args.expected_review_rows,
            "Every locked source-candidate blob must receive exactly one adjudication.",
        ),
        qc_row(
            "commit_occurrence_count",
            sum(int(row["verified_commit_occurrences"]) for row in adjudicated_rows)
            == args.expected_commit_occurrences,
            sum(int(row["verified_commit_occurrences"]) for row in adjudicated_rows),
            args.expected_commit_occurrences,
            "The adjudicated blobs must retain all verified historical commit:path occurrences.",
        ),
        qc_row(
            "locked_class_summary",
            check_class_summary(summary_rows),
            json.dumps(
                {
                    row["final_source_class"]: {
                        "blobs": row["blobs"],
                        "commit_occurrences": row["commit_occurrences"],
                        "repo_month_memberships": row["repository_month_memberships"],
                    }
                    for row in summary_rows
                },
                sort_keys=True,
            ),
            json.dumps(EXPECTED_CLASS_COUNTS, sort_keys=True),
            "Manual class counts must match the outcome-blind 2026-07-31 review.",
        ),
        qc_row(
            "unique_affected_repository_months",
            len(affected_month_rows) == args.expected_affected_repository_months,
            len(affected_month_rows),
            args.expected_affected_repository_months,
            "Overlapping blob memberships must be deduplicated by dataset_source, repo_name, and time.",
        ),
        qc_row(
            "unique_affected_repositories",
            len(affected_repository_rows) == args.expected_affected_repositories,
            len(affected_repository_rows),
            args.expected_affected_repositories,
            "Affected repositories must be deduplicated by dataset_source and repo_name.",
        ),
        qc_row(
            "affected_month_dataset_source_distribution",
            dataset_source_counts == Counter({"treatment": 53, "control": 13}),
            json.dumps(dict(sorted(dataset_source_counts.items()))),
            json.dumps({"control": 13, "treatment": 53}),
            "The 66 affected repository-months must retain the audited treatment/control distribution.",
        ),
        qc_row(
            "all_primary_inventory_actions_are_exclusion",
            all(
                row["primary_inventory_action"] == PRIMARY_INVENTORY_ACTION
                for row in adjudicated_rows
            ),
            sum(
                row["primary_inventory_action"] == PRIMARY_INVENTORY_ACTION
                for row in adjudicated_rows
            ),
            len(adjudicated_rows),
            "Raw sources must not be rewritten or silently repaired for the primary Python 3 AST inventory.",
        ),
        qc_row(
            "agc_hwc_or_did_inputs_used",
            True,
            "NONE",
            "NONE",
            "This adjudication stage is outcome-blind and reads only run-py-7f04 source evidence.",
        ),
    ]
    failed_critical = [
        row for row in qc_rows if row["severity"] == "critical" and row["passed"] != "True"
    ]
    if failed_critical:
        failed_names = [row["check_name"] for row in failed_critical]
        raise ValidationError(f"Critical QC checks failed: {failed_names}")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    try:
        adjudication_path = staging_dir / "run-py-7f05-manual-adjudication.csv"
        affected_months_path = staging_dir / "run-py-7f05-affected-repository-months.csv"
        affected_repositories_path = staging_dir / "run-py-7f05-affected-repositories.csv"
        summary_path = staging_dir / "run-py-7f05-adjudication-summary.csv"
        qc_path = staging_dir / "run-py-7f05-adjudication-qc.csv"
        metadata_path = staging_dir / "run-py-7f05-adjudication-metadata.json"

        output_fieldnames = fieldnames + [
            name for name in ADJUDICATION_OUTPUT_COLUMNS if name not in fieldnames
        ]
        write_csv(adjudication_path, output_fieldnames, adjudicated_rows)
        write_csv(
            affected_months_path,
            (
                "dataset_source",
                "repo_name",
                "time",
                "source_candidate_blob_count",
                "review_ids_json",
                "git_blob_shas_json",
                "relative_paths_json",
                "final_source_classes_json",
                "contains_valid_python2",
                "contains_ipython_style",
                "contains_malformed_incomplete",
                "python3_ast_inventory_complete",
                "robustness_month_action",
            ),
            affected_month_rows,
        )
        write_csv(
            affected_repositories_path,
            (
                "dataset_source",
                "repo_name",
                "affected_month_count",
                "affected_blob_count",
                "months_json",
                "review_ids_json",
                "git_blob_shas_json",
                "final_source_classes_json",
                "strong_robustness_action",
            ),
            affected_repository_rows,
        )
        write_csv(
            summary_path,
            (
                "final_source_class",
                "blobs",
                "commit_occurrences",
                "repository_month_memberships",
                "affected_repositories",
                "primary_inventory_action",
                "robustness_month_action",
            ),
            summary_rows,
        )
        write_csv(
            qc_path,
            ("check_name", "severity", "passed", "observed", "expected", "note"),
            qc_rows,
        )

        metadata = {
            "schema_version": SCHEMA_VERSION,
            "status": "PASS",
            "purpose": "Outcome-blind manual adjudication of residual source-candidate parse failures",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "manual_review_date": MANUAL_REVIEW_DATE,
            "script": {
                "path": str(Path(__file__).resolve()),
                "sha256": sha256_file(Path(__file__).resolve()),
                "python_version": sys.version.split()[0],
            },
            "inputs": {
                "manual_review_evidence": str(input_path),
                "manual_review_evidence_sha256": sha256_file(input_path),
                "agc_hwc_inputs": "NONE",
                "function_role_outcomes": "NONE",
                "did_panel_inputs": "NONE",
                "att_or_confidence_interval_inputs": "NONE",
            },
            "policy": {
                "primary_inventory_action": PRIMARY_INVENTORY_ACTION,
                "robustness_month_action": ROBUSTNESS_MONTH_ACTION,
                "source_rewriting": "PROHIBITED",
                "malformed_source_repair": "PROHIBITED",
            },
            "counts": {
                "adjudicated_blobs": len(adjudicated_rows),
                "commit_path_occurrences": sum(
                    int(row["verified_commit_occurrences"]) for row in adjudicated_rows
                ),
                "repository_month_memberships_before_deduplication": sum(
                    int(row["repository_month_occurrences"]) for row in adjudicated_rows
                ),
                "unique_affected_repository_months": len(affected_month_rows),
                "unique_affected_repositories": len(affected_repository_rows),
                "affected_treatment_repository_months": dataset_source_counts["treatment"],
                "affected_control_repository_months": dataset_source_counts["control"],
                "critical_qc_failures": 0,
            },
            "class_counts": {
                row["final_source_class"]: {
                    "blobs": row["blobs"],
                    "commit_occurrences": row["commit_occurrences"],
                    "repository_month_memberships": row["repository_month_memberships"],
                }
                for row in summary_rows
            },
            "outputs": {
                "manual_adjudication": adjudication_path.name,
                "affected_repository_months": affected_months_path.name,
                "affected_repositories": affected_repositories_path.name,
                "adjudication_summary": summary_path.name,
                "adjudication_qc": qc_path.name,
            },
        }
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )

        publish_output(staging_dir, output_dir, args.overwrite_output)
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        raise

    print("run-py-7f05 adjudication complete")
    print(f"Adjudicated blobs:              {len(adjudicated_rows)}")
    print(f"Commit:path occurrences:        {args.expected_commit_occurrences}")
    print(f"Affected repository-months:     {len(affected_month_rows)}")
    print(f"Affected repositories:          {len(affected_repository_rows)}")
    print(f"Output directory:               {output_dir}")
    print("Status:                         PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
