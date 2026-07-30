#!/usr/bin/env python3
"""Extract frozen donor AGC outcomes and prepare a Webscout substitution panel.

This step is the first post-freeze step allowed to read AGC classifications.
It preserves the donor choice frozen by run-py-8e and the monthly commit audit
from run-py-8f. It then:

1. Counts synchronous class-method AGC unique bodies for the frozen selected
   and fallback donors in 2025-04 and 2025-06.
2. Verifies that zero-commit donor months also contain zero function events and
   zero class-method AGC unique bodies.
3. Preserves the run-py-7n fixed original-positive sample.
4. Creates a new outcome column where only HelpingAI/Webscout's 2025-04 and
   2025-06 class-method increments are replaced by the selected donor's frozen
   target-month increments.
5. Verifies that a zero donor increment is numerically equivalent to setting
   the Webscout target-month class-method increment to zero while retaining the
   repository-month rows and baseline module-function outcome.

The script prepares data only. It does not estimate a DiD model and does not
change the frozen donor after observing outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


SCRIPT_VERSION = "run-py-8g-v1"
OUTPUT_PREFIX = "webscout_rematched_donor_agc_substitution"

SELECTED_DONOR_DEFAULT = "Hack-a-Day/2024-Supercon-8-Add-On-Badge"
FALLBACK_DONOR_DEFAULT = "viktoriasemaan/sa-ai-agent"
TARGET_CONTROL_DEFAULT = "HelpingAI/Webscout"
TARGET_MONTHS_DEFAULT = ("2025-04", "2025-06")

KEY_COLUMNS = ["dataset_source", "repo_name", "time"]
EVENT_KEY_COLUMNS = ["dataset_source", "repo_name", "time"]
BODY_COLUMN = "function_body_sha256"
FUNCTION_KIND_COLUMN = "function_kind"
AGC_COLUMN = "npr_agc_like"
HWC_COLUMN = "npr_hwc_like"

ORIGINAL_MODULE_OUTCOME = "npr_agc_regular_module_function_unique_bodies"
ORIGINAL_METHOD_INCREMENT = "selected_repo_method_agc_unique_bodies"
ORIGINAL_OVERLAP = "selected_repo_module_method_agc_unique_body_overlap"
ORIGINAL_HYBRID_OUTCOME = "npr_agc_regfun_selected_classmethod_unique_bodies"

SUBSTITUTED_METHOD_INCREMENT = "webscout_frozen_donor_method_agc_unique_bodies"
SUBSTITUTED_OVERLAP = "webscout_frozen_donor_module_method_agc_unique_body_overlap"
SUBSTITUTION_APPLIED = "webscout_frozen_donor_substitution_applied"
SUBSTITUTION_OUTCOME = (
    "npr_agc_regfun_selected_classmethod_webscout_frozen_donor_"
    "substitution_unique_bodies"
)
SUBSTITUTION_LOG_OUTCOME = "log1p_" + SUBSTITUTION_OUTCOME
SUBSTITUTION_OCCURRENCE = (
    "has_npr_agc_regfun_selected_classmethod_webscout_frozen_donor_"
    "substitution_unique_body"
)
SUBSTITUTION_ZERO = (
    "zero_npr_agc_regfun_selected_classmethod_webscout_frozen_donor_"
    "substitution_unique_body_month"
)
SUBSTITUTION_READY_PAPER = (
    "analysis_ready_regfun_selected_classmethod_webscout_frozen_donor_"
    "substitution_paper_ncloc"
)
SUBSTITUTION_READY_PYTHON = (
    "analysis_ready_regfun_selected_classmethod_webscout_frozen_donor_"
    "substitution_python_snapshot_ncloc"
)

HYBRID_READY_PAPER = "analysis_ready_regfun_selected_classmethod_agc_uniquebody_paper_ncloc"
HYBRID_READY_PYTHON = (
    "analysis_ready_regfun_selected_classmethod_agc_uniquebody_"
    "python_snapshot_ncloc"
)

REPO_MONTH_METHOD_COUNT = "method_agc_unique_bodies"
REPO_MONTH_OVERLAP_COUNT = "module_method_agc_unique_body_overlap"


class AnalysisError(RuntimeError):
    """Raised when frozen-design or arithmetic validation fails."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract frozen donor class-method AGC outcomes and prepare a "
            "fixed-sample Webscout target-month substitution panel."
        )
    )
    parser.add_argument("--freeze-manifest", type=Path, required=False)
    parser.add_argument("--commit-activity", type=Path, required=False)
    parser.add_argument("--event-classifications", type=Path, required=False)
    parser.add_argument("--repo-month-counts", type=Path, required=False)
    parser.add_argument("--fixed-sample-panel", type=Path, required=False)
    parser.add_argument("--output-dir", type=Path, required=False)
    parser.add_argument("--expected-selected-donor", default=SELECTED_DONOR_DEFAULT)
    parser.add_argument("--expected-fallback-donor", default=FALLBACK_DONOR_DEFAULT)
    parser.add_argument("--target-control", default=TARGET_CONTROL_DEFAULT)
    parser.add_argument(
        "--target-month",
        action="append",
        default=None,
        help="Repeat for each YYYY-MM target month.",
    )
    parser.add_argument(
        "--expected-webscout-method-increment",
        action="append",
        default=None,
        help="Frozen target-month check in YYYY-MM=COUNT format.",
    )
    parser.add_argument("--expected-fixed-sample-rows", type=int, default=487)
    parser.add_argument("--expected-fixed-sample-repositories", type=int, default=132)
    parser.add_argument("--expected-original-hybrid-total", type=int, default=3075)
    parser.add_argument("--expected-removed-net-bodies", type=int, default=48)
    parser.add_argument("--expected-substitution-total", type=int, default=3027)
    parser.add_argument("--skip-frozen-count-checks", action="store_true")
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def normalize_repo(value: object) -> str:
    return str(value).strip().removeprefix("https://github.com/").removesuffix(".git").strip("/")


def normalize_month(value: object) -> str:
    text = str(value).strip()[:7]
    if len(text) != 7 or text[4] != "-":
        raise AnalysisError(f"Invalid YYYY-MM value: {value}")
    year, month = text.split("-", 1)
    if not (year.isdigit() and month.isdigit() and 1 <= int(month) <= 12):
        raise AnalysisError(f"Invalid YYYY-MM value: {value}")
    return text


def bool_value(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"true", "t", "1", "1.0", "yes"}


def normalize_binary(series: pd.Series, label: str) -> pd.Series:
    mapping: dict[Any, int] = {
        True: 1,
        False: 0,
        1: 1,
        0: 0,
        1.0: 1,
        0.0: 0,
        "True": 1,
        "False": 0,
        "TRUE": 1,
        "FALSE": 0,
        "true": 1,
        "false": 0,
        "1": 1,
        "0": 0,
        "1.0": 1,
        "0.0": 0,
    }
    result = series.map(mapping)
    if result.isna().any():
        examples = series[result.isna()].astype(str).head(20).tolist()
        raise AnalysisError(f"{label} contains non-binary values: {examples}")
    return result.astype("int8")


def require_file(path: Path | None, label: str) -> Path:
    if path is None or not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def require_columns(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise AnalysisError(
            f"{label} is missing required columns: {missing}. "
            f"Available columns: {list(frame.columns)}"
        )


def require_unique(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    duplicated = frame.duplicated(columns, keep=False)
    if duplicated.any():
        sample = frame.loc[duplicated, columns].head(20)
        raise AnalysisError(
            f"{label} contains duplicate keys for {columns}:\n"
            f"{sample.to_string(index=False)}"
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_output_directory(path: Path, overwrite: bool) -> None:
    if path.exists() and any(path.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"Output directory is not empty: {path}. Set overwrite intentionally."
            )
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        frame.to_csv(handle, index=False)
    os.replace(temporary, path)


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(temporary, path)


def add_check(
    rows: list[dict[str, object]],
    name: str,
    passed: bool,
    observed: object,
    expected: object,
    note: str,
) -> None:
    rows.append(
        {
            "check": name,
            "passed": bool(passed),
            "observed": observed,
            "expected": expected,
            "note": note,
        }
    )


def parse_expected_increment(values: list[str] | None, months: list[str]) -> dict[str, int]:
    if not values:
        defaults = {"2025-04": 18, "2025-06": 30}
        return {month: defaults[month] for month in months if month in defaults}
    result: dict[str, int] = {}
    for value in values:
        if "=" not in value:
            raise AnalysisError(
                "Expected Webscout increments must use YYYY-MM=COUNT format."
            )
        month_text, count_text = value.split("=", 1)
        month = normalize_month(month_text)
        try:
            count = int(count_text)
        except ValueError as error:
            raise AnalysisError(f"Invalid increment count: {value}") from error
        if count < 0:
            raise AnalysisError(f"Increment must be nonnegative: {value}")
        result[month] = count
    missing = sorted(set(months) - set(result))
    if missing:
        raise AnalysisError(f"Missing expected increments for months: {missing}")
    return result


def load_frozen_donors(
    path: Path,
    expected_selected: str,
    expected_fallback: str,
) -> tuple[pd.DataFrame, str, str, str]:
    frame = pd.read_csv(path, low_memory=False)
    require_columns(
        frame,
        [
            "freeze_role",
            "candidate_control_repo",
            "ranking_sha256",
            "frozen_before_post_adoption_outcome_review",
            "post_adoption_agc_outcome_read",
            "did_executed",
        ],
        "Freeze manifest",
    )
    frame["candidate_control_repo"] = frame["candidate_control_repo"].map(normalize_repo)
    roles = frame.set_index("freeze_role")["candidate_control_repo"].to_dict()
    selected = roles.get("selected", "")
    fallback = roles.get("fallback", "")
    expected_selected = normalize_repo(expected_selected)
    expected_fallback = normalize_repo(expected_fallback)
    if selected != expected_selected:
        raise AnalysisError(
            f"Selected donor mismatch: expected {expected_selected}, observed {selected}"
        )
    if fallback != expected_fallback:
        raise AnalysisError(
            f"Fallback donor mismatch: expected {expected_fallback}, observed {fallback}"
        )
    if not frame["frozen_before_post_adoption_outcome_review"].map(bool_value).all():
        raise AnalysisError("Donor was not frozen before outcome review.")
    if frame["post_adoption_agc_outcome_read"].map(bool_value).any():
        raise AnalysisError("Freeze manifest indicates prior AGC outcome review.")
    if frame["did_executed"].map(bool_value).any():
        raise AnalysisError("Freeze manifest indicates prior DiD execution.")
    ranking_hashes = frame["ranking_sha256"].dropna().astype(str).unique()
    if len(ranking_hashes) != 1:
        raise AnalysisError("Freeze manifest does not contain one consistent ranking SHA.")
    return frame, selected, fallback, str(ranking_hashes[0])


def load_commit_activity(
    path: Path,
    donors: set[str],
    months: set[str],
) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    require_columns(
        frame,
        [
            "repo_name",
            "target_month",
            "month_commit_count",
            "month_has_commit",
            "activity_status",
            "agc_outcome_read",
            "did_executed",
        ],
        "Commit activity audit",
    )
    frame["repo_name"] = frame["repo_name"].map(normalize_repo)
    frame["target_month"] = frame["target_month"].map(normalize_month)
    frame["month_commit_count"] = pd.to_numeric(
        frame["month_commit_count"], errors="raise"
    ).astype("int64")
    selected = frame[
        frame["repo_name"].isin(donors) & frame["target_month"].isin(months)
    ].copy()
    require_unique(selected, ["repo_name", "target_month"], "Commit activity audit")
    expected_rows = len(donors) * len(months)
    if len(selected) != expected_rows:
        raise AnalysisError(
            f"Commit audit coverage mismatch: expected {expected_rows}, observed {len(selected)}"
        )
    if selected["agc_outcome_read"].map(bool_value).any():
        raise AnalysisError("run-py-8f unexpectedly read AGC outcomes.")
    if selected["did_executed"].map(bool_value).any():
        raise AnalysisError("run-py-8f unexpectedly executed DiD.")
    return selected.sort_values(["repo_name", "target_month"]).reset_index(drop=True)


def normalize_event_keys(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["dataset_source"] = result["dataset_source"].astype("string").str.strip()
    result["repo_name"] = result["repo_name"].map(normalize_repo)
    result["time"] = result["time"].map(normalize_month)
    result[FUNCTION_KIND_COLUMN] = (
        result[FUNCTION_KIND_COLUMN].astype("string").str.strip().str.lower()
    )
    result[BODY_COLUMN] = result[BODY_COLUMN].astype("string").str.strip().str.lower()
    result[AGC_COLUMN] = normalize_binary(result[AGC_COLUMN], AGC_COLUMN)
    result[HWC_COLUMN] = normalize_binary(result[HWC_COLUMN], HWC_COLUMN)
    return result


def build_donor_outcome_audit(
    events: pd.DataFrame,
    commit_activity: pd.DataFrame,
    donors: list[str],
    months: list[str],
    selected_donor: str,
) -> pd.DataFrame:
    required = [
        *EVENT_KEY_COLUMNS,
        "function_event_id",
        BODY_COLUMN,
        FUNCTION_KIND_COLUMN,
        AGC_COLUMN,
        HWC_COLUMN,
    ]
    require_columns(events, required, "Event classifications")
    events = normalize_event_keys(events)

    rows: list[dict[str, object]] = []
    for repo_name in donors:
        for month in months:
            subset = events[
                events["repo_name"].eq(repo_name) & events["time"].eq(month)
            ].copy()
            method = subset[subset[FUNCTION_KIND_COLUMN].eq("method")].copy()
            method_agc = method[method[AGC_COLUMN].eq(1)].copy()
            commit_row = commit_activity[
                commit_activity["repo_name"].eq(repo_name)
                & commit_activity["target_month"].eq(month)
            ].iloc[0]
            rows.append(
                {
                    "donor_role": "selected" if repo_name == selected_donor else "fallback",
                    "repo_name": repo_name,
                    "target_month": month,
                    "month_commit_count": int(commit_row["month_commit_count"]),
                    "month_has_commit": bool_value(commit_row["month_has_commit"]),
                    "commit_activity_status": str(commit_row["activity_status"]),
                    "all_function_event_rows": int(len(subset)),
                    "method_event_rows": int(len(method)),
                    "method_agc_event_rows": int(len(method_agc)),
                    "method_agc_unique_bodies": int(method_agc[BODY_COLUMN].nunique()),
                    "zero_commit_zero_event_consistent": bool(
                        int(commit_row["month_commit_count"]) != 0 or len(subset) == 0
                    ),
                    "zero_commit_zero_method_agc_consistent": bool(
                        int(commit_row["month_commit_count"]) != 0
                        or method_agc[BODY_COLUMN].nunique() == 0
                    ),
                    "agc_outcome_read_in_this_step": True,
                    "did_executed": False,
                }
            )
    return pd.DataFrame(rows).sort_values(["donor_role", "target_month"]).reset_index(drop=True)


def load_repo_month_counts(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    require_columns(
        frame,
        [*KEY_COLUMNS, REPO_MONTH_METHOD_COUNT, REPO_MONTH_OVERLAP_COUNT],
        "run-py-7j repository-month counts",
    )
    result = frame.copy()
    result["dataset_source"] = result["dataset_source"].astype("string").str.strip()
    result["repo_name"] = result["repo_name"].map(normalize_repo)
    result["time"] = result["time"].map(normalize_month)
    for column in [REPO_MONTH_METHOD_COUNT, REPO_MONTH_OVERLAP_COUNT]:
        result[column] = pd.to_numeric(result[column], errors="raise").astype("int64")
    require_unique(result, KEY_COLUMNS, "run-py-7j repository-month counts")
    return result


def add_repo_month_crosscheck(
    donor_outcome: pd.DataFrame,
    repo_month_counts: pd.DataFrame,
) -> pd.DataFrame:
    result = donor_outcome.copy()
    lookup = repo_month_counts[
        ["repo_name", "time", REPO_MONTH_METHOD_COUNT, REPO_MONTH_OVERLAP_COUNT]
    ].rename(
        columns={
            "time": "target_month",
            REPO_MONTH_METHOD_COUNT: "run_py_7j_method_agc_unique_bodies",
            REPO_MONTH_OVERLAP_COUNT: "run_py_7j_module_method_overlap",
        }
    )
    result = result.merge(
        lookup,
        on=["repo_name", "target_month"],
        how="left",
        validate="one_to_one",
    )
    result["run_py_7j_method_agc_unique_bodies"] = (
        result["run_py_7j_method_agc_unique_bodies"].fillna(0).astype("int64")
    )
    result["run_py_7j_module_method_overlap"] = (
        result["run_py_7j_module_method_overlap"].fillna(0).astype("int64")
    )
    result["event_count_matches_run_py_7j_method_count"] = (
        result["method_agc_unique_bodies"].eq(
            result["run_py_7j_method_agc_unique_bodies"]
        )
    )
    return result


def load_fixed_panel(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    required = [
        *KEY_COLUMNS,
        ORIGINAL_MODULE_OUTCOME,
        ORIGINAL_METHOD_INCREMENT,
        ORIGINAL_OVERLAP,
        ORIGINAL_HYBRID_OUTCOME,
        HYBRID_READY_PAPER,
        HYBRID_READY_PYTHON,
        "sample_membership_fixed_to_run_py_7h",
        "causal_interpretation_allowed",
    ]
    require_columns(frame, required, "run-py-7n fixed-sample panel")
    result = frame.copy()
    result["dataset_source"] = result["dataset_source"].astype("string").str.strip()
    result["repo_name"] = result["repo_name"].map(normalize_repo)
    result["time"] = result["time"].map(normalize_month)
    require_unique(result, KEY_COLUMNS, "run-py-7n fixed-sample panel")
    for column in [
        ORIGINAL_MODULE_OUTCOME,
        ORIGINAL_METHOD_INCREMENT,
        ORIGINAL_OVERLAP,
        ORIGINAL_HYBRID_OUTCOME,
    ]:
        result[column] = pd.to_numeric(result[column], errors="raise").astype("int64")
    return result


def build_substitution_panel(
    panel: pd.DataFrame,
    donor_outcomes: pd.DataFrame,
    selected_donor: str,
    target_control: str,
    target_months: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    target_control = normalize_repo(target_control)
    selected_counts = donor_outcomes[
        donor_outcomes["repo_name"].eq(selected_donor)
    ].set_index("target_month")["method_agc_unique_bodies"].to_dict()

    result = panel.copy()
    target_mask = result["repo_name"].eq(target_control) & result["time"].isin(target_months)
    target_rows = result.loc[target_mask].copy()
    if len(target_rows) != len(target_months):
        raise AnalysisError(
            f"Expected one {target_control} row per target month; observed {len(target_rows)}"
        )
    if set(target_rows["time"]) != set(target_months):
        raise AnalysisError("Target control months are incomplete in the fixed sample.")

    result[SUBSTITUTION_APPLIED] = target_mask
    result[SUBSTITUTED_METHOD_INCREMENT] = result[ORIGINAL_METHOD_INCREMENT].astype("int64")
    result[SUBSTITUTED_OVERLAP] = result[ORIGINAL_OVERLAP].astype("int64")
    result["webscout_original_method_agc_unique_bodies"] = np.where(
        target_mask, result[ORIGINAL_METHOD_INCREMENT], 0
    ).astype("int64")
    result["webscout_original_module_method_agc_unique_body_overlap"] = np.where(
        target_mask, result[ORIGINAL_OVERLAP], 0
    ).astype("int64")
    result["webscout_frozen_donor_repo"] = np.where(target_mask, selected_donor, "")
    result["webscout_frozen_donor_target_month_commit_count"] = 0

    for month in target_months:
        month_mask = target_mask & result["time"].eq(month)
        donor_count = int(selected_counts[month])
        result.loc[month_mask, SUBSTITUTED_METHOD_INCREMENT] = donor_count
        result.loc[month_mask, SUBSTITUTED_OVERLAP] = 0

    result[SUBSTITUTION_OUTCOME] = (
        result[ORIGINAL_HYBRID_OUTCOME]
        - result[ORIGINAL_METHOD_INCREMENT]
        + result[ORIGINAL_OVERLAP]
        + result[SUBSTITUTED_METHOD_INCREMENT]
        - result[SUBSTITUTED_OVERLAP]
    ).astype("int64")
    result[SUBSTITUTION_LOG_OUTCOME] = np.log1p(result[SUBSTITUTION_OUTCOME])
    result[SUBSTITUTION_OCCURRENCE] = result[SUBSTITUTION_OUTCOME].gt(0).astype("int8")
    result[SUBSTITUTION_ZERO] = result[SUBSTITUTION_OUTCOME].eq(0).astype("int8")
    result[SUBSTITUTION_READY_PAPER] = result[HYBRID_READY_PAPER].astype("int8")
    result[SUBSTITUTION_READY_PYTHON] = result[HYBRID_READY_PYTHON].astype("int8")
    result["webscout_frozen_donor_substitution_rule"] = np.where(
        target_mask,
        "replace_webscout_target_month_classmethod_increment_with_frozen_donor_increment",
        "no_change",
    )
    result["webscout_frozen_donor_selection_locked_before_outcome"] = True
    result["sample_membership_unchanged_by_donor_substitution"] = True
    result["causal_interpretation_allowed"] = False

    month_audit_columns = [
        "dataset_source",
        "repo_name",
        "time",
        ORIGINAL_MODULE_OUTCOME,
        ORIGINAL_METHOD_INCREMENT,
        ORIGINAL_OVERLAP,
        ORIGINAL_HYBRID_OUTCOME,
        SUBSTITUTED_METHOD_INCREMENT,
        SUBSTITUTED_OVERLAP,
        SUBSTITUTION_OUTCOME,
        "webscout_frozen_donor_repo",
        SUBSTITUTION_APPLIED,
    ]
    month_audit = result.loc[target_mask, month_audit_columns].copy()
    month_audit["removed_net_method_bodies"] = (
        month_audit[ORIGINAL_HYBRID_OUTCOME] - month_audit[SUBSTITUTION_OUTCOME]
    )
    month_audit["equivalent_to_zero_method_increment_ablation"] = (
        month_audit[SUBSTITUTED_METHOD_INCREMENT].eq(0)
        & month_audit[SUBSTITUTED_OVERLAP].eq(0)
        & month_audit[SUBSTITUTION_OUTCOME].eq(month_audit[ORIGINAL_MODULE_OUTCOME])
    )
    return result, month_audit.sort_values("time").reset_index(drop=True)


def build_validation(
    freeze: pd.DataFrame,
    commit_activity: pd.DataFrame,
    donor_outcome: pd.DataFrame,
    original_panel: pd.DataFrame,
    substitution_panel: pd.DataFrame,
    month_audit: pd.DataFrame,
    selected_donor: str,
    target_control: str,
    target_months: list[str],
    expected_increments: dict[str, int],
    args: argparse.Namespace,
) -> pd.DataFrame:
    checks: list[dict[str, object]] = []
    selected_outcomes = donor_outcome[donor_outcome["repo_name"].eq(selected_donor)]
    non_target_mask = ~(
        original_panel["repo_name"].eq(normalize_repo(target_control))
        & original_panel["time"].isin(target_months)
    )

    add_check(
        checks,
        "donor_frozen_before_outcome_review",
        freeze["frozen_before_post_adoption_outcome_review"].map(bool_value).all(),
        True,
        True,
        "The donor choice must precede AGC outcome inspection.",
    )
    add_check(
        checks,
        "selected_donor_commit_counts_zero_in_all_target_months",
        bool((selected_outcomes["month_commit_count"] == 0).all()),
        ",".join(selected_outcomes["month_commit_count"].astype(str)),
        "0,0",
        "The selected donor was audited as inactive in both target months.",
    )
    add_check(
        checks,
        "selected_donor_has_zero_function_events_in_zero_commit_months",
        bool((selected_outcomes["all_function_event_rows"] == 0).all()),
        ",".join(selected_outcomes["all_function_event_rows"].astype(str)),
        "0,0",
        "Zero-commit months must not contain extracted function events.",
    )
    add_check(
        checks,
        "selected_donor_has_zero_method_agc_unique_bodies",
        bool((selected_outcomes["method_agc_unique_bodies"] == 0).all()),
        ",".join(selected_outcomes["method_agc_unique_bodies"].astype(str)),
        "0,0",
        "The frozen selected donor must contribute zero target-month method increments.",
    )
    add_check(
        checks,
        "all_frozen_donor_zero_commit_zero_event_consistency",
        bool(donor_outcome["zero_commit_zero_event_consistent"].all()),
        int((~donor_outcome["zero_commit_zero_event_consistent"]).sum()),
        0,
        "Every frozen donor zero-commit month must contain zero function events.",
    )
    add_check(
        checks,
        "all_frozen_donor_zero_commit_zero_method_agc_consistency",
        bool(donor_outcome["zero_commit_zero_method_agc_consistent"].all()),
        int((~donor_outcome["zero_commit_zero_method_agc_consistent"]).sum()),
        0,
        "Every frozen donor zero-commit month must contain zero method AGC bodies.",
    )
    add_check(
        checks,
        "donor_event_aggregation_matches_run_py_7j",
        bool(donor_outcome["event_count_matches_run_py_7j_method_count"].all()),
        int((~donor_outcome["event_count_matches_run_py_7j_method_count"]).sum()),
        0,
        "Independent event aggregation must reproduce run-py-7j method counts.",
    )
    add_check(
        checks,
        "webscout_panel_counts_match_run_py_7j",
        bool(
            month_audit[ORIGINAL_METHOD_INCREMENT].eq(
                month_audit["run_py_7j_webscout_method_agc_unique_bodies"]
            ).all()
            and month_audit[ORIGINAL_OVERLAP].eq(
                month_audit["run_py_7j_webscout_module_method_overlap"]
            ).all()
        ),
        int(
            (~month_audit[ORIGINAL_METHOD_INCREMENT].eq(
                month_audit["run_py_7j_webscout_method_agc_unique_bodies"]
            )).sum()
            + (~month_audit[ORIGINAL_OVERLAP].eq(
                month_audit["run_py_7j_webscout_module_method_overlap"]
            )).sum()
        ),
        0,
        "The run-py-7n Webscout counts must reproduce run-py-7j repository-month counts.",
    )
    observed_increments = month_audit.set_index("time")[ORIGINAL_METHOD_INCREMENT].to_dict()
    add_check(
        checks,
        "webscout_target_month_method_increments_match_frozen_values",
        all(int(observed_increments.get(month, -1)) == expected_increments[month] for month in target_months),
        ";".join(f"{month}={observed_increments.get(month)}" for month in target_months),
        ";".join(f"{month}={expected_increments[month]}" for month in target_months),
        "The original Webscout target-month increments must match prior diagnostics.",
    )
    add_check(
        checks,
        "webscout_target_month_cross_kind_overlap_zero",
        bool((month_audit[ORIGINAL_OVERLAP] == 0).all()),
        ",".join(month_audit[ORIGINAL_OVERLAP].astype(str)),
        "0,0",
        "Frozen arithmetic assumes no original module-method body overlap in target months.",
    )
    add_check(
        checks,
        "substitution_rows_retained",
        set(month_audit["time"]) == set(target_months),
        ",".join(sorted(month_audit["time"])),
        ",".join(sorted(target_months)),
        "Substitution changes values, not repository-month membership.",
    )
    add_check(
        checks,
        "substitution_equivalent_to_zero_increment_ablation",
        bool(month_audit["equivalent_to_zero_method_increment_ablation"].all()),
        int((~month_audit["equivalent_to_zero_method_increment_ablation"]).sum()),
        0,
        "A frozen donor with zero target-month method increments is numerically equivalent to target-month method ablation.",
    )
    original_columns = list(original_panel.columns)
    non_target_equal = original_panel.loc[non_target_mask, original_columns].reset_index(drop=True).equals(
        substitution_panel.loc[non_target_mask, original_columns].reset_index(drop=True)
    )
    add_check(
        checks,
        "all_original_columns_unchanged_outside_target_rows",
        non_target_equal,
        non_target_equal,
        True,
        "Only the new substitution-specific columns may differ outside target rows.",
    )
    add_check(
        checks,
        "sample_keys_unchanged",
        original_panel[KEY_COLUMNS].equals(substitution_panel[KEY_COLUMNS]),
        len(substitution_panel),
        len(original_panel),
        "The fixed original-positive sample must remain unchanged.",
    )
    add_check(
        checks,
        "source_panel_membership_is_frozen_to_run_py_7h",
        original_panel["sample_membership_fixed_to_run_py_7h"].map(bool_value).all(),
        int(
            (~original_panel["sample_membership_fixed_to_run_py_7h"].map(bool_value)).sum()
        ),
        0,
        "Every source row must come from the run-py-7n fixed sample.",
    )
    add_check(
        checks,
        "substitution_outcome_nonnegative_integer",
        bool(
            substitution_panel[SUBSTITUTION_OUTCOME].ge(0).all()
            and np.allclose(
                substitution_panel[SUBSTITUTION_OUTCOME],
                np.floor(substitution_panel[SUBSTITUTION_OUTCOME]),
            )
        ),
        int((substitution_panel[SUBSTITUTION_OUTCOME] < 0).sum()),
        0,
        "The prepared outcome must be a nonnegative integer count.",
    )
    add_check(
        checks,
        "causal_interpretation_disallowed",
        not substitution_panel["causal_interpretation_allowed"].map(bool_value).any(),
        False,
        False,
        "This is a noncausal supplementary month-substitution sensitivity.",
    )
    add_check(
        checks,
        "did_not_run",
        True,
        "Data preparation only",
        "No DiD model",
        "The next step must estimate the model separately.",
    )

    if not args.skip_frozen_count_checks:
        original_total = int(original_panel[ORIGINAL_HYBRID_OUTCOME].sum())
        substitution_total = int(substitution_panel[SUBSTITUTION_OUTCOME].sum())
        removed = original_total - substitution_total
        frozen = [
            (
                "fixed_sample_rows_match_frozen",
                len(original_panel),
                args.expected_fixed_sample_rows,
            ),
            (
                "fixed_sample_repositories_match_frozen",
                original_panel["repo_name"].nunique(),
                args.expected_fixed_sample_repositories,
            ),
            (
                "original_hybrid_total_matches_frozen",
                original_total,
                args.expected_original_hybrid_total,
            ),
            (
                "removed_net_bodies_match_frozen",
                removed,
                args.expected_removed_net_bodies,
            ),
            (
                "substitution_total_matches_frozen",
                substitution_total,
                args.expected_substitution_total,
            ),
        ]
        for name, observed, expected in frozen:
            add_check(
                checks,
                name,
                int(observed) == int(expected),
                int(observed),
                int(expected),
                "Frozen range100_200 fixed-sample arithmetic.",
            )

    return pd.DataFrame(checks)


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "donor_outcomes": output_dir / f"{OUTPUT_PREFIX}_target_month_outcomes.csv",
        "substitution_panel": output_dir
        / "panel_event_monthly_regfun_selected_classmethod_agc_uniquebody_"
        "webscout_frozen_donor_substitution_original_positive_sample_parse_clean.csv",
        "month_audit": output_dir / f"{OUTPUT_PREFIX}_month_audit.csv",
        "equivalence": output_dir / f"{OUTPUT_PREFIX}_ablation_equivalence.csv",
        "validation": output_dir / f"{OUTPUT_PREFIX}_validation.csv",
        "provenance": output_dir / f"{OUTPUT_PREFIX}_provenance.csv",
        "summary": output_dir / f"{OUTPUT_PREFIX}_summary.json",
        "status": output_dir / f"{OUTPUT_PREFIX}_status.txt",
    }


def run_analysis(args: argparse.Namespace) -> dict[str, Any]:
    freeze_path = require_file(args.freeze_manifest, "Freeze manifest")
    commit_path = require_file(args.commit_activity, "Commit activity audit")
    events_path = require_file(args.event_classifications, "Event classifications")
    counts_path = require_file(args.repo_month_counts, "run-py-7j repository-month counts")
    panel_path = require_file(args.fixed_sample_panel, "run-py-7n fixed-sample panel")
    if args.output_dir is None:
        raise AnalysisError("Output directory is required.")

    target_months = [normalize_month(value) for value in (args.target_month or TARGET_MONTHS_DEFAULT)]
    if len(set(target_months)) != len(target_months):
        raise AnalysisError("Target months must be unique.")
    expected_increments = parse_expected_increment(
        args.expected_webscout_method_increment, target_months
    )

    prepare_output_directory(args.output_dir, args.overwrite_output)
    paths = output_paths(args.output_dir)

    freeze, selected_donor, fallback_donor, ranking_hash = load_frozen_donors(
        freeze_path,
        args.expected_selected_donor,
        args.expected_fallback_donor,
    )
    commit_activity = load_commit_activity(
        commit_path,
        {selected_donor, fallback_donor},
        set(target_months),
    )
    events = pd.read_csv(events_path, low_memory=False)
    donor_outcomes = build_donor_outcome_audit(
        events,
        commit_activity,
        [selected_donor, fallback_donor],
        target_months,
        selected_donor,
    )
    repo_month_counts = load_repo_month_counts(counts_path)
    donor_outcomes = add_repo_month_crosscheck(donor_outcomes, repo_month_counts)

    original_panel = load_fixed_panel(panel_path)
    substitution_panel, month_audit = build_substitution_panel(
        original_panel,
        donor_outcomes,
        selected_donor,
        args.target_control,
        target_months,
    )
    webscout_lookup = repo_month_counts.loc[
        repo_month_counts["repo_name"].eq(normalize_repo(args.target_control))
        & repo_month_counts["time"].isin(target_months),
        ["time", REPO_MONTH_METHOD_COUNT, REPO_MONTH_OVERLAP_COUNT],
    ].rename(
        columns={
            REPO_MONTH_METHOD_COUNT: "run_py_7j_webscout_method_agc_unique_bodies",
            REPO_MONTH_OVERLAP_COUNT: "run_py_7j_webscout_module_method_overlap",
        }
    )
    month_audit = month_audit.merge(
        webscout_lookup,
        on="time",
        how="left",
        validate="one_to_one",
    )
    month_audit["run_py_7j_webscout_method_agc_unique_bodies"] = (
        month_audit["run_py_7j_webscout_method_agc_unique_bodies"]
        .fillna(0)
        .astype("int64")
    )
    month_audit["run_py_7j_webscout_module_method_overlap"] = (
        month_audit["run_py_7j_webscout_module_method_overlap"]
        .fillna(0)
        .astype("int64")
    )
    validation = build_validation(
        freeze,
        commit_activity,
        donor_outcomes,
        original_panel,
        substitution_panel,
        month_audit,
        selected_donor,
        args.target_control,
        target_months,
        expected_increments,
        args,
    )
    failed = validation[~validation["passed"].map(bool_value)]

    equivalence = month_audit[
        [
            "repo_name",
            "time",
            ORIGINAL_MODULE_OUTCOME,
            ORIGINAL_METHOD_INCREMENT,
            ORIGINAL_OVERLAP,
            ORIGINAL_HYBRID_OUTCOME,
            SUBSTITUTED_METHOD_INCREMENT,
            SUBSTITUTED_OVERLAP,
            SUBSTITUTION_OUTCOME,
            "removed_net_method_bodies",
            "equivalent_to_zero_method_increment_ablation",
        ]
    ].copy()
    equivalence["comparison_scenario"] = "webscout_without_2025_04_and_2025_06"
    equivalence["interpretation"] = (
        "frozen_pre_adoption_donor_has_zero_target_month_method_increment"
    )

    provenance = pd.DataFrame(
        [
            {
                "script_version": SCRIPT_VERSION,
                "analysis_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "freeze_manifest": str(freeze_path),
                "freeze_manifest_sha256": sha256_file(freeze_path),
                "commit_activity": str(commit_path),
                "commit_activity_sha256": sha256_file(commit_path),
                "event_classifications": str(events_path),
                "event_classifications_sha256": sha256_file(events_path),
                "repo_month_counts": str(counts_path),
                "repo_month_counts_sha256": sha256_file(counts_path),
                "fixed_sample_panel": str(panel_path),
                "fixed_sample_panel_sha256": sha256_file(panel_path),
                "ranking_sha256": ranking_hash,
                "selected_donor": selected_donor,
                "fallback_donor": fallback_donor,
                "target_control": normalize_repo(args.target_control),
                "target_months": ",".join(target_months),
                "donor_selection_changed_after_outcome_review": False,
                "post_adoption_agc_outcome_read": True,
                "did_executed": False,
                "causal_interpretation_allowed": False,
            }
        ]
    )

    atomic_write_csv(donor_outcomes, paths["donor_outcomes"])
    atomic_write_csv(substitution_panel, paths["substitution_panel"])
    atomic_write_csv(month_audit, paths["month_audit"])
    atomic_write_csv(equivalence, paths["equivalence"])
    atomic_write_csv(validation, paths["validation"])
    atomic_write_csv(provenance, paths["provenance"])

    original_total = int(original_panel[ORIGINAL_HYBRID_OUTCOME].sum())
    substitution_total = int(substitution_panel[SUBSTITUTION_OUTCOME].sum())
    selected_outcome_rows = donor_outcomes[
        donor_outcomes["repo_name"].eq(selected_donor)
    ]
    summary = {
        "status": "PASS" if failed.empty else "FAIL",
        "script_version": SCRIPT_VERSION,
        "analysis": "frozen donor AGC extraction and Webscout target-month substitution panel preparation",
        "interpretation": "noncausal supplementary fixed-sample donor month-substitution sensitivity",
        "selected_donor": selected_donor,
        "fallback_donor": fallback_donor,
        "target_control": normalize_repo(args.target_control),
        "target_months": target_months,
        "selection_locked_before_outcome_review": True,
        "selected_donor_method_agc_unique_bodies": {
            row.target_month: int(row.method_agc_unique_bodies)
            for row in selected_outcome_rows.itertuples()
        },
        "fixed_sample_rows": int(len(original_panel)),
        "fixed_sample_repositories": int(original_panel["repo_name"].nunique()),
        "original_hybrid_total": original_total,
        "substitution_outcome_total": substitution_total,
        "removed_net_bodies": original_total - substitution_total,
        "substitution_equivalent_to_target_month_ablation": bool(
            equivalence["equivalent_to_zero_method_increment_ablation"].all()
        ),
        "post_adoption_agc_outcome_read": True,
        "did_ran": False,
        "causal_interpretation_allowed": False,
        "failed_checks": int(len(failed)),
        "input_hashes": {
            "freeze_manifest": sha256_file(freeze_path),
            "commit_activity": sha256_file(commit_path),
            "event_classifications": sha256_file(events_path),
            "repo_month_counts": sha256_file(counts_path),
            "fixed_sample_panel": sha256_file(panel_path),
            "ranking": ranking_hash,
        },
        "outputs": {name: str(path) for name, path in paths.items()},
        "next_step": (
            "Run a separate static Borusyak DiD comparison using the frozen donor substitution outcome."
            if failed.empty
            else "Stop and resolve validation failures before any DiD estimation."
        ),
    }
    atomic_write_json(summary, paths["summary"])

    status_lines = [
        "PASS" if failed.empty else "FAIL",
        f"script_version={SCRIPT_VERSION}",
        f"selected_donor={selected_donor}",
        f"fallback_donor={fallback_donor}",
        f"target_control={normalize_repo(args.target_control)}",
        f"target_months={','.join(target_months)}",
        "donor_selection_locked_before_outcome_review=TRUE",
        "post_adoption_agc_outcome_read=TRUE",
        "did_executed=FALSE",
        "sample_membership_unchanged=TRUE",
        f"substitution_equivalent_to_target_month_ablation={str(bool(equivalence['equivalent_to_zero_method_increment_ablation'].all())).upper()}",
        "causal_interpretation_allowed=FALSE",
        f"failed_checks={len(failed)}",
    ]
    paths["status"].write_text("\n".join(status_lines) + "\n", encoding="utf-8")

    print("=" * 80)
    print("run-py-8g: frozen donor AGC extraction and substitution panel")
    print("=" * 80)
    print(f"Status:                              {summary['status']}")
    print(f"Selected donor:                      {selected_donor}")
    print(f"Fallback donor:                      {fallback_donor}")
    print(f"Target control:                      {normalize_repo(args.target_control)}")
    print(f"Target months:                       {', '.join(target_months)}")
    print("Selected donor method AGC outcomes:")
    print(
        selected_outcome_rows[
            [
                "target_month",
                "month_commit_count",
                "all_function_event_rows",
                "method_agc_unique_bodies",
            ]
        ].to_string(index=False)
    )
    print(f"Original hybrid total:               {original_total}")
    print(f"Substitution outcome total:          {substitution_total}")
    print(f"Removed net bodies:                  {original_total - substitution_total}")
    print(
        "Equivalent to 2025-04/06 ablation:  "
        f"{bool(equivalence['equivalent_to_zero_method_increment_ablation'].all())}"
    )
    print(f"Post-adoption AGC outcomes inspected: YES")
    print(f"DiD executed:                        NO")
    print(f"Failed checks:                       {len(failed)}")
    print(f"Output directory:                    {args.output_dir}")
    print("=" * 80)

    if not failed.empty:
        raise AnalysisError(
            "run-py-8g validation failed:\n" + failed.to_string(index=False)
        )
    return summary


def build_synthetic_inputs(root: Path) -> dict[str, Path]:
    freeze = pd.DataFrame(
        [
            {
                "freeze_role": "selected",
                "candidate_control_repo": "example/SelectedDonor",
                "ranking_sha256": "abc123",
                "frozen_before_post_adoption_outcome_review": True,
                "post_adoption_agc_outcome_read": False,
                "did_executed": False,
            },
            {
                "freeze_role": "fallback",
                "candidate_control_repo": "example/FallbackDonor",
                "ranking_sha256": "abc123",
                "frozen_before_post_adoption_outcome_review": True,
                "post_adoption_agc_outcome_read": False,
                "did_executed": False,
            },
        ]
    )
    commit_rows = []
    for repo in ["example/SelectedDonor", "example/FallbackDonor"]:
        for month in TARGET_MONTHS_DEFAULT:
            commit_rows.append(
                {
                    "repo_name": repo,
                    "target_month": month,
                    "month_commit_count": 0,
                    "month_has_commit": False,
                    "activity_status": "inactive_target_month_snapshot_carry_forward",
                    "agc_outcome_read": False,
                    "did_executed": False,
                }
            )
    events = pd.DataFrame(
        [
            {
                "dataset_source": "control",
                "repo_name": "example/SelectedDonor",
                "time": "2025-03",
                "function_event_id": "outside-target",
                BODY_COLUMN: "sha-outside",
                FUNCTION_KIND_COLUMN: "method",
                AGC_COLUMN: 1,
                HWC_COLUMN: 0,
            }
        ]
    )
    counts = pd.DataFrame(
        [
            {
                "dataset_source": "control",
                "repo_name": "HelpingAI/Webscout",
                "time": "2025-04",
                REPO_MONTH_METHOD_COUNT: 18,
                REPO_MONTH_OVERLAP_COUNT: 0,
            },
            {
                "dataset_source": "control",
                "repo_name": "HelpingAI/Webscout",
                "time": "2025-06",
                REPO_MONTH_METHOD_COUNT: 30,
                REPO_MONTH_OVERLAP_COUNT: 0,
            },
        ]
    )
    panel_rows = []
    for month, module_count, method_count in [
        ("2025-04", 3, 18),
        ("2025-06", 11, 30),
    ]:
        panel_rows.append(
            {
                "dataset_source": "control",
                "repo_name": "HelpingAI/Webscout",
                "time": month,
                ORIGINAL_MODULE_OUTCOME: module_count,
                ORIGINAL_METHOD_INCREMENT: method_count,
                ORIGINAL_OVERLAP: 0,
                ORIGINAL_HYBRID_OUTCOME: module_count + method_count,
                HYBRID_READY_PAPER: 1,
                HYBRID_READY_PYTHON: 1,
                "sample_membership_fixed_to_run_py_7h": True,
                "causal_interpretation_allowed": False,
            }
        )
    panel_rows.append(
        {
            "dataset_source": "treatment",
            "repo_name": "example/Treatment",
            "time": "2025-04",
            ORIGINAL_MODULE_OUTCOME: 2,
            ORIGINAL_METHOD_INCREMENT: 4,
            ORIGINAL_OVERLAP: 0,
            ORIGINAL_HYBRID_OUTCOME: 6,
            HYBRID_READY_PAPER: 1,
            HYBRID_READY_PYTHON: 1,
            "sample_membership_fixed_to_run_py_7h": True,
            "causal_interpretation_allowed": False,
        }
    )

    paths = {
        "freeze": root / "freeze.csv",
        "commit": root / "commit.csv",
        "events": root / "events.csv",
        "counts": root / "counts.csv",
        "panel": root / "panel.csv",
    }
    freeze.to_csv(paths["freeze"], index=False)
    pd.DataFrame(commit_rows).to_csv(paths["commit"], index=False)
    events.to_csv(paths["events"], index=False)
    counts.to_csv(paths["counts"], index=False)
    pd.DataFrame(panel_rows).to_csv(paths["panel"], index=False)
    return paths


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="run-py-8g-self-test-") as temporary:
        root = Path(temporary)
        inputs = build_synthetic_inputs(root)
        args = argparse.Namespace(
            freeze_manifest=inputs["freeze"],
            commit_activity=inputs["commit"],
            event_classifications=inputs["events"],
            repo_month_counts=inputs["counts"],
            fixed_sample_panel=inputs["panel"],
            output_dir=root / "output",
            expected_selected_donor="example/SelectedDonor",
            expected_fallback_donor="example/FallbackDonor",
            target_control="HelpingAI/Webscout",
            target_month=list(TARGET_MONTHS_DEFAULT),
            expected_webscout_method_increment=["2025-04=18", "2025-06=30"],
            expected_fixed_sample_rows=3,
            expected_fixed_sample_repositories=2,
            expected_original_hybrid_total=68,
            expected_removed_net_bodies=48,
            expected_substitution_total=20,
            skip_frozen_count_checks=False,
            overwrite_output=True,
            self_test=False,
        )
        summary = run_analysis(args)
        if summary["status"] != "PASS":
            raise AnalysisError("Synthetic self-test did not PASS.")
        panel = pd.read_csv(output_paths(args.output_dir)["substitution_panel"])
        web = panel[panel["repo_name"].eq("HelpingAI/Webscout")]
        if web[SUBSTITUTION_OUTCOME].tolist() != [3, 11]:
            raise AnalysisError("Synthetic substitution outcome arithmetic failed.")
    print("Self-test: PASS")


def main() -> int:
    args = parse_args()
    try:
        if args.self_test:
            run_self_test()
            return 0
        run_analysis(args)
        return 0
    except Exception as error:  # noqa: BLE001
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
