#!/usr/bin/env python3
"""Build the run-x-d07 ML-threshold x SonarQube quality burden panel.

This script is the ML counterpart of the existing NPR threshold-panel
preparation stage. It does not estimate a treatment effect. It combines the
validated A04 continuous file-level ML AGC share with the canonical D02
file-level SonarQube burden and the B06 repo-month panel, then materializes a
zero-inclusive threshold x sample x repo-month panel for downstream run-x-d08.

Scientific contract
-------------------
- ML file metric: file_ml_agc_share_space_by_token_weighted
- File selection: finite ML share > threshold
- Threshold grid: 0.10, 0.14, ..., 0.50, ..., 0.86, 0.90 (21 cutoffs)
- Primary cutoff: strict > 0.50
- Function-level ML classifier boundary is unchanged
- Missing/non-finite ML shares remain unclassified and are never selected
- Mapping scope is fixed to all_ml_files for this threshold-sensitivity lineage
- Samples: full_sample and exclude_scope_mismatch_repos
- Primary 0.50 burden must exactly reproduce D05 for both samples
- Density is not computed because selected-file SonarQube NCLOC is unavailable

Primary output
--------------
quality_ml_threshold_repo_month_panel.csv.gz

The downstream key is:
    sample_spec + threshold_spec_id + repo_id + time_index
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

IMPLEMENTATION_VERSION = "v1"
EXPERIMENT_NAME = "run-x-d07-build-ml-threshold-quality-burden-panel"
ML_METRIC = "file_ml_agc_share_space_by_token_weighted"
PRIMARY_THRESHOLD = 0.50
STRICT_OPERATOR = ">"
MAPPING_SPEC = "all_ml_files"
DEFAULT_THRESHOLDS = tuple(round(0.10 + 0.04 * i, 2) for i in range(21))
FILE_KEYS = ("snapshot_id", "relative_path", "file_sha256")
REPO_TIME_KEYS = ("repo_id", "time_index")
JOIN_SHA_COLUMN = "_file_sha256_join"
JOIN_FILE_KEYS = ("snapshot_id", "relative_path", JOIN_SHA_COLUMN)
MISSING_SHA_SENTINEL = "__MISSING_FILE_SHA256__"

# Output name -> accepted D02 source column names.
BURDEN_SOURCES = {
    "selected_issue_total": ("sonar_issue_total", "issue_total"),
    "selected_issue_code_smell": ("sonar_issue_code_smell", "issue_code_smell", "code_smell"),
    "selected_issue_bug": ("sonar_issue_bug", "issue_bug", "bug"),
    "selected_issue_vulnerability": ("sonar_issue_vulnerability", "issue_vulnerability", "vulnerability"),
    "selected_issue_high_severity": ("sonar_issue_high_severity", "issue_high_severity", "high_severity"),
    "selected_issue_maintainability_impact": (
        "sonar_issue_maintainability_impact", "issue_maintainability_impact", "maintainability_impact"
    ),
    "selected_issue_reliability_impact": (
        "sonar_issue_reliability_impact", "issue_reliability_impact", "reliability_impact"
    ),
    "selected_issue_security_impact": (
        "sonar_issue_security_impact", "issue_security_impact", "security_impact"
    ),
}


def abort(message: str) -> None:
    raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_table(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def require_columns(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        abort(f"{label} is missing required columns: {missing}")


def normalize_repo_time_keys(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    out = frame.copy()
    require_columns(out, REPO_TIME_KEYS, label)
    out["repo_id"] = pd.to_numeric(out["repo_id"], errors="raise").astype(int)
    out["time_index"] = pd.to_numeric(out["time_index"], errors="raise").astype(int)
    if out[list(REPO_TIME_KEYS)].isna().any().any():
        abort(f"{label} contains missing repo_id/time_index")
    return out


def normalize_file_keys(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    out = frame.copy()
    require_columns(out, FILE_KEYS, label)
    for column in ("snapshot_id", "relative_path"):
        if out[column].isna().any():
            abort(f"{label} contains missing {column}")
        out[column] = out[column].astype(str)
    sha = out["file_sha256"].astype("string").str.strip()
    sha = sha.mask(sha.isna() | sha.eq(""), pd.NA)
    out["file_sha256"] = sha
    out[JOIN_SHA_COLUMN] = sha.fillna(MISSING_SHA_SENTINEL).astype(str)
    return out


def audit_missing_sha_identity(a04: pd.DataFrame, unique_d02: pd.DataFrame) -> dict[str, int]:
    a04_missing = a04.loc[a04["file_sha256"].isna(), ["snapshot_id", "relative_path"]].copy()
    d02_missing = unique_d02.loc[
        unique_d02["file_sha256"].isna(), ["snapshot_id", "relative_path"]
    ].copy()
    if a04_missing.duplicated(["snapshot_id", "relative_path"]).any():
        abort("A04 missing-SHA rows are not unique by snapshot_id + relative_path")
    if d02_missing.duplicated(["snapshot_id", "relative_path"]).any():
        abort("D02 missing-SHA rows are not unique by snapshot_id + relative_path")
    comparison = d02_missing.merge(
        a04_missing,
        on=["snapshot_id", "relative_path"],
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    return {
        "a04_missing_sha_files": int(len(a04_missing)),
        "d02_missing_sha_files": int(len(d02_missing)),
        "d02_only_missing_sha_keys": int((comparison["_merge"] == "left_only").sum()),
        "a04_only_missing_sha_keys": int((comparison["_merge"] == "right_only").sum()),
    }


def resolve_burden_columns(d02: pd.DataFrame) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for output_column, candidates in BURDEN_SOURCES.items():
        found = next((candidate for candidate in candidates if candidate in d02.columns), None)
        if found is None:
            abort(
                f"D02 cannot provide {output_column}; expected one of {list(candidates)}. "
                f"Available columns include: {list(d02.columns)}"
            )
        resolved[output_column] = found
    return resolved


def threshold_spec_id(value: float) -> str:
    return f"ml_t{int(round(value * 100)):02d}"


def parse_thresholds(text: str) -> list[float]:
    values = sorted(float(token.strip()) for token in text.split(",") if token.strip())
    if len(values) != len(set(values)):
        abort("Threshold values must be unique")
    expected = list(DEFAULT_THRESHOLDS)
    if len(values) != len(expected) or any(
        not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12)
        for left, right in zip(values, expected)
    ):
        abort(f"D07 requires exact 21-point grid {expected}; observed {values}")
    return values


def extract_d05_mapping_reference(d05: pd.DataFrame) -> pd.DataFrame:
    require_columns(d05, ["sample_spec", "mapping_spec", "repo_id", "time_index"], "D05")
    ref = d05.loc[d05["mapping_spec"].astype(str).eq(MAPPING_SPEC)].copy()
    if ref.empty:
        abort("D05 all_ml_files mapping reference is empty")
    ref = normalize_repo_time_keys(ref, "D05 all_ml_files reference")
    if ref.duplicated(["sample_spec", "repo_id", "time_index"]).any():
        abort("D05 all_ml_files reference has duplicate sample/repo-month keys")
    return ref


def resolve_d05_file_count_column(d05: pd.DataFrame) -> str:
    for column in ("selected_file_rows", "selected_file_count"):
        if column in d05.columns:
            return column
    abort("D05 reference is missing selected_file_rows/selected_file_count")
    raise AssertionError


def derive_sample_specs(d05_ref: pd.DataFrame, b06: pd.DataFrame) -> tuple[dict[str, set[int]], list[int]]:
    required_samples = {"full_sample", "exclude_scope_mismatch_repos"}
    observed = set(d05_ref["sample_spec"].astype(str).unique())
    if not required_samples.issubset(observed):
        abort(f"D05 reference lacks required sample specs: {sorted(required_samples - observed)}")

    full_ids = set(d05_ref.loc[d05_ref["sample_spec"].eq("full_sample"), "repo_id"].astype(int).unique())
    sensitivity_ids = set(
        d05_ref.loc[d05_ref["sample_spec"].eq("exclude_scope_mismatch_repos"), "repo_id"].astype(int).unique()
    )
    b06_ids = set(b06["repo_id"].astype(int).unique())
    if full_ids != b06_ids:
        abort(f"D05 full-sample repository set differs from B06: D05={len(full_ids)}, B06={len(b06_ids)}")
    if not sensitivity_ids.issubset(full_ids):
        abort("D05 sensitivity repository set is not a subset of the full sample")
    excluded = sorted(full_ids - sensitivity_ids)
    return {
        "full_sample": full_ids,
        "exclude_scope_mismatch_repos": sensitivity_ids,
    }, excluded


def add_log_outcomes(panel: pd.DataFrame) -> None:
    for output_column in BURDEN_SOURCES:
        panel[f"log1p_{output_column}"] = np.log1p(panel[output_column].astype(float))


def treatment_counts(panel: pd.DataFrame) -> dict[str, int]:
    require_columns(panel, ["treatment_group", "event_index"], "B06 sample")
    treatment = pd.to_numeric(panel["treatment_group"], errors="raise").astype(int)
    event_index = pd.to_numeric(panel["event_index"], errors="raise").astype(int)
    time_index = pd.to_numeric(panel["time_index"], errors="raise").astype(int)
    control = treatment.eq(0)
    treated = treatment.eq(1)
    pre = treated & time_index.lt(event_index)
    post = treated & time_index.ge(event_index)
    dynamic = treated & (time_index - event_index).between(0, 6)
    return {
        "repo_month_rows": int(len(panel)),
        "repositories": int(panel["repo_id"].nunique()),
        "control_repositories": int(panel.loc[control, "repo_id"].nunique()),
        "treatment_repositories": int(panel.loc[treated, "repo_id"].nunique()),
        "control_rows": int(control.sum()),
        "treatment_pre_rows": int(pre.sum()),
        "treatment_post_rows": int(post.sum()),
        "untreated_first_stage_rows": int((control | pre).sum()),
        "dynamic_event_0_to_6_rows": int(dynamic.sum()),
    }


def compare_primary_to_d05(
    primary_panels: dict[str, pd.DataFrame],
    d05_ref: pd.DataFrame,
    d05_file_count_column: str,
) -> pd.DataFrame:
    audit_rows: list[dict[str, object]] = []
    comparison_columns = ["selected_file_count", *BURDEN_SOURCES.keys()]
    for sample_spec, panel in primary_panels.items():
        reference = d05_ref.loc[d05_ref["sample_spec"].eq(sample_spec)].copy()
        reference = reference.rename(columns={d05_file_count_column: "selected_file_count"})
        required_ref = ["repo_id", "time_index", "selected_file_count", *BURDEN_SOURCES.keys()]
        require_columns(reference, required_ref, f"D05 {sample_spec} reference")
        merged = reference[required_ref].merge(
            panel[["repo_id", "time_index", *comparison_columns]],
            on=["repo_id", "time_index"],
            how="outer",
            suffixes=("_reference", "_new"),
            indicator=True,
            validate="one_to_one",
        )
        key_mismatches = int((merged["_merge"] != "both").sum())
        audit_rows.append({
            "sample_spec": sample_spec,
            "metric": "repo_month_keys",
            "mismatches": key_mismatches,
            "status": "pass" if key_mismatches == 0 else "fail",
        })
        for metric in comparison_columns:
            left = pd.to_numeric(merged[f"{metric}_reference"], errors="coerce")
            right = pd.to_numeric(merged[f"{metric}_new"], errors="coerce")
            tolerance = 0.0 if metric == "selected_file_count" else 1e-9
            mismatches = int((~np.isclose(left, right, atol=tolerance, rtol=0, equal_nan=False)).sum())
            audit_rows.append({
                "sample_spec": sample_spec,
                "metric": metric,
                "mismatches": mismatches,
                "status": "pass" if mismatches == 0 else "fail",
            })
    audit = pd.DataFrame(audit_rows)
    if audit["status"].ne("pass").any():
        abort("D05 primary >0.50 reproduction failed; inspect reproduction audit")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a04-file", required=True, type=Path)
    parser.add_argument("--d02-file", required=True, type=Path)
    parser.add_argument("--b06-file", required=True, type=Path)
    parser.add_argument("--d05-reference-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--thresholds", default=",".join(f"{v:.2f}" for v in DEFAULT_THRESHOLDS))
    parser.add_argument("--expected-a04-rows", type=int, default=494592)
    parser.add_argument("--expected-d02-rows", type=int, default=510297)
    parser.add_argument("--expected-d02-unique-files", type=int, default=494592)
    parser.add_argument("--expected-b06-rows", type=int, default=1954)
    parser.add_argument("--expected-b06-repositories", type=int, default=167)
    parser.add_argument("--expected-treatment-repositories", type=int, default=63)
    parser.add_argument("--expected-control-repositories", type=int, default=104)
    parser.add_argument("--expected-sensitivity-rows", type=int, default=1915)
    parser.add_argument("--expected-sensitivity-repositories", type=int, default=165)
    parser.add_argument("--expected-sensitivity-treatment-repositories", type=int, default=62)
    parser.add_argument("--expected-sensitivity-control-repositories", type=int, default=103)
    parser.add_argument("--expected-scope-excluded-repositories", type=int, default=2)
    parser.add_argument("--expected-eligible-rows", type=int, default=204509)
    parser.add_argument("--expected-eligible-unique-files", type=int, default=196644)
    parser.add_argument("--expected-primary-selected-rows", type=int, default=43325)
    parser.add_argument("--expected-primary-selected-unique-files", type=int, default=41905)
    parser.add_argument("--expected-primary-issue-stock", type=float, default=48478.0)
    args = parser.parse_args()

    thresholds = parse_thresholds(args.thresholds)
    for path in (args.a04_file, args.d02_file, args.b06_file, args.d05_reference_file):
        if not path.is_file():
            abort(f"Required input does not exist: {path}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading A04 ML file scores: {args.a04_file}")
    a04 = normalize_file_keys(read_table(args.a04_file), "A04")
    print(f"Reading D02 canonical file burden: {args.d02_file}")
    d02 = normalize_file_keys(normalize_repo_time_keys(read_table(args.d02_file), "D02"), "D02")
    print(f"Reading B06 authoritative panel: {args.b06_file}")
    b06 = normalize_repo_time_keys(read_table(args.b06_file), "B06")
    print(f"Reading D05 primary reference: {args.d05_reference_file}")
    d05 = read_table(args.d05_reference_file)
    d05_ref = extract_d05_mapping_reference(d05)

    if len(a04) != args.expected_a04_rows:
        abort(f"A04 row mismatch: expected {args.expected_a04_rows}, observed {len(a04)}")
    if len(d02) != args.expected_d02_rows:
        abort(f"D02 row mismatch: expected {args.expected_d02_rows}, observed {len(d02)}")
    if len(b06) != args.expected_b06_rows:
        abort(f"B06 row mismatch: expected {args.expected_b06_rows}, observed {len(b06)}")
    if b06["repo_id"].nunique() != args.expected_b06_repositories:
        abort("B06 repository-count mismatch")
    if b06.duplicated(list(REPO_TIME_KEYS)).any():
        abort("B06 contains duplicate repo-month keys")

    require_columns(a04, [ML_METRIC], "A04")
    a04[ML_METRIC] = pd.to_numeric(a04[ML_METRIC], errors="coerce")
    if a04.duplicated(list(JOIN_FILE_KEYS)).any():
        abort("A04 has duplicate historical file keys")

    burden_columns = resolve_burden_columns(d02)
    for source_column in burden_columns.values():
        d02[source_column] = pd.to_numeric(d02[source_column], errors="raise")
        if (d02[source_column] < 0).any():
            abort(f"D02 contains negative burden values in {source_column}")

    unique_d02 = d02.drop_duplicates(list(JOIN_FILE_KEYS)).copy()
    if len(unique_d02) != args.expected_d02_unique_files:
        abort(
            f"D02 unique-file mismatch: expected {args.expected_d02_unique_files}, observed {len(unique_d02)}"
        )
    missing_sha = audit_missing_sha_identity(a04, unique_d02)
    if missing_sha["d02_only_missing_sha_keys"] or missing_sha["a04_only_missing_sha_keys"]:
        abort(f"A04/D02 missing-SHA identity mismatch: {missing_sha}")

    universe = unique_d02[list(JOIN_FILE_KEYS)].merge(
        a04[list(JOIN_FILE_KEYS)],
        on=list(JOIN_FILE_KEYS),
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    d02_only = int((universe["_merge"] == "left_only").sum())
    a04_only = int((universe["_merge"] == "right_only").sum())
    if d02_only or a04_only:
        abort(f"A04/D02 historical-file universe mismatch: d02_only={d02_only}, a04_only={a04_only}")

    base = d02.merge(
        a04[list(JOIN_FILE_KEYS) + [ML_METRIC]],
        on=list(JOIN_FILE_KEYS),
        how="left",
        validate="many_to_one",
    )
    if len(base) != len(d02):
        abort("A04/D02 expanded join changed D02 row count")
    eligible = base[ML_METRIC].notna() & np.isfinite(base[ML_METRIC])
    eligible_rows = int(eligible.sum())
    eligible_unique = int(base.loc[eligible, list(JOIN_FILE_KEYS)].drop_duplicates().shape[0])
    if eligible_rows != args.expected_eligible_rows:
        abort(f"ML-eligible expanded-row mismatch: expected {args.expected_eligible_rows}, observed {eligible_rows}")
    if eligible_unique != args.expected_eligible_unique_files:
        abort(
            f"ML-eligible unique-file mismatch: expected {args.expected_eligible_unique_files}, observed {eligible_unique}"
        )

    sample_repo_ids, excluded_repo_ids = derive_sample_specs(d05_ref, b06)
    if len(excluded_repo_ids) != args.expected_scope_excluded_repositories:
        abort(
            f"Scope-excluded repository mismatch: expected {args.expected_scope_excluded_repositories}, "
            f"observed {len(excluded_repo_ids)} ({excluded_repo_ids})"
        )

    sample_b06: dict[str, pd.DataFrame] = {}
    for sample_spec, repo_ids in sample_repo_ids.items():
        sample = b06.loc[b06["repo_id"].isin(repo_ids)].copy()
        sample_b06[sample_spec] = sample
    full_counts = treatment_counts(sample_b06["full_sample"])
    sensitivity_counts = treatment_counts(sample_b06["exclude_scope_mismatch_repos"])
    expected_pairs = [
        (full_counts["repo_month_rows"], args.expected_b06_rows, "full rows"),
        (full_counts["repositories"], args.expected_b06_repositories, "full repositories"),
        (full_counts["treatment_repositories"], args.expected_treatment_repositories, "full treatment repositories"),
        (full_counts["control_repositories"], args.expected_control_repositories, "full control repositories"),
        (sensitivity_counts["repo_month_rows"], args.expected_sensitivity_rows, "sensitivity rows"),
        (sensitivity_counts["repositories"], args.expected_sensitivity_repositories, "sensitivity repositories"),
        (sensitivity_counts["treatment_repositories"], args.expected_sensitivity_treatment_repositories, "sensitivity treatment repositories"),
        (sensitivity_counts["control_repositories"], args.expected_sensitivity_control_repositories, "sensitivity control repositories"),
    ]
    for observed, expected, label in expected_pairs:
        if observed != expected:
            abort(f"{label} mismatch: expected {expected}, observed {observed}")

    # Eligible support is threshold-independent and is materialized per repo-month.
    eligible_agg = (
        base.loc[eligible, ["repo_id", "time_index"]]
        .groupby(["repo_id", "time_index"], as_index=False)
        .size()
        .rename(columns={"size": "eligible_ml_file_count"})
    )

    panels: list[pd.DataFrame] = []
    global_audit_rows: list[dict[str, object]] = []
    timing_rows: list[dict[str, object]] = []
    primary_panels: dict[str, pd.DataFrame] = {}

    for threshold in thresholds:
        selected_mask = eligible & base[ML_METRIC].gt(threshold)
        selected = base.loc[selected_mask].copy()
        selected["_has_issue"] = selected[burden_columns["selected_issue_total"]].gt(0).astype(int)

        agg_spec: dict[str, tuple[str, str]] = {
            "selected_file_count": (burden_columns["selected_issue_total"], "size"),
            "selected_file_with_any_issue_count": ("_has_issue", "sum"),
        }
        for output_column, source_column in burden_columns.items():
            agg_spec[output_column] = (source_column, "sum")
        selected_agg = selected.groupby(["repo_id", "time_index"], as_index=False).agg(**agg_spec)

        selected_unique = int(selected[list(JOIN_FILE_KEYS)].drop_duplicates().shape[0])
        selected_expanded = int(len(selected))

        for sample_spec, base_panel in sample_b06.items():
            panel = base_panel.merge(eligible_agg, on=["repo_id", "time_index"], how="left", validate="one_to_one")
            panel = panel.merge(selected_agg, on=["repo_id", "time_index"], how="left", validate="one_to_one")
            integer_columns = [
                "eligible_ml_file_count", "selected_file_count", "selected_file_with_any_issue_count"
            ]
            for column in integer_columns:
                panel[column] = panel[column].fillna(0).astype(int)
            for output_column in burden_columns:
                panel[output_column] = panel[output_column].fillna(0.0).astype(float)

            panel["selected_issue_free_file_count"] = (
                panel["selected_file_count"] - panel["selected_file_with_any_issue_count"]
            ).astype(int)
            if (panel["selected_issue_free_file_count"] < 0).any():
                abort("Selected issue-free file count became negative")
            panel["selected_file_share_of_eligible"] = np.where(
                panel["eligible_ml_file_count"].gt(0),
                panel["selected_file_count"] / panel["eligible_ml_file_count"],
                0.0,
            )
            panel["has_selected_files"] = panel["selected_file_count"].gt(0).astype(int)
            panel["has_selected_issue_burden"] = panel["selected_issue_total"].gt(0).astype(int)
            add_log_outcomes(panel)

            panel["sample_spec"] = sample_spec
            panel["mapping_spec"] = MAPPING_SPEC
            panel["threshold_spec_id"] = threshold_spec_id(threshold)
            panel["threshold"] = float(threshold)
            panel["threshold_role"] = "primary" if math.isclose(threshold, PRIMARY_THRESHOLD, abs_tol=1e-12) else "sensitivity_grid"
            panel["ml_metric"] = ML_METRIC
            panel["ml_operator"] = STRICT_OPERATOR
            panel["primary_threshold"] = PRIMARY_THRESHOLD
            panel["primary_analysis"] = int(
                sample_spec == "full_sample" and math.isclose(threshold, PRIMARY_THRESHOLD, abs_tol=1e-12)
            )
            panels.append(panel)

            if math.isclose(threshold, PRIMARY_THRESHOLD, abs_tol=1e-12):
                primary_panels[sample_spec] = panel.copy()

            sample_selected = selected.loc[selected["repo_id"].isin(sample_repo_ids[sample_spec])]
            counts = treatment_counts(panel)
            audit = {
                "sample_spec": sample_spec,
                "mapping_spec": MAPPING_SPEC,
                "threshold_spec_id": threshold_spec_id(threshold),
                "threshold": float(threshold),
                "threshold_role": panel["threshold_role"].iloc[0],
                "repo_month_rows": int(len(panel)),
                "repositories": int(panel["repo_id"].nunique()),
                "eligible_file_rows": int(base.loc[eligible & base["repo_id"].isin(sample_repo_ids[sample_spec])].shape[0]),
                "selected_file_rows": int(len(sample_selected)),
                "selected_unique_historical_files": int(
                    sample_selected[list(JOIN_FILE_KEYS)].drop_duplicates().shape[0]
                ),
                "repo_months_with_selected_files": int(panel["has_selected_files"].sum()),
                "repo_months_with_positive_issue_burden": int(panel["has_selected_issue_burden"].sum()),
                "zero_issue_repo_month_share": float(panel["selected_issue_total"].eq(0).mean()),
                "repositories_with_within_quality_variation": int(
                    panel.groupby("repo_id")["log1p_selected_issue_total"].nunique().gt(1).sum()
                ),
            }
            for output_column in burden_columns:
                audit[output_column] = float(panel[output_column].sum())
            global_audit_rows.append(audit)

            # Compact timing audit for downstream support inspection.
            treatment_group = pd.to_numeric(panel["treatment_group"], errors="raise").astype(int)
            event_index = pd.to_numeric(panel["event_index"], errors="raise").astype(int)
            time_index = pd.to_numeric(panel["time_index"], errors="raise").astype(int)
            timing_masks = {
                "control": treatment_group.eq(0),
                "treatment_pre": treatment_group.eq(1) & time_index.lt(event_index),
                "treatment_post": treatment_group.eq(1) & time_index.ge(event_index),
            }
            for timing_group, timing_mask in timing_masks.items():
                part = panel.loc[timing_mask]
                timing_rows.append({
                    "sample_spec": sample_spec,
                    "threshold_spec_id": threshold_spec_id(threshold),
                    "threshold": float(threshold),
                    "timing_group": timing_group,
                    "repo_month_rows": int(len(part)),
                    "repositories": int(part["repo_id"].nunique()),
                    "selected_file_rows": int(part["selected_file_count"].sum()),
                    "selected_issue_total": float(part["selected_issue_total"].sum()),
                })

    long_panel = pd.concat(panels, ignore_index=True)
    expected_long_rows = len(thresholds) * (args.expected_b06_rows + args.expected_sensitivity_rows)
    if len(long_panel) != expected_long_rows:
        abort(f"Long-panel row mismatch: expected {expected_long_rows}, observed {len(long_panel)}")
    key_columns = ["sample_spec", "threshold_spec_id", "repo_id", "time_index"]
    duplicate_keys = int(long_panel.duplicated(key_columns).sum())
    if duplicate_keys:
        abort(f"D07 long panel contains {duplicate_keys} duplicate keys")

    global_audit = pd.DataFrame(global_audit_rows).sort_values(["sample_spec", "threshold"]).reset_index(drop=True)
    for sample_spec in sample_repo_ids:
        sample_audit = global_audit.loc[global_audit["sample_spec"].eq(sample_spec)].sort_values("threshold")
        monotone_metrics = ["selected_file_rows", *BURDEN_SOURCES.keys()]
        for metric in monotone_metrics:
            values = pd.to_numeric(sample_audit[metric], errors="raise").to_numpy(dtype=float)
            if np.any(np.diff(values) > 1e-9):
                abort(f"Threshold monotonicity failed for {sample_spec}::{metric}: {values}")

    full_primary_audit = global_audit.loc[
        global_audit["sample_spec"].eq("full_sample") & np.isclose(global_audit["threshold"], PRIMARY_THRESHOLD)
    ]
    if len(full_primary_audit) != 1:
        abort("Expected exactly one full-sample primary audit row")
    primary_row = full_primary_audit.iloc[0]
    if int(primary_row["selected_file_rows"]) != args.expected_primary_selected_rows:
        abort("Primary selected expanded-file count does not reproduce D05")
    if int(primary_row["selected_unique_historical_files"]) != args.expected_primary_selected_unique_files:
        abort("Primary selected unique-file count does not reproduce A04/D05")
    if not math.isclose(float(primary_row["selected_issue_total"]), args.expected_primary_issue_stock, abs_tol=1e-9):
        abort("Primary selected issue stock does not reproduce D05")

    d05_file_count_column = resolve_d05_file_count_column(d05_ref)
    reproduction = compare_primary_to_d05(primary_panels, d05_ref, d05_file_count_column)

    sample_summary_rows = []
    for sample_spec, panel in sample_b06.items():
        counts = treatment_counts(panel)
        counts.update({
            "sample_spec": sample_spec,
            "excluded_repository_count": 0 if sample_spec == "full_sample" else len(excluded_repo_ids),
            "excluded_repo_ids": "" if sample_spec == "full_sample" else "|".join(map(str, excluded_repo_ids)),
        })
        sample_summary_rows.append(counts)
    sample_summary = pd.DataFrame(sample_summary_rows)

    outcome_spec = pd.DataFrame([
        {
            "outcome": f"log1p_{column}",
            "raw_outcome": column,
            "role": "primary_burden" if column == "selected_issue_total" else "burden_robustness",
            "transform": "log1p(repo-month selected-file issue stock)",
            "density_computed": 0,
        }
        for column in BURDEN_SOURCES
    ])

    # Recompute all log outcomes before writing and count any mismatch.
    log_mismatches = 0
    for column in BURDEN_SOURCES:
        observed = pd.to_numeric(long_panel[f"log1p_{column}"], errors="raise").to_numpy(dtype=float)
        expected = np.log1p(pd.to_numeric(long_panel[column], errors="raise").to_numpy(dtype=float))
        log_mismatches += int((~np.isclose(observed, expected, atol=1e-12, rtol=0)).sum())

    qc_rows: list[tuple[str, object, object, str, str]] = []
    def add_qc(name: str, observed: object, expected: object, status: str, detail: str = "") -> None:
        qc_rows.append((name, observed, expected, status, detail))

    add_qc("threshold_count", len(thresholds), 21, "pass" if len(thresholds) == 21 else "fail")
    add_qc("sample_spec_count", len(sample_repo_ids), 2, "pass" if len(sample_repo_ids) == 2 else "fail")
    add_qc("a04_rows", len(a04), args.expected_a04_rows, "pass")
    add_qc("d02_rows", len(d02), args.expected_d02_rows, "pass")
    add_qc("d02_unique_files", len(unique_d02), args.expected_d02_unique_files, "pass")
    add_qc("b06_rows", len(b06), args.expected_b06_rows, "pass")
    add_qc("full_sample_rows", full_counts["repo_month_rows"], args.expected_b06_rows, "pass")
    add_qc("scope_sensitivity_rows", sensitivity_counts["repo_month_rows"], args.expected_sensitivity_rows, "pass")
    add_qc("long_panel_rows", len(long_panel), expected_long_rows, "pass" if len(long_panel) == expected_long_rows else "fail")
    add_qc("long_panel_duplicate_keys", duplicate_keys, 0, "pass" if duplicate_keys == 0 else "fail")
    add_qc("eligible_expanded_file_rows", eligible_rows, args.expected_eligible_rows, "pass")
    add_qc("eligible_unique_files", eligible_unique, args.expected_eligible_unique_files, "pass")
    add_qc("a04_missing_sha_files", missing_sha["a04_missing_sha_files"], missing_sha["d02_missing_sha_files"], "pass")
    missing_sha_mismatch = missing_sha["d02_only_missing_sha_keys"] + missing_sha["a04_only_missing_sha_keys"]
    add_qc("missing_sha_identity_mismatches", missing_sha_mismatch, 0, "pass" if missing_sha_mismatch == 0 else "fail")
    add_qc("d02_only_file_keys", d02_only, 0, "pass" if d02_only == 0 else "fail")
    add_qc("a04_only_file_keys", a04_only, 0, "pass" if a04_only == 0 else "fail")
    add_qc("scope_sensitivity_repositories_excluded", len(excluded_repo_ids), args.expected_scope_excluded_repositories, "pass")
    add_qc("primary_full_selected_file_rows", int(primary_row["selected_file_rows"]), args.expected_primary_selected_rows, "pass")
    add_qc("primary_full_selected_unique_files", int(primary_row["selected_unique_historical_files"]), args.expected_primary_selected_unique_files, "pass")
    add_qc("primary_full_selected_issue_total", float(primary_row["selected_issue_total"]), args.expected_primary_issue_stock, "pass")
    reproduction_failures = int(reproduction["mismatches"].sum())
    add_qc("primary_d05_reproduction_mismatches", reproduction_failures, 0, "pass" if reproduction_failures == 0 else "fail")
    add_qc("negative_selected_issue_values", int((long_panel[list(BURDEN_SOURCES)].to_numpy(dtype=float) < 0).sum()), 0, "pass")
    add_qc("log1p_outcome_recomputation_mismatches", log_mismatches, 0, "pass" if log_mismatches == 0 else "fail")
    qc = pd.DataFrame(qc_rows, columns=["check", "observed", "expected", "status", "detail"])
    if qc["status"].eq("fail").any():
        abort("D07 hard QC failed; inspect quality_ml_threshold_checks.csv")

    output_panel = args.output_dir / "quality_ml_threshold_repo_month_panel.csv.gz"
    output_global = args.output_dir / "quality_ml_threshold_global_audit.csv"
    output_timing = args.output_dir / "quality_ml_threshold_by_treatment_timing.csv"
    output_sample = args.output_dir / "quality_ml_threshold_sample_summary.csv"
    output_outcomes = args.output_dir / "quality_ml_threshold_outcome_spec.csv"
    output_reproduction = args.output_dir / "quality_ml_threshold_d05_reproduction.csv"
    output_checks = args.output_dir / "quality_ml_threshold_checks.csv"
    output_summary = args.output_dir / "quality_ml_threshold_summary.csv"
    output_metadata = args.output_dir / "metadata.json"

    long_panel.to_csv(output_panel, index=False, compression="gzip")
    global_audit.to_csv(output_global, index=False)
    pd.DataFrame(timing_rows).to_csv(output_timing, index=False)
    sample_summary.to_csv(output_sample, index=False)
    outcome_spec.to_csv(output_outcomes, index=False)
    reproduction.to_csv(output_reproduction, index=False)
    qc.to_csv(output_checks, index=False)

    summary = pd.DataFrame([
        ("script_version", "run-x-d07-v1"),
        ("status", "PASS"),
        ("ml_metric", ML_METRIC),
        ("quality_semantics", "unresolved_sonarqube_issue_stock_at_historical_snapshot"),
        ("mapping_spec", MAPPING_SPEC),
        ("thresholds", len(thresholds)),
        ("sample_specs", len(sample_repo_ids)),
        ("full_sample_repo_month_rows", full_counts["repo_month_rows"]),
        ("scope_sensitivity_repo_month_rows", sensitivity_counts["repo_month_rows"]),
        ("long_panel_rows", len(long_panel)),
        ("primary_threshold", PRIMARY_THRESHOLD),
        ("primary_full_selected_file_rows", int(primary_row["selected_file_rows"])),
        ("primary_full_selected_issue_total", float(primary_row["selected_issue_total"])),
        ("eligible_expanded_file_rows", eligible_rows),
        ("eligible_unique_historical_files", eligible_unique),
        ("density_computed", 0),
        ("scope_sensitivity_repositories", len(excluded_repo_ids)),
        ("hard_qc_failures", int(qc["status"].eq("fail").sum())),
    ], columns=["metric", "value"])
    summary.to_csv(output_summary, index=False)

    metadata = {
        "experiment_name": EXPERIMENT_NAME,
        "implementation_version": IMPLEMENTATION_VERSION,
        "inputs": {
            "a04_file": str(args.a04_file), "a04_sha256": sha256_file(args.a04_file),
            "d02_file": str(args.d02_file), "d02_sha256": sha256_file(args.d02_file),
            "b06_file": str(args.b06_file), "b06_sha256": sha256_file(args.b06_file),
            "d05_reference_file": str(args.d05_reference_file), "d05_reference_sha256": sha256_file(args.d05_reference_file),
        },
        "ml_metric": ML_METRIC,
        "operator": STRICT_OPERATOR,
        "threshold_grid": [float(v) for v in thresholds],
        "primary_threshold": PRIMARY_THRESHOLD,
        "mapping_spec": MAPPING_SPEC,
        "sample_specs": ["full_sample", "exclude_scope_mismatch_repos"],
        "scope_excluded_repo_ids": [int(value) for value in excluded_repo_ids],
        "function_level_classifier_boundary": "unchanged",
        "density_computed": False,
        "downstream_experiment": "run-x-d08",
        "selection_policy": "thresholds are sensitivity specifications; never choose a threshold using downstream DiD significance",
    }
    output_metadata.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("=" * 80)
    print("run-x-d07 ML threshold x SonarQube burden panel")
    print("Status:                                  PASS")
    print(f"Thresholds:                              {len(thresholds)}")
    print(f"Sample specifications:                   {len(sample_repo_ids)}")
    print(f"Full-sample repo-month rows:             {full_counts['repo_month_rows']}")
    print(f"Scope-sensitivity repo-month rows:       {sensitivity_counts['repo_month_rows']}")
    print(f"Long panel rows:                         {len(long_panel)}")
    print(f"Primary threshold:                       {PRIMARY_THRESHOLD:.2f}")
    print(f"Primary full selected files:             {int(primary_row['selected_file_rows'])}")
    print(f"Primary full selected issue stock:       {float(primary_row['selected_issue_total']):.0f}")
    print(f"ML-eligible expanded files:              {eligible_rows}")
    print(f"ML-eligible unique historical files:     {eligible_unique}")
    print(f"A04/D02 missing file_sha256 files:       {missing_sha['a04_missing_sha_files']}/{missing_sha['d02_missing_sha_files']}")
    print(f"Scope-sensitivity repositories excluded: {len(excluded_repo_ids)}")
    print("D05 primary reproduction:                PASS")
    print("Density computed:                        0")
    print("Hard QC failures:                        0")
    print(f"D08 input panel:                         {output_panel}")
    print("=" * 80)


if __name__ == "__main__":
    main()
