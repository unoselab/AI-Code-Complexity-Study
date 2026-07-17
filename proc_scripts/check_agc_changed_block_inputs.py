#!/usr/bin/env python3
"""Validate inputs needed for the AGC changed-block repository-month analysis.

This checker does not create the final changed-block panel. It verifies that:
1. Existing detector block predictions contain stable block-level keys.
2. The snapshot manifest supports previous/current monthly commit pairing.
3. Cloned repositories still contain the exact commits and can compute Python diffs.
4. Re-parsing current snapshot files with the detector's own tree-sitter logic
   reproduces the stored detector block keys exactly.

The final changed-block preparation script should be created only after this
checker passes on the real project data.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tokenize
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


DETECTOR_PROFILE = (
    "codellama-7b_4500_complexity_stratified_maxlen2048_svm_ast"
)

BLOCK_REQUIRED_COLUMNS = [
    "dataset_source",
    "repo_name",
    "repo_slug",
    "commit",
    "relative_path",
    "content_sha256",
    "block_idx",
    "block_kind",
    "block_name",
    "start_line",
    "end_line",
    "pred_label",
    "predicted_agc",
]

BLOCK_KEY_COLUMNS = [
    "dataset_source",
    "repo_name",
    "commit",
    "relative_path",
    "block_idx",
]

BLOCK_ALIGNMENT_COLUMNS = [
    "block_idx",
    "block_kind",
    "block_name",
    "start_line",
    "end_line",
]

MANIFEST_REQUIRED_COLUMNS = [
    "dataset_source",
    "repo_name",
    "month",
    "latest_commit",
    "snapshot_dir",
    "python_file_count",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check inputs for AGC changed-block panel preparation."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(
            "repo_python/run-py-3a/strict/repo_month_snapshot_manifest.csv"
        ),
    )
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=Path("repo_python/run-py-3a/strict/python_snapshots"),
    )
    parser.add_argument(
        "--detector-root",
        type=Path,
        default=Path(f"../python_snapshots_detect/{DETECTOR_PROFILE}/strict"),
    )
    parser.add_argument("--block-treatment", type=Path, default=None)
    parser.add_argument("--block-control", type=Path, default=None)
    parser.add_argument(
        "--agc-detector-script",
        type=Path,
        default=Path("../../ai_detector/src/app/agc_detector.py"),
    )
    parser.add_argument(
        "--tree-sitter-lib",
        type=Path,
        default=Path(
            "../../ai_detector/src/code-analyzer-tree-sitter/build/my-languages.so"
        ),
    )
    parser.add_argument(
        "--ast-helper-dir",
        type=Path,
        default=Path("../../ai_detector/src/code-analyzer-tree-sitter"),
    )
    parser.add_argument(
        "--treatment-clone-dir",
        type=Path,
        default=Path("../treatment-repos"),
    )
    parser.add_argument(
        "--control-clone-dir",
        type=Path,
        default=Path("../control-repos"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("repo_python/tmp/run-py-4a-input-check/strict"),
    )
    parser.add_argument(
        "--alignment-files-per-source",
        type=int,
        default=25,
        help="Number of detector files per source to re-parse for exact key alignment.",
    )
    parser.add_argument(
        "--max-diff-pairs-per-source",
        type=int,
        default=25,
        help="Number of consecutive monthly pairs per source to test with git diff.",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=200_000,
    )
    parser.add_argument(
        "--skip-clone-checks",
        action="store_true",
    )
    return parser.parse_args()


def require_file(path: Path, label: str) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return path


def require_dir(path: Path, label: str) -> Path:
    path = path.expanduser().resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return path


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temp, index=False)
    os.replace(temp, path)


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_detector_module(script_path: Path):
    spec = importlib.util.spec_from_file_location(
        "agc_detector_changed_block_input_check",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import detector module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def month_number(period: pd.Period) -> int:
    return period.year * 12 + period.month


def validate_manifest(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    manifest = pd.read_csv(path, dtype={"latest_commit": "string"})
    missing = sorted(set(MANIFEST_REQUIRED_COLUMNS) - set(manifest.columns))
    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "section": "manifest",
            "check": "required_columns_present",
            "passed": int(not missing),
            "value": ";".join(missing),
        }
    )
    if missing:
        raise ValueError(f"Manifest missing columns: {missing}")

    for column in ["dataset_source", "repo_name", "month", "latest_commit"]:
        manifest[column] = manifest[column].astype(str).str.strip()

    duplicate_count = int(
        manifest.duplicated(["dataset_source", "repo_name", "month"]).sum()
    )
    checks.append(
        {
            "section": "manifest",
            "check": "unique_source_repo_month",
            "passed": int(duplicate_count == 0),
            "value": duplicate_count,
        }
    )

    manifest["month_period"] = pd.PeriodIndex(manifest["month"], freq="M")
    manifest = manifest.sort_values(
        ["dataset_source", "repo_name", "month_period"]
    ).reset_index(drop=True)
    grouped = manifest.groupby(["dataset_source", "repo_name"], sort=False)
    manifest["previous_month"] = grouped["month_period"].shift(1)
    manifest["previous_commit"] = grouped["latest_commit"].shift(1)
    manifest["previous_snapshot_dir"] = grouped["snapshot_dir"].shift(1)

    current_numbers = manifest["month_period"].map(month_number)
    previous_numbers = manifest["previous_month"].map(
        lambda value: month_number(value) if pd.notna(value) else pd.NA
    )
    manifest["month_gap"] = current_numbers - previous_numbers
    manifest["has_previous_month"] = manifest["previous_commit"].notna().astype(int)
    manifest["is_consecutive_month"] = manifest["month_gap"].eq(1).astype(int)
    manifest["same_commit_as_previous"] = (
        manifest["latest_commit"].eq(manifest["previous_commit"])
        & manifest["previous_commit"].notna()
    ).astype(int)

    pairs = manifest.loc[
        manifest["has_previous_month"].eq(1),
        [
            "dataset_source",
            "repo_name",
            "previous_month",
            "month_period",
            "previous_commit",
            "latest_commit",
            "previous_snapshot_dir",
            "snapshot_dir",
            "month_gap",
            "is_consecutive_month",
            "same_commit_as_previous",
        ],
    ].copy()
    pairs = pairs.rename(
        columns={"month_period": "month", "latest_commit": "current_commit"}
    )
    pairs["previous_month"] = pairs["previous_month"].astype(str)
    pairs["month"] = pairs["month"].astype(str)

    consecutive = int(pairs["is_consecutive_month"].sum())
    nonconsecutive = int((pairs["is_consecutive_month"] == 0).sum())
    checks.extend(
        [
            {
                "section": "manifest",
                "check": "repo_month_rows",
                "passed": 1,
                "value": len(manifest),
            },
            {
                "section": "manifest",
                "check": "monthly_pairs",
                "passed": 1,
                "value": len(pairs),
            },
            {
                "section": "manifest",
                "check": "consecutive_month_pairs",
                "passed": int(consecutive > 0),
                "value": consecutive,
            },
            {
                "section": "manifest",
                "check": "nonconsecutive_month_pairs",
                "passed": 1,
                "value": nonconsecutive,
            },
        ]
    )
    return manifest, pairs, checks


def inspect_block_file(
    path: Path,
    expected_source: str,
    chunksize: int,
    sample_file_limit: int,
) -> tuple[dict[str, Any], list[pd.DataFrame]]:
    header = pd.read_csv(path, nrows=0)
    missing = sorted(set(BLOCK_REQUIRED_COLUMNS) - set(header.columns))
    if missing:
        raise ValueError(f"{path} missing detector columns: {missing}")

    rows = 0
    source_mismatches = 0
    invalid_predictions = 0
    invalid_line_ranges = 0
    duplicate_key_hashes = 0
    seen_hashes: set[int] = set()
    sampled_file_keys: list[tuple[str, str, str]] = []
    sampled_file_key_set: set[tuple[str, str, str]] = set()

    usecols = list(dict.fromkeys(BLOCK_REQUIRED_COLUMNS))
    for chunk in pd.read_csv(
        path,
        usecols=usecols,
        dtype={"commit": "string"},
        chunksize=chunksize,
        low_memory=False,
    ):
        rows += len(chunk)
        source_mismatches += int(
            chunk["dataset_source"].astype(str).ne(expected_source).sum()
        )
        prediction_values = pd.to_numeric(
            chunk["predicted_agc"], errors="coerce"
        )
        invalid_predictions += int((~prediction_values.isin([0, 1])).sum())
        starts = pd.to_numeric(chunk["start_line"], errors="coerce")
        ends = pd.to_numeric(chunk["end_line"], errors="coerce")
        invalid_line_ranges += int(
            (starts.isna() | ends.isna() | (starts < 1) | (ends < starts)).sum()
        )

        key_hashes = pd.util.hash_pandas_object(
            chunk[BLOCK_KEY_COLUMNS].astype(str), index=False
        ).astype("uint64")
        for key_hash in key_hashes.tolist():
            key_int = int(key_hash)
            if key_int in seen_hashes:
                duplicate_key_hashes += 1
            else:
                seen_hashes.add(key_int)

        if len(sampled_file_keys) < sample_file_limit:
            for file_key in chunk[["repo_name", "commit", "relative_path"]].itertuples(
                index=False, name=None
            ):
                normalized_key = tuple(str(value) for value in file_key)
                if normalized_key in sampled_file_key_set:
                    continue
                sampled_file_key_set.add(normalized_key)
                sampled_file_keys.append(normalized_key)
                if len(sampled_file_keys) >= sample_file_limit:
                    break

    sample_parts: dict[tuple[str, str, str], list[pd.DataFrame]] = {
        key: [] for key in sampled_file_keys
    }
    if sample_parts:
        for chunk in pd.read_csv(
            path,
            usecols=usecols,
            dtype={"commit": "string"},
            chunksize=chunksize,
            low_memory=False,
        ):
            normalized = chunk[["repo_name", "commit", "relative_path"]].astype(str)
            keys = list(normalized.itertuples(index=False, name=None))
            for key in sample_parts:
                mask = [candidate == key for candidate in keys]
                if any(mask):
                    sample_parts[key].append(chunk.loc[mask].copy())
    sampled_frames = [
        pd.concat(sample_parts[key], ignore_index=True)
        for key in sampled_file_keys
        if sample_parts[key]
    ]

    summary = {
        "dataset_source": expected_source,
        "path": str(path),
        "columns": ",".join(header.columns),
        "rows": rows,
        "missing_required_columns": ";".join(missing),
        "source_mismatches": source_mismatches,
        "invalid_predictions": invalid_predictions,
        "invalid_line_ranges": invalid_line_ranges,
        "duplicate_block_key_hashes": duplicate_key_hashes,
        "sampled_files": len(sampled_frames),
        "schema_pass": int(
            not missing
            and source_mismatches == 0
            and invalid_predictions == 0
            and invalid_line_ranges == 0
            and duplicate_key_hashes == 0
        ),
    }
    return summary, sampled_frames


def locate_snapshot_file(
    snapshot_root: Path,
    source: str,
    repo_slug: str,
    commit: str,
    relative_path: str,
) -> Path:
    return snapshot_root / source / repo_slug / commit / Path(relative_path)


def validate_block_alignment(
    sampled_frames_by_source: dict[str, list[pd.DataFrame]],
    snapshot_root: Path,
    detector_module,
    parser,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for source, sampled_frames in sampled_frames_by_source.items():
        for stored in sampled_frames:
            first = stored.iloc[0]
            repo_slug = str(first["repo_slug"])
            commit = str(first["commit"])
            relative_path = str(first["relative_path"])
            snapshot_file = locate_snapshot_file(
                snapshot_root,
                source,
                repo_slug,
                commit,
                relative_path,
            )
            record: dict[str, Any] = {
                "dataset_source": source,
                "repo_name": str(first["repo_name"]),
                "commit": commit,
                "relative_path": relative_path,
                "snapshot_file": str(snapshot_file),
                "stored_blocks": len(stored),
                "parsed_blocks": pd.NA,
                "content_sha_matches": 0,
                "exact_key_alignment": 0,
                "error": "",
            }
            try:
                if not snapshot_file.is_file():
                    raise FileNotFoundError(snapshot_file)
                actual_sha = sha256_file(snapshot_file)
                expected_sha = str(first["content_sha256"])
                record["content_sha_matches"] = int(actual_sha == expected_sha)

                with tokenize.open(snapshot_file) as handle:
                    source_text = handle.read()
                parsed_blocks = detector_module.extract_blocks(source_text, parser)
                parsed = pd.DataFrame(
                    [
                        {
                            "block_idx": index,
                            "block_kind": block["kind"],
                            "block_name": block["name"],
                            "start_line": int(block["start_line"]),
                            "end_line": int(block["end_line"]),
                        }
                        for index, block in enumerate(parsed_blocks, start=1)
                    ]
                )
                record["parsed_blocks"] = len(parsed)

                stored_keys = stored[BLOCK_ALIGNMENT_COLUMNS].copy()
                for column in ["block_idx", "start_line", "end_line"]:
                    stored_keys[column] = pd.to_numeric(
                        stored_keys[column], errors="raise"
                    ).astype(int)
                stored_keys = stored_keys.sort_values("block_idx").reset_index(
                    drop=True
                )
                parsed = parsed[BLOCK_ALIGNMENT_COLUMNS].sort_values(
                    "block_idx"
                ).reset_index(drop=True)
                record["exact_key_alignment"] = int(stored_keys.equals(parsed))
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(record)
    return pd.DataFrame(rows)


def run_git(repo: Path, arguments: Iterable[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def validate_clone_commits(
    manifest: pd.DataFrame,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    clone_roots = {
        "treatment": treatment_clone_dir,
        "control": control_clone_dir,
    }
    unique = manifest.drop_duplicates(
        ["dataset_source", "repo_name", "latest_commit"]
    )
    for row in unique.itertuples(index=False):
        source = str(row.dataset_source)
        repo_name = str(row.repo_name)
        commit = str(row.latest_commit)
        repo_slug = repo_name.replace("/", "_")
        repo_dir = clone_roots[source] / repo_slug
        exists = repo_dir.is_dir()
        commit_exists = 0
        error = ""
        if exists:
            result = run_git(repo_dir, ["cat-file", "-e", f"{commit}^{{commit}}"])
            commit_exists = int(result.returncode == 0)
            if result.returncode != 0:
                error = result.stderr.strip()
        else:
            error = "clone directory missing"
        rows.append(
            {
                "dataset_source": source,
                "repo_name": repo_name,
                "latest_commit": commit,
                "repo_dir": str(repo_dir),
                "repo_dir_exists": int(exists),
                "commit_exists": commit_exists,
                "error": error,
            }
        )
    return pd.DataFrame(rows)


def validate_git_diffs(
    pairs: pd.DataFrame,
    treatment_clone_dir: Path,
    control_clone_dir: Path,
    max_pairs_per_source: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    clone_roots = {
        "treatment": treatment_clone_dir,
        "control": control_clone_dir,
    }
    eligible = pairs.loc[pairs["is_consecutive_month"].eq(1)].copy()
    for source, source_pairs in eligible.groupby("dataset_source", sort=True):
        selected = source_pairs.head(max_pairs_per_source)
        for pair in selected.itertuples(index=False):
            repo_slug = str(pair.repo_name).replace("/", "_")
            repo_dir = clone_roots[str(source)] / repo_slug
            result = run_git(
                repo_dir,
                [
                    "diff",
                    "--name-status",
                    "--find-renames",
                    str(pair.previous_commit),
                    str(pair.current_commit),
                    "--",
                    "*.py",
                ],
            )
            output_lines = [
                line for line in result.stdout.splitlines() if line.strip()
            ]
            rows.append(
                {
                    "dataset_source": source,
                    "repo_name": pair.repo_name,
                    "previous_month": pair.previous_month,
                    "month": pair.month,
                    "previous_commit": pair.previous_commit,
                    "current_commit": pair.current_commit,
                    "repo_dir": str(repo_dir),
                    "git_diff_exit_code": result.returncode,
                    "python_diff_rows": len(output_lines),
                    "stderr": result.stderr.strip(),
                }
            )
    return pd.DataFrame(rows)


def build_checks(
    manifest_checks: list[dict[str, Any]],
    block_summaries: pd.DataFrame,
    alignment: pd.DataFrame,
    clone_commits: pd.DataFrame | None,
    git_diffs: pd.DataFrame | None,
) -> pd.DataFrame:
    checks = list(manifest_checks)
    for row in block_summaries.itertuples(index=False):
        checks.append(
            {
                "section": "block_predictions",
                "check": f"{row.dataset_source}_schema_and_key",
                "passed": int(row.schema_pass),
                "value": row.rows,
            }
        )

    alignment_errors = int(alignment["error"].astype(str).ne("").sum())
    alignment_mismatches = int(alignment["exact_key_alignment"].ne(1).sum())
    hash_mismatches = int(alignment["content_sha_matches"].ne(1).sum())
    checks.extend(
        [
            {
                "section": "block_alignment",
                "check": "sample_files_checked",
                "passed": int(len(alignment) > 0),
                "value": len(alignment),
            },
            {
                "section": "block_alignment",
                "check": "snapshot_content_hash_matches",
                "passed": int(hash_mismatches == 0),
                "value": hash_mismatches,
            },
            {
                "section": "block_alignment",
                "check": "detector_keys_reproduced_exactly",
                "passed": int(alignment_mismatches == 0 and alignment_errors == 0),
                "value": alignment_mismatches,
            },
        ]
    )

    if clone_commits is not None:
        missing_repos = int(clone_commits["repo_dir_exists"].ne(1).sum())
        missing_commits = int(clone_commits["commit_exists"].ne(1).sum())
        checks.extend(
            [
                {
                    "section": "clone_commits",
                    "check": "all_clone_directories_exist",
                    "passed": int(missing_repos == 0),
                    "value": missing_repos,
                },
                {
                    "section": "clone_commits",
                    "check": "all_manifest_commits_exist",
                    "passed": int(missing_commits == 0),
                    "value": missing_commits,
                },
            ]
        )
    if git_diffs is not None:
        diff_failures = int(git_diffs["git_diff_exit_code"].ne(0).sum())
        checks.append(
            {
                "section": "git_diff",
                "check": "sample_monthly_diffs_succeed",
                "passed": int(len(git_diffs) > 0 and diff_failures == 0),
                "value": diff_failures,
            }
        )
    return pd.DataFrame(checks)


def main() -> int:
    args = parse_args()
    args.detector_root = require_dir(args.detector_root, "detector root")
    args.block_treatment = require_file(
        args.block_treatment
        or args.detector_root / "block_predictions_treatment.csv",
        "treatment block predictions",
    )
    args.block_control = require_file(
        args.block_control
        or args.detector_root / "block_predictions_control.csv",
        "control block predictions",
    )
    args.manifest = require_file(args.manifest, "repo-month snapshot manifest")
    args.snapshot_root = require_dir(args.snapshot_root, "snapshot root")
    args.agc_detector_script = require_file(
        args.agc_detector_script, "AGC detector script"
    )
    args.tree_sitter_lib = require_file(
        args.tree_sitter_lib, "tree-sitter language library"
    )
    args.ast_helper_dir = require_dir(args.ast_helper_dir, "AST helper directory")
    args.output_dir = args.output_dir.expanduser().resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest, pairs, manifest_checks = validate_manifest(args.manifest)

    block_summary_rows: list[dict[str, Any]] = []
    sampled_frames_by_source: dict[str, list[pd.DataFrame]] = {}
    for source, path in [
        ("treatment", args.block_treatment),
        ("control", args.block_control),
    ]:
        summary, samples = inspect_block_file(
            path,
            source,
            args.chunksize,
            args.alignment_files_per_source,
        )
        block_summary_rows.append(summary)
        sampled_frames_by_source[source] = samples
    block_summaries = pd.DataFrame(block_summary_rows)

    detector_module = load_detector_module(args.agc_detector_script)
    parser, _ = detector_module.load_parser_and_F(
        str(args.tree_sitter_lib), str(args.ast_helper_dir)
    )
    alignment = validate_block_alignment(
        sampled_frames_by_source,
        args.snapshot_root,
        detector_module,
        parser,
    )

    clone_commits: pd.DataFrame | None = None
    git_diffs: pd.DataFrame | None = None
    if not args.skip_clone_checks:
        treatment_clone_dir = require_dir(
            args.treatment_clone_dir, "treatment clone directory"
        )
        control_clone_dir = require_dir(
            args.control_clone_dir, "control clone directory"
        )
        clone_commits = validate_clone_commits(
            manifest, treatment_clone_dir, control_clone_dir
        )
        git_diffs = validate_git_diffs(
            pairs,
            treatment_clone_dir,
            control_clone_dir,
            args.max_diff_pairs_per_source,
        )

    checks = build_checks(
        manifest_checks,
        block_summaries,
        alignment,
        clone_commits,
        git_diffs,
    )
    failed = int(checks["passed"].ne(1).sum())
    status = "PASS" if failed == 0 else "FAIL"

    atomic_write_csv(
        block_summaries,
        args.output_dir / "agc_changed_block_prediction_schema.csv",
    )
    atomic_write_csv(
        pairs,
        args.output_dir / "agc_changed_block_month_pairs.csv",
    )
    atomic_write_csv(
        alignment,
        args.output_dir / "agc_changed_block_key_alignment_sample.csv",
    )
    if clone_commits is not None:
        atomic_write_csv(
            clone_commits,
            args.output_dir / "agc_changed_block_clone_commit_checks.csv",
        )
    if git_diffs is not None:
        atomic_write_csv(
            git_diffs,
            args.output_dir / "agc_changed_block_git_diff_checks.csv",
        )
    atomic_write_csv(
        checks,
        args.output_dir / "agc_changed_block_input_checks.csv",
    )

    summary = {
        "status": status,
        "checks_total": len(checks),
        "checks_passed": int(checks["passed"].eq(1).sum()),
        "checks_failed": failed,
        "manifest_rows": len(manifest),
        "monthly_pairs": len(pairs),
        "consecutive_month_pairs": int(pairs["is_consecutive_month"].sum()),
        "same_commit_pairs": int(pairs["same_commit_as_previous"].sum()),
        "detector_block_rows": {
            str(row.dataset_source): int(row.rows)
            for row in block_summaries.itertuples(index=False)
        },
        "alignment_files_checked": len(alignment),
        "alignment_mismatches": int(alignment["exact_key_alignment"].ne(1).sum()),
        "clone_commit_rows_checked": 0 if clone_commits is None else len(clone_commits),
        "clone_commit_failures": (
            0
            if clone_commits is None
            else int(clone_commits["commit_exists"].ne(1).sum())
        ),
        "git_diff_pairs_checked": 0 if git_diffs is None else len(git_diffs),
        "git_diff_failures": (
            0
            if git_diffs is None
            else int(git_diffs["git_diff_exit_code"].ne(0).sum())
        ),
        "output_dir": str(args.output_dir),
    }
    atomic_write_json(
        summary,
        args.output_dir / "agc_changed_block_input_check_summary.json",
    )

    print("=" * 72)
    print("AGC changed-block input check")
    print(f"Status:                    {status}")
    print(f"Checks passed:             {summary['checks_passed']}/{summary['checks_total']}")
    print(f"Manifest rows:             {summary['manifest_rows']}")
    print(f"Consecutive month pairs:   {summary['consecutive_month_pairs']}")
    print(f"Alignment files checked:   {summary['alignment_files_checked']}")
    print(f"Alignment mismatches:      {summary['alignment_mismatches']}")
    print(f"Clone commits checked:     {summary['clone_commit_rows_checked']}")
    print(f"Clone commit failures:     {summary['clone_commit_failures']}")
    print(f"Git diff pairs checked:    {summary['git_diff_pairs_checked']}")
    print(f"Git diff failures:         {summary['git_diff_failures']}")
    print(f"Output directory:          {summary['output_dir']}")
    print("=" * 72)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
