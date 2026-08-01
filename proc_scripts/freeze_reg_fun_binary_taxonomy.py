#!/usr/bin/env python3
"""Freeze the binary function taxonomy: testing versus other functions.

This stage converts the outcome-blind run-py-7f06 candidate assignments into
an exhaustive, mutually exclusive two-group taxonomy. It does not create
repository-month outcomes and does not read or estimate treatment effects.

Scientific boundaries
---------------------
- A body-month unit is ``testing`` when run-py-7f06 records the testing signal.
- Testing includes test functions, fixtures, and test-support helpers detected
  by test-oriented function names or source paths.
- Every remaining body-month unit is assigned to ``other_functions``.
- Earlier candidate roles (main, web/API, CLI, validation, and other_general)
  are intentionally collapsed into ``other_functions``.
- Decorators remain provenance fields and do not define a third group.
- No monthly panel, ATT, standard error, confidence interval, or p-value is
  read or computed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCRIPT_VERSION = "run-py-7f07-v1"
INPUT_SCHEMA_VERSION = "run-py-7f06-v1"
TAXONOMY_STATUS = "FROZEN_BINARY"
TAXONOMY_VERSION = "testing-vs-other-functions-v1"

KEY_COLUMNS = [
    "dataset_source",
    "repo_name",
    "time",
    "function_body_sha256",
]

REQUIRED_ASSIGNMENT_COLUMNS = {
    *KEY_COLUMNS,
    "time_to_event",
    "treatment_period",
    "event_context_count",
    "function_names",
    "relative_paths",
    "testing",
    "test_name",
    "test_path",
    "candidate_primary_role",
    "candidate_context_roles",
    "context_role_disagreement",
    "decorator_callables",
    "taxonomy_status",
}

OUTPUT_ASSIGNMENT_COLUMNS = [
    *KEY_COLUMNS,
    "time_to_event",
    "treatment_period",
    "event_context_count",
    "function_names",
    "relative_paths",
    "test_name",
    "test_path",
    "testing_signal",
    "function_group",
    "function_group_label",
    "candidate_primary_role_7f06",
    "candidate_context_roles_7f06",
    "context_role_disagreement_7f06",
    "decorator_callables",
    "taxonomy_status",
    "taxonomy_version",
]

GROUPS = ["testing", "other_functions"]
GROUP_LABELS = {
    "testing": "Testing and test-support functions",
    "other_functions": "Other functions",
}


class ValidationError(RuntimeError):
    """Raised when an input or cross-artifact invariant is violated."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assignments", type=Path)
    parser.add_argument("--audit-metadata", type=Path)
    parser.add_argument("--audit-qc", type=Path)
    parser.add_argument("--candidate-taxonomy", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-body-months", type=int, default=2249)
    parser.add_argument("--expected-testing", type=int, default=627)
    parser.add_argument("--expected-other-functions", type=int, default=1622)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--self-test-only", action="store_true")
    return parser.parse_args(argv)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"Expected a JSON object in {path}")
    return value


def parse_bool01(value: str, label: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true"}:
        return True
    if normalized in {"0", "false"}:
        return False
    raise ValidationError(f"{label} must be 0/1 or true/false; found {value!r}")


def require_positive(value: int, label: str) -> None:
    if value <= 0:
        raise ValidationError(f"{label} must be positive; found {value}")


def validate_input_contract(
    metadata: Mapping[str, Any],
    qc_path: Path,
    taxonomy: Mapping[str, Any],
) -> None:
    if metadata.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise ValidationError(
            "Unexpected run-py-7f06 schema_version: "
            f"{metadata.get('schema_version')!r}"
        )
    if metadata.get("status") != "PASS":
        raise ValidationError("run-py-7f06 metadata status must be PASS")
    if metadata.get("taxonomy_status") != "CANDIDATE_NOT_FROZEN":
        raise ValidationError(
            "run-py-7f06 taxonomy_status must be CANDIDATE_NOT_FROZEN"
        )

    scope = metadata.get("scientific_scope")
    if not isinstance(scope, dict):
        raise ValidationError("run-py-7f06 scientific_scope is missing")
    if scope.get("att_or_uncertainty_computed") is not False:
        raise ValidationError("run-py-7f06 must not compute ATT or uncertainty")
    if scope.get("role_specific_monthly_outcomes_created") is not False:
        raise ValidationError("run-py-7f06 must not create role-specific outcomes")
    if scope.get("full_history_audit_is_outcome_blind") is not True:
        raise ValidationError("run-py-7f06 audit must be outcome-blind")

    with qc_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"check_name", "severity", "passed"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValidationError(f"Unexpected run-py-7f06 QC schema: {qc_path}")
        qc_rows = list(reader)
    if not qc_rows:
        raise ValidationError("run-py-7f06 QC is empty")
    failed_critical = [
        row.get("check_name", "")
        for row in qc_rows
        if row.get("severity") == "critical"
        and not parse_bool01(row.get("passed", ""), "run-py-7f06 QC passed")
    ]
    if failed_critical:
        raise ValidationError(
            "run-py-7f06 has failed critical QC checks: "
            + ", ".join(failed_critical)
        )

    roles = taxonomy.get("primary_candidate_roles")
    precedence = taxonomy.get("precedence")
    if not isinstance(roles, list) or "testing" not in roles:
        raise ValidationError("run-py-7f06 taxonomy must include testing")
    if not isinstance(precedence, list) or not precedence or precedence[0] != "testing":
        raise ValidationError("run-py-7f06 precedence must place testing first")


def classify_row(row: Mapping[str, str], row_number: int) -> tuple[str, bool]:
    testing = parse_bool01(row["testing"], f"row {row_number} testing")
    test_name = parse_bool01(row["test_name"], f"row {row_number} test_name")
    test_path = parse_bool01(row["test_path"], f"row {row_number} test_path")
    if testing != (test_name or test_path):
        raise ValidationError(
            f"row {row_number} testing must equal test_name OR test_path"
        )

    candidate_role = row["candidate_primary_role"].strip()
    if testing != (candidate_role == "testing"):
        raise ValidationError(
            f"row {row_number} testing signal disagrees with 7f06 primary role"
        )
    return ("testing" if testing else "other_functions"), testing


def load_and_classify(
    assignments_path: Path,
) -> tuple[list[dict[str, str]], Counter[str], Counter[tuple[str, str, str]], dict[str, set[str]]]:
    output_rows: list[dict[str, str]] = []
    group_counts: Counter[str] = Counter()
    support_counts: Counter[tuple[str, str, str]] = Counter()
    repositories: dict[str, set[str]] = defaultdict(set)
    seen_keys: set[tuple[str, ...]] = set()

    with assignments_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValidationError(f"Assignments file has no header: {assignments_path}")
        missing = sorted(REQUIRED_ASSIGNMENT_COLUMNS - set(reader.fieldnames))
        if missing:
            raise ValidationError(
                "run-py-7f06 assignments are missing columns: " + ", ".join(missing)
            )

        for row_number, row in enumerate(reader, start=2):
            key = tuple(row[column].strip() for column in KEY_COLUMNS)
            if any(not value for value in key):
                raise ValidationError(f"row {row_number} has an empty primary key")
            if key in seen_keys:
                raise ValidationError(f"row {row_number} duplicates key {key}")
            seen_keys.add(key)

            group, testing = classify_row(row, row_number)
            dataset_source = row["dataset_source"].strip()
            treatment_period = row["treatment_period"].strip()
            if dataset_source not in {"treatment", "control"}:
                raise ValidationError(
                    f"row {row_number} has invalid dataset_source {dataset_source!r}"
                )
            if treatment_period not in {"pre", "event", "post", "control"}:
                raise ValidationError(
                    f"row {row_number} has invalid treatment_period "
                    f"{treatment_period!r}"
                )
            if dataset_source == "control" and treatment_period != "control":
                raise ValidationError(
                    f"row {row_number} control row must use treatment_period=control"
                )
            if dataset_source == "treatment" and treatment_period == "control":
                raise ValidationError(
                    f"row {row_number} treatment row cannot use control period"
                )

            output_rows.append(
                {
                    **{column: row[column] for column in KEY_COLUMNS},
                    "time_to_event": row["time_to_event"],
                    "treatment_period": treatment_period,
                    "event_context_count": row["event_context_count"],
                    "function_names": row["function_names"],
                    "relative_paths": row["relative_paths"],
                    "test_name": "1" if parse_bool01(row["test_name"], "test_name") else "0",
                    "test_path": "1" if parse_bool01(row["test_path"], "test_path") else "0",
                    "testing_signal": "1" if testing else "0",
                    "function_group": group,
                    "function_group_label": GROUP_LABELS[group],
                    "candidate_primary_role_7f06": row["candidate_primary_role"],
                    "candidate_context_roles_7f06": row["candidate_context_roles"],
                    "context_role_disagreement_7f06": row["context_role_disagreement"],
                    "decorator_callables": row["decorator_callables"],
                    "taxonomy_status": TAXONOMY_STATUS,
                    "taxonomy_version": TAXONOMY_VERSION,
                }
            )
            group_counts[group] += 1
            support_counts[(group, dataset_source, treatment_period)] += 1
            repositories[group].add(row["repo_name"].strip())

    return output_rows, group_counts, support_counts, repositories


def make_summary_rows(
    counts: Mapping[str, int],
    repositories: Mapping[str, set[str]],
    total: int,
) -> list[dict[str, Any]]:
    return [
        {
            "function_group": group,
            "function_group_label": GROUP_LABELS[group],
            "body_month_units": counts.get(group, 0),
            "repositories": len(repositories.get(group, set())),
            "share_of_body_month_units": counts.get(group, 0) / total,
        }
        for group in GROUPS
    ]


def make_support_rows(
    support: Mapping[tuple[str, str, str], int],
    output_rows: Iterable[Mapping[str, str]],
) -> list[dict[str, Any]]:
    repo_support: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in output_rows:
        key = (row["function_group"], row["dataset_source"], row["treatment_period"])
        repo_support[key].add(row["repo_name"])
    rows: list[dict[str, Any]] = []
    for group in GROUPS:
        for dataset_source, period in (
            ("control", "control"),
            ("treatment", "pre"),
            ("treatment", "event"),
            ("treatment", "post"),
        ):
            key = (group, dataset_source, period)
            rows.append(
                {
                    "function_group": group,
                    "dataset_source": dataset_source,
                    "treatment_period": period,
                    "body_month_units": support.get(key, 0),
                    "repositories": len(repo_support.get(key, set())),
                }
            )
    return rows


def qc_row(
    name: str,
    passed: bool,
    observed: Any,
    expected: Any,
    note: str,
) -> dict[str, Any]:
    return {
        "check_name": name,
        "severity": "critical",
        "passed": passed,
        "observed": observed,
        "expected": expected,
        "note": note,
    }


def build_qc(
    rows: Sequence[Mapping[str, str]],
    counts: Mapping[str, int],
    expected_total: int,
    expected_testing: int,
    expected_other: int,
) -> list[dict[str, Any]]:
    assigned_groups = {row["function_group"] for row in rows}
    key_count = len({tuple(row[column] for column in KEY_COLUMNS) for row in rows})
    testing_mismatches = sum(
        (row["testing_signal"] == "1") != (row["function_group"] == "testing")
        for row in rows
    )
    other_mismatches = sum(
        (row["testing_signal"] == "0")
        != (row["function_group"] == "other_functions")
        for row in rows
    )
    return [
        qc_row(
            "primary_body_month_units",
            len(rows) == expected_total,
            len(rows),
            expected_total,
            "The locked run-py-7f06 body-month scope must be preserved.",
        ),
        qc_row(
            "unique_primary_keys",
            key_count == len(rows),
            key_count,
            len(rows),
            "Each body-month unit must occur exactly once.",
        ),
        qc_row(
            "testing_units",
            counts.get("testing", 0) == expected_testing,
            counts.get("testing", 0),
            expected_testing,
            "Testing is the locked name-or-path testing signal from run-py-7f06.",
        ),
        qc_row(
            "other_function_units",
            counts.get("other_functions", 0) == expected_other,
            counts.get("other_functions", 0),
            expected_other,
            "All non-testing units must be assigned to other_functions.",
        ),
        qc_row(
            "binary_group_sum",
            sum(counts.values()) == expected_total,
            sum(counts.values()),
            expected_total,
            "The two groups must exhaust all body-month units.",
        ),
        qc_row(
            "exact_group_set",
            assigned_groups == set(GROUPS),
            "|".join(sorted(assigned_groups)),
            "other_functions|testing",
            "No third group is permitted.",
        ),
        qc_row(
            "duplicate_assignments",
            key_count == len(rows),
            len(rows) - key_count,
            0,
            "Every body-month unit must receive one group only.",
        ),
        qc_row(
            "unassigned_units",
            all(row["function_group"] in GROUPS for row in rows),
            sum(row["function_group"] not in GROUPS for row in rows),
            0,
            "Every body-month unit must receive a binary group.",
        ),
        qc_row(
            "testing_rule_mismatches",
            testing_mismatches == 0,
            testing_mismatches,
            0,
            "testing_signal=1 must map only to testing.",
        ),
        qc_row(
            "other_rule_mismatches",
            other_mismatches == 0,
            other_mismatches,
            0,
            "testing_signal=0 must map only to other_functions.",
        ),
        qc_row(
            "taxonomy_frozen",
            TAXONOMY_STATUS == "FROZEN_BINARY",
            TAXONOMY_STATUS,
            "FROZEN_BINARY",
            "The outcome-blind binary grouping decision is fixed.",
        ),
    ]


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(
    output_dir: Path,
    assignments: Sequence[Mapping[str, str]],
    summary: Sequence[Mapping[str, Any]],
    support: Sequence[Mapping[str, Any]],
    qc: Sequence[Mapping[str, Any]],
    taxonomy: Mapping[str, Any],
    metadata: Mapping[str, Any],
    overwrite: bool,
) -> None:
    output_names = [
        "run-py-7f07-primary-body-month-binary-group-assignments.csv",
        "run-py-7f07-binary-group-summary.csv",
        "run-py-7f07-binary-group-support.csv",
        "run-py-7f07-binary-taxonomy.json",
        "run-py-7f07-binary-taxonomy-qc.csv",
        "run-py-7f07-binary-taxonomy-metadata.json",
    ]
    existing = [output_dir / name for name in output_names if (output_dir / name).exists()]
    if existing and not overwrite:
        raise ValidationError(
            "Output files already exist; use --overwrite for an intentional rerun: "
            + ", ".join(str(path) for path in existing)
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=".run-py-7f07-", dir=output_dir))
    try:
        write_csv(
            staging_dir / output_names[0],
            assignments,
            OUTPUT_ASSIGNMENT_COLUMNS,
        )
        write_csv(
            staging_dir / output_names[1],
            summary,
            [
                "function_group",
                "function_group_label",
                "body_month_units",
                "repositories",
                "share_of_body_month_units",
            ],
        )
        write_csv(
            staging_dir / output_names[2],
            support,
            [
                "function_group",
                "dataset_source",
                "treatment_period",
                "body_month_units",
                "repositories",
            ],
        )
        (staging_dir / output_names[3]).write_text(
            json.dumps(taxonomy, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_csv(
            staging_dir / output_names[4],
            qc,
            ["check_name", "severity", "passed", "observed", "expected", "note"],
        )
        (staging_dir / output_names[5]).write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for name in output_names:
            os.replace(staging_dir / name, output_dir / name)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def run_self_test() -> None:
    base = {
        "dataset_source": "treatment",
        "repo_name": "example/repo",
        "time": "2025-01",
        "function_body_sha256": "a" * 64,
        "time_to_event": "0",
        "treatment_period": "event",
        "event_context_count": "1",
        "function_names": "sample",
        "relative_paths": "src/module.py",
        "candidate_context_roles": "other_general",
        "context_role_disagreement": "0",
        "decorator_callables": "",
        "taxonomy_status": "CANDIDATE_NOT_FROZEN",
    }
    testing_row = {
        **base,
        "testing": "1",
        "test_name": "0",
        "test_path": "1",
        "candidate_primary_role": "testing",
    }
    group, signal = classify_row(testing_row, 2)
    if group != "testing" or not signal:
        raise ValidationError("Self-test failed for testing assignment")

    other_row = {
        **base,
        "testing": "0",
        "test_name": "0",
        "test_path": "0",
        "candidate_primary_role": "web_api_handler",
    }
    group, signal = classify_row(other_row, 3)
    if group != "other_functions" or signal:
        raise ValidationError("Self-test failed for other_functions assignment")

    invalid_row = {
        **testing_row,
        "testing": "0",
    }
    try:
        classify_row(invalid_row, 4)
    except ValidationError:
        pass
    else:
        raise ValidationError("Self-test failed to reject inconsistent testing evidence")

    print("Self-test: PASS")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.self_test_only:
            run_self_test()
            return 0

        required_paths = {
            "assignments": args.assignments,
            "audit metadata": args.audit_metadata,
            "audit QC": args.audit_qc,
            "candidate taxonomy": args.candidate_taxonomy,
        }
        for label, path in required_paths.items():
            if path is None or not path.is_file() or path.stat().st_size == 0:
                raise ValidationError(f"Missing or empty {label}: {path}")
        if args.output_dir is None:
            raise ValidationError("--output-dir is required")

        require_positive(args.expected_body_months, "expected body-months")
        require_positive(args.expected_testing, "expected testing")
        require_positive(args.expected_other_functions, "expected other functions")
        if args.expected_testing + args.expected_other_functions != args.expected_body_months:
            raise ValidationError(
                "Expected testing plus other_functions must equal expected body-months"
            )

        audit_metadata = read_json(args.audit_metadata)
        candidate_taxonomy = read_json(args.candidate_taxonomy)
        validate_input_contract(audit_metadata, args.audit_qc, candidate_taxonomy)

        assignments, counts, support_counts, repositories = load_and_classify(
            args.assignments
        )
        summary = make_summary_rows(counts, repositories, len(assignments))
        support = make_support_rows(support_counts, assignments)
        qc = build_qc(
            assignments,
            counts,
            args.expected_body_months,
            args.expected_testing,
            args.expected_other_functions,
        )
        critical_failures = sum(
            row["severity"] == "critical" and not row["passed"] for row in qc
        )

        frozen_taxonomy = {
            "schema_version": SCRIPT_VERSION,
            "taxonomy_status": TAXONOMY_STATUS,
            "taxonomy_version": TAXONOMY_VERSION,
            "unit_of_assignment": (
                "distinct function_body_sha256 within dataset_source, repo_name, and month"
            ),
            "groups": [
                {
                    "id": "testing",
                    "label": GROUP_LABELS["testing"],
                    "definition": (
                        "A regular synchronous module function with a test-oriented "
                        "function name or source path; includes test cases, fixtures, "
                        "and test-support helpers."
                    ),
                    "rule": "testing_signal == 1",
                },
                {
                    "id": "other_functions",
                    "label": GROUP_LABELS["other_functions"],
                    "definition": (
                        "Every regular synchronous module function that does not have "
                        "the testing signal."
                    ),
                    "rule": "testing_signal == 0",
                },
            ],
            "partition_policy": {
                "mutually_exclusive": True,
                "exhaustive": True,
                "precedence_required": False,
                "unassigned_policy": "prohibited",
                "third_group_policy": "prohibited",
            },
            "collapsed_run_py_7f06_roles": [
                "main_entry_point",
                "web_api_handler",
                "cli_argument_processing",
                "validation_parsing_conversion",
                "other_general",
            ],
            "decorator_policy": (
                "retain decorator callables as provenance only; decorators do not "
                "create a function group"
            ),
            "decision_basis": (
                "The outcome-blind run-py-7f06 audit supported the testing rule; "
                "the remaining candidate roles were collapsed to avoid semantic "
                "misclassification and sparse control support."
            ),
            "prohibited_at_this_stage": [
                "group-specific zero-inclusive repository-month outcomes",
                "ATT estimates",
                "standard errors",
                "confidence intervals",
                "p-values",
            ],
        }

        metadata = {
            "schema_version": SCRIPT_VERSION,
            "status": "PASS" if critical_failures == 0 else "FAIL",
            "taxonomy_status": TAXONOMY_STATUS,
            "taxonomy_version": TAXONOMY_VERSION,
            "counts": {
                "primary_body_month_units": len(assignments),
                "testing_units": counts.get("testing", 0),
                "other_function_units": counts.get("other_functions", 0),
                "binary_group_sum": sum(counts.values()),
                "testing_repositories": len(repositories.get("testing", set())),
                "other_function_repositories": len(
                    repositories.get("other_functions", set())
                ),
                "duplicate_assignments": len(assignments)
                - len(
                    {
                        tuple(row[column] for column in KEY_COLUMNS)
                        for row in assignments
                    }
                ),
                "unassigned_units": sum(
                    row["function_group"] not in GROUPS for row in assignments
                ),
                "critical_qc_failures": critical_failures,
            },
            "inputs": {
                "run_py_7f06_assignments": {
                    "path": str(args.assignments),
                    "sha256": sha256_file(args.assignments),
                },
                "run_py_7f06_audit_metadata": {
                    "path": str(args.audit_metadata),
                    "sha256": sha256_file(args.audit_metadata),
                },
                "run_py_7f06_audit_qc": {
                    "path": str(args.audit_qc),
                    "sha256": sha256_file(args.audit_qc),
                },
                "run_py_7f06_candidate_taxonomy": {
                    "path": str(args.candidate_taxonomy),
                    "sha256": sha256_file(args.candidate_taxonomy),
                },
            },
            "outputs": {
                "assignments": "run-py-7f07-primary-body-month-binary-group-assignments.csv",
                "summary": "run-py-7f07-binary-group-summary.csv",
                "support": "run-py-7f07-binary-group-support.csv",
                "taxonomy": "run-py-7f07-binary-taxonomy.json",
                "qc": "run-py-7f07-binary-taxonomy-qc.csv",
            },
            "scientific_scope": {
                "binary_taxonomy_frozen": True,
                "outcome_inputs_read": False,
                "group_specific_monthly_outcomes_created": False,
                "att_or_uncertainty_computed": False,
            },
        }

        write_outputs(
            args.output_dir,
            assignments,
            summary,
            support,
            qc,
            frozen_taxonomy,
            metadata,
            args.overwrite,
        )

        print("run-py-7f07 binary taxonomy freeze complete")
        print(f"Primary body-month units:  {len(assignments):,}")
        print(f"Testing units:             {counts.get('testing', 0):,}")
        print(f"Other-function units:      {counts.get('other_functions', 0):,}")
        print(f"Binary group sum:          {sum(counts.values()):,}")
        print("Duplicate assignments:     0")
        print("Unassigned units:          0")
        print(f"Critical QC failures:      {critical_failures}")
        print(f"Taxonomy status:           {TAXONOMY_STATUS}")
        print(f"Output directory:          {args.output_dir.resolve()}")
        print(f"Status:                    {metadata['status']}")
        return 0 if critical_failures == 0 else 1
    except (ValidationError, OSError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
