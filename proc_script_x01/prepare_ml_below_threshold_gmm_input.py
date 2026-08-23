#!/usr/bin/env python3
"""Prepare the ML-below-threshold repo-month input panel for run-x-g04.

The experiment partitions the canonical historical Python file universe using
A04's token-weighted file-level ML AGC share while preserving unclassified
files as a separate category:

    Eligible:      finite file_ml_agc_share_space_by_token_weighted
    Above:         finite ML share > 0.50
    Below:         finite ML share <= 0.50
    Unclassified:  ML share is missing or non-finite

The G04 output is a zero-inclusive repo-month input panel for the downstream
run-x-g05 GMM experiment. Its quality variable is the SonarQube issue burden
aggregated only over the Below set. Unclassified ML files are never treated as
below-threshold.

Inputs
------
A04:
    Canonical historical-file ML aggregation with token-weighted AGC share.
D02:
    Canonical repo-month/file SonarQube burden for the same historical files.
B06:
    Authoritative 1,954-row repo-month panel used for file-count auditing and
    the downstream G05 velocity/covariate join.
D05 reference:
    Previously validated ML-primary repo-month panel used to reproduce the
    Above set exactly before trusting the complementary Below construction.

Outputs
-------
ml_below_threshold_repo_month_panel.csv.gz
    Zero-inclusive 1,954-row panel containing the below-threshold issue burden.
ml_below_threshold_support.csv
    Global support for all, eligible, above, below, and unclassified sets.
ml_below_threshold_reproduction_audit.csv
    Exact reproduction audit against the D05 primary high-ML-share panel.
ml_below_threshold_qc.csv
    Hard identity, join, set-algebra, and B06 reconciliation checks.
ml_below_threshold_metadata.csv
    Input provenance and threshold definitions.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

IMPLEMENTATION_VERSION = "v2"
EXPERIMENT_NAME = "run-x-g04-prepare-ml-below-threshold-gmm-input"
ML_METRIC = "file_ml_agc_share_space_by_token_weighted"
ML_THRESHOLD = 0.50
FILE_KEYS = ("snapshot_id", "relative_path", "file_sha256")
REPO_TIME_KEYS = ("repo_id", "time_index")
JOIN_SHA_COLUMN = "_file_sha256_join"
JOIN_FILE_KEYS = ("snapshot_id", "relative_path", JOIN_SHA_COLUMN)
MISSING_SHA_SENTINEL = "__MISSING_FILE_SHA256__"


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
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        abort(f"{label} is missing required columns: {missing}")


def normalize_repo_time_keys(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    out = frame.copy()
    require_columns(out, REPO_TIME_KEYS, label)
    out["repo_id"] = pd.to_numeric(out["repo_id"], errors="raise").astype(int)
    out["time_index"] = pd.to_numeric(out["time_index"], errors="raise").astype(int)
    if out[list(REPO_TIME_KEYS)].isna().any().any():
        abort(f"{label} contains missing repo_id/time_index keys")
    return out


def normalize_file_keys(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    """Normalize historical-file keys while preserving canonical missing SHA rows.

    A04 keeps no-FUN / not-prepared files in the full historical universe. Some
    of those canonical rows can have a missing file_sha256. D05 and the already
    validated G01 lineage reconcile A04 and D02 on the same historical-file
    universe, so a missing SHA is not itself an error. We therefore require the
    stable snapshot/path components, preserve missing SHA as missing, and build
    an explicit sentinel join column for deterministic A04-D02 reconciliation.
    """
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
    """Verify that missing-SHA historical files match exactly by snapshot/path."""
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


def extract_d05_primary(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()

    # Prefer the explicit primary_analysis marker when available. Otherwise,
    # reproduce the documented D05 primary specification directly.
    if "primary_analysis" in data.columns:
        primary = pd.to_numeric(data["primary_analysis"], errors="coerce") == 1
        data = data.loc[primary].copy()
    else:
        require_columns(data, ["sample_spec", "mapping_spec"], "D05 reference")
        data = data.loc[
            (data["sample_spec"].astype(str) == "full_sample")
            & (data["mapping_spec"].astype(str) == "all_ml_files")
        ].copy()

    if data.empty:
        abort("D05 primary-reference filter produced zero rows")

    if "selected_file_rows" not in data.columns:
        if "selected_file_count" in data.columns:
            data["selected_file_rows"] = data["selected_file_count"]
        else:
            abort("D05 reference is missing selected_file_rows/selected_file_count")

    require_columns(
        data,
        ["repo_id", "time_index", "selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"],
        "D05 reference",
    )
    data = normalize_repo_time_keys(data, "D05 reference")
    for column in ("selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"):
        data[column] = pd.to_numeric(data[column], errors="raise")
    if data.duplicated(list(REPO_TIME_KEYS)).any():
        abort("D05 primary reference contains duplicate repo-month keys")
    return data[list(REPO_TIME_KEYS) + ["selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"]]


def compare_reproduction(reference: pd.DataFrame, reconstructed: pd.DataFrame) -> pd.DataFrame:
    check = reference.merge(
        reconstructed,
        on=list(REPO_TIME_KEYS),
        how="outer",
        suffixes=("_reference", "_new"),
        indicator=True,
        validate="one_to_one",
    )
    key_mismatch = int((check["_merge"] != "both").sum())
    row_mismatch = int((~np.isclose(
        check["selected_file_rows_reference"], check["selected_file_rows_new"],
        atol=0, rtol=0, equal_nan=False,
    )).sum())
    issue_mismatch = int((~np.isclose(
        check["selected_issue_total_reference"], check["selected_issue_total_new"],
        atol=1e-9, rtol=0, equal_nan=False,
    )).sum())
    log_mismatch = int((~np.isclose(
        check["log1p_selected_issue_total_reference"], check["log1p_selected_issue_total_new"],
        atol=1e-12, rtol=0, equal_nan=False,
    )).sum())
    status = "pass" if (key_mismatch + row_mismatch + issue_mismatch + log_mismatch) == 0 else "fail"
    return pd.DataFrame([{
        "reference": "D05_primary_ML_above_threshold",
        "reference_rows": len(reference),
        "new_rows": len(reconstructed),
        "key_mismatches": key_mismatch,
        "selected_file_row_mismatches": row_mismatch,
        "selected_issue_total_mismatches": issue_mismatch,
        "log1p_mismatches": log_mismatch,
        "status": status,
    }])


def aggregate_selection(base: pd.DataFrame, mask: pd.Series, prefix: str) -> pd.DataFrame:
    selected = base.loc[mask, ["repo_id", "time_index", "sonar_issue_total"]].copy()
    if selected.empty:
        return pd.DataFrame(columns=["repo_id", "time_index", f"{prefix}_file_rows", f"{prefix}_issue_total"])
    return selected.groupby(["repo_id", "time_index"], as_index=False).agg(
        **{
            f"{prefix}_file_rows": ("sonar_issue_total", "size"),
            f"{prefix}_issue_total": ("sonar_issue_total", "sum"),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a04-file", required=True, type=Path)
    parser.add_argument("--d02-file", required=True, type=Path)
    parser.add_argument("--b06-file", required=True, type=Path)
    parser.add_argument("--d05-reference-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-a04-rows", type=int, default=494592)
    parser.add_argument("--expected-d02-rows", type=int, default=510297)
    parser.add_argument("--expected-d02-unique-files", type=int, default=494592)
    parser.add_argument("--expected-b06-rows", type=int, default=1954)
    parser.add_argument("--expected-eligible-rows", type=int, default=204509)
    parser.add_argument("--expected-eligible-unique-files", type=int, default=196644)
    parser.add_argument("--expected-above-rows", type=int, default=43325)
    parser.add_argument("--expected-above-unique-files", type=int, default=41905)
    parser.add_argument("--expected-above-issue-stock", type=float, default=48478.0)
    parser.add_argument("--expected-below-rows", type=int, default=161184)
    parser.add_argument("--expected-below-unique-files", type=int, default=154739)
    args = parser.parse_args()

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
    print(f"Reading D05 ML reference: {args.d05_reference_file}")
    d05 = read_table(args.d05_reference_file)

    if len(a04) != args.expected_a04_rows:
        abort(f"A04 row mismatch: expected {args.expected_a04_rows}, observed {len(a04)}")
    if len(d02) != args.expected_d02_rows:
        abort(f"D02 row mismatch: expected {args.expected_d02_rows}, observed {len(d02)}")
    if len(b06) != args.expected_b06_rows:
        abort(f"B06 row mismatch: expected {args.expected_b06_rows}, observed {len(b06)}")

    require_columns(a04, [ML_METRIC], "A04")
    require_columns(d02, ["sonar_issue_total"], "D02")
    require_columns(b06, ["python_file_count_manifest", "issue_total_py_sonarqube"], "B06")

    if a04.duplicated(list(JOIN_FILE_KEYS)).any():
        abort("A04 contains duplicate historical file keys after missing-SHA normalization")
    if b06.duplicated(list(REPO_TIME_KEYS)).any():
        abort("B06 contains duplicate repo-month keys")

    a04[ML_METRIC] = pd.to_numeric(a04[ML_METRIC], errors="coerce")
    d02["sonar_issue_total"] = pd.to_numeric(d02["sonar_issue_total"], errors="raise")
    b06["python_file_count_manifest"] = pd.to_numeric(b06["python_file_count_manifest"], errors="raise").astype(int)
    b06["issue_total_py_sonarqube"] = pd.to_numeric(b06["issue_total_py_sonarqube"], errors="raise")
    if d02["sonar_issue_total"].isna().any() or (d02["sonar_issue_total"] < 0).any():
        abort("D02 sonar_issue_total must be complete and non-negative")

    unique_d02 = d02[list(FILE_KEYS) + [JOIN_SHA_COLUMN]].drop_duplicates(subset=list(JOIN_FILE_KEYS))
    unique_d02_files = int(len(unique_d02))
    if unique_d02_files != args.expected_d02_unique_files:
        abort(f"D02 unique-file mismatch: expected {args.expected_d02_unique_files}, observed {unique_d02_files}")
    if unique_d02.duplicated(list(JOIN_FILE_KEYS)).any():
        abort("D02 unique historical-file keys are not unique after missing-SHA normalization")

    # Missing SHA is valid for canonical unclassified files. Audit those rows
    # separately by snapshot/path, then reconcile the complete universe with an
    # explicit sentinel join key. This matches the validated A04-D02 lineage
    # without silently treating missing SHA as an ordinary hash value.
    missing_sha_audit = audit_missing_sha_identity(a04, unique_d02)
    if missing_sha_audit["d02_only_missing_sha_keys"] or missing_sha_audit["a04_only_missing_sha_keys"]:
        abort(
            "A04/D02 missing-SHA identity mismatch: "
            f"d02_only={missing_sha_audit['d02_only_missing_sha_keys']}, "
            f"a04_only={missing_sha_audit['a04_only_missing_sha_keys']}"
        )

    identity_audit = unique_d02[list(JOIN_FILE_KEYS)].merge(
        a04[list(JOIN_FILE_KEYS)],
        on=list(JOIN_FILE_KEYS),
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    d02_only = int((identity_audit["_merge"] == "left_only").sum())
    a04_only = int((identity_audit["_merge"] == "right_only").sum())
    if d02_only or a04_only:
        abort(f"A04/D02 historical-file identity mismatch: d02_only={d02_only}, a04_only={a04_only}")

    base = d02.merge(
        a04[list(JOIN_FILE_KEYS) + [ML_METRIC]],
        on=list(JOIN_FILE_KEYS),
        how="left",
        validate="many_to_one",
    )
    if len(base) != len(d02):
        abort(f"A04/D02 expanded join changed row count: before={len(d02)}, after={len(base)}")

    eligible = base[ML_METRIC].notna() & np.isfinite(base[ML_METRIC])
    above = eligible & (base[ML_METRIC] > ML_THRESHOLD)
    below = eligible & (base[ML_METRIC] <= ML_THRESHOLD)
    unclassified = ~eligible
    all_files = pd.Series(True, index=base.index, dtype=bool)

    observed_counts = {
        "eligible": int(eligible.sum()),
        "above": int(above.sum()),
        "below": int(below.sum()),
    }
    expected_counts = {
        "eligible": args.expected_eligible_rows,
        "above": args.expected_above_rows,
        "below": args.expected_below_rows,
    }
    for name, expected in expected_counts.items():
        if observed_counts[name] != expected:
            abort(f"{name} row mismatch: expected {expected}, observed {observed_counts[name]}")

    eligible_unique = int(base.loc[eligible, list(FILE_KEYS)].drop_duplicates().shape[0])
    above_unique = int(base.loc[above, list(FILE_KEYS)].drop_duplicates().shape[0])
    below_unique = int(base.loc[below, list(FILE_KEYS)].drop_duplicates().shape[0])
    unique_expected = {
        "eligible": args.expected_eligible_unique_files,
        "above": args.expected_above_unique_files,
        "below": args.expected_below_unique_files,
    }
    unique_observed = {"eligible": eligible_unique, "above": above_unique, "below": below_unique}
    for name, expected in unique_expected.items():
        if unique_observed[name] != expected:
            abort(f"{name} unique-file mismatch: expected {expected}, observed {unique_observed[name]}")

    above_issue_stock = float(base.loc[above, "sonar_issue_total"].sum())
    if not np.isclose(above_issue_stock, args.expected_above_issue_stock, atol=1e-9, rtol=0):
        abort(
            f"Above-threshold issue-stock mismatch: expected {args.expected_above_issue_stock}, "
            f"observed {above_issue_stock}"
        )

    masks = {
        "all": all_files,
        "ml_eligible": eligible,
        "ml_above_threshold": above,
        "ml_below_threshold": below,
        "ml_unclassified": unclassified,
    }

    panel = b06[["repo_id", "time_index", "python_file_count_manifest", "issue_total_py_sonarqube"]].copy()
    for prefix, mask in masks.items():
        agg = aggregate_selection(base, mask, prefix)
        panel = panel.merge(agg, on=list(REPO_TIME_KEYS), how="left", validate="one_to_one")
        panel[f"{prefix}_file_rows"] = panel[f"{prefix}_file_rows"].fillna(0).astype(int)
        panel[f"{prefix}_issue_total"] = panel[f"{prefix}_issue_total"].fillna(0.0)

    # Generic selected_* columns are the downstream run-x-g05 input contract.
    panel["selected_file_rows"] = panel["ml_below_threshold_file_rows"]
    panel["selected_issue_total"] = panel["ml_below_threshold_issue_total"]
    panel["log1p_selected_issue_total"] = np.log1p(panel["selected_issue_total"].astype(float))

    panel["ml_metric"] = ML_METRIC
    panel["ml_threshold"] = ML_THRESHOLD
    panel["ml_eligibility_rule"] = "finite_weighted_ML_AGC_share"
    panel["ml_above_rule"] = "finite_ML_share_GT_primary_threshold"
    panel["ml_below_rule"] = "finite_ML_share_LE_primary_threshold"
    panel["ml_unclassified_rule"] = "ML_share_missing_or_nonfinite"

    eligible_count_identity = (
        panel["ml_eligible_file_rows"]
        == panel["ml_above_threshold_file_rows"] + panel["ml_below_threshold_file_rows"]
    )
    eligible_issue_identity = np.isclose(
        panel["ml_eligible_issue_total"],
        panel["ml_above_threshold_issue_total"] + panel["ml_below_threshold_issue_total"],
        atol=1e-9,
        rtol=0,
    )
    all_count_identity = (
        panel["all_file_rows"] == panel["ml_eligible_file_rows"] + panel["ml_unclassified_file_rows"]
    )
    all_issue_identity = np.isclose(
        panel["all_issue_total"],
        panel["ml_eligible_issue_total"] + panel["ml_unclassified_issue_total"],
        atol=1e-9,
        rtol=0,
    )
    b06_file_count_identity = panel["all_file_rows"] == panel["python_file_count_manifest"]
    b06_issue_identity = np.isclose(
        panel["all_issue_total"], panel["issue_total_py_sonarqube"], atol=1e-9, rtol=0
    )

    hard_checks = {
        "eligible_count_identity": eligible_count_identity,
        "eligible_issue_identity": eligible_issue_identity,
        "all_count_identity": all_count_identity,
        "all_issue_identity": all_issue_identity,
        "b06_file_count_identity": b06_file_count_identity,
    }
    failed = {name: int((~values).sum()) for name, values in hard_checks.items() if not bool(values.all())}
    if failed:
        abort(f"ML threshold partition hard algebra failed: {failed}")

    # Reproduce the validated D05 primary high-ML-share subset exactly.
    above_reconstructed = panel[[
        "repo_id", "time_index", "ml_above_threshold_file_rows", "ml_above_threshold_issue_total"
    ]].rename(columns={
        "ml_above_threshold_file_rows": "selected_file_rows",
        "ml_above_threshold_issue_total": "selected_issue_total",
    })
    above_reconstructed["log1p_selected_issue_total"] = np.log1p(above_reconstructed["selected_issue_total"])
    d05_reference = extract_d05_primary(d05)
    reproduction_audit = compare_reproduction(d05_reference, above_reconstructed)
    if not (reproduction_audit["status"] == "pass").all():
        abort("D05 primary ML reproduction failed; G04 below-threshold panel is not trusted")

    def support_row(name: str, mask: pd.Series) -> dict[str, object]:
        subset = base.loc[mask]
        return {
            "selection": name,
            "expanded_repo_month_file_rows": int(mask.sum()),
            "unique_historical_files": int(subset[list(FILE_KEYS)].drop_duplicates().shape[0]),
            "issue_stock": float(subset["sonar_issue_total"].sum()),
            "repo_months_with_files": int((panel[f"{name}_file_rows"] > 0).sum()),
            "repo_months_with_positive_issue_stock": int((panel[f"{name}_issue_total"] > 0).sum()),
        }

    support = pd.DataFrame([support_row(name, mask) for name, mask in masks.items()])

    b06_issue_delta = panel["issue_total_py_sonarqube"] - panel["all_issue_total"]
    b06_issue_mismatch_rows = int((~b06_issue_identity).sum())
    b06_issue_delta_sum = float(b06_issue_delta.sum())

    below_issue_stock = float(base.loc[below, "sonar_issue_total"].sum())
    eligible_issue_stock = float(base.loc[eligible, "sonar_issue_total"].sum())
    unclassified_issue_stock = float(base.loc[unclassified, "sonar_issue_total"].sum())
    below_zero_share = float((panel["selected_issue_total"] == 0).mean())
    below_variation_repos = int(panel.groupby("repo_id")["log1p_selected_issue_total"].nunique().gt(1).sum())

    qc_rows = [
        ("repo_month_rows", len(panel), args.expected_b06_rows, len(panel) == args.expected_b06_rows),
        ("duplicate_repo_month_keys", int(panel.duplicated(list(REPO_TIME_KEYS)).sum()), 0, not panel.duplicated(list(REPO_TIME_KEYS)).any()),
        ("a04_unique_historical_files", len(a04), args.expected_a04_rows, len(a04) == args.expected_a04_rows),
        ("d02_unique_historical_files", unique_d02_files, args.expected_d02_unique_files, unique_d02_files == args.expected_d02_unique_files),
        ("a04_d02_d02_only_keys", d02_only, 0, d02_only == 0),
        ("a04_d02_a04_only_keys", a04_only, 0, a04_only == 0),
        ("a04_missing_file_sha256_files", missing_sha_audit["a04_missing_sha_files"], missing_sha_audit["d02_missing_sha_files"], missing_sha_audit["a04_missing_sha_files"] == missing_sha_audit["d02_missing_sha_files"]),
        ("d02_only_missing_sha_keys", missing_sha_audit["d02_only_missing_sha_keys"], 0, missing_sha_audit["d02_only_missing_sha_keys"] == 0),
        ("a04_only_missing_sha_keys", missing_sha_audit["a04_only_missing_sha_keys"], 0, missing_sha_audit["a04_only_missing_sha_keys"] == 0),
        ("ml_eligible_rows", int(eligible.sum()), args.expected_eligible_rows, int(eligible.sum()) == args.expected_eligible_rows),
        ("ml_eligible_unique_files", eligible_unique, args.expected_eligible_unique_files, eligible_unique == args.expected_eligible_unique_files),
        ("ml_above_threshold_rows", int(above.sum()), args.expected_above_rows, int(above.sum()) == args.expected_above_rows),
        ("ml_above_threshold_unique_files", above_unique, args.expected_above_unique_files, above_unique == args.expected_above_unique_files),
        ("ml_below_threshold_rows", int(below.sum()), args.expected_below_rows, int(below.sum()) == args.expected_below_rows),
        ("ml_below_threshold_unique_files", below_unique, args.expected_below_unique_files, below_unique == args.expected_below_unique_files),
        ("ml_above_threshold_issue_stock", above_issue_stock, args.expected_above_issue_stock, np.isclose(above_issue_stock, args.expected_above_issue_stock, atol=1e-9, rtol=0)),
        ("d05_primary_reproduction_failures", int((reproduction_audit["status"] != "pass").sum()), 0, (reproduction_audit["status"] == "pass").all()),
        ("eligible_count_identity_failures", int((~eligible_count_identity).sum()), 0, eligible_count_identity.all()),
        ("eligible_issue_identity_failures", int((~eligible_issue_identity).sum()), 0, eligible_issue_identity.all()),
        ("all_count_identity_failures", int((~all_count_identity).sum()), 0, all_count_identity.all()),
        ("all_issue_identity_failures", int((~all_issue_identity).sum()), 0, all_issue_identity.all()),
        ("b06_file_count_identity_failures", int((~b06_file_count_identity).sum()), 0, b06_file_count_identity.all()),
    ]
    qc = pd.DataFrame([
        {"check": name, "observed": observed, "expected": expected, "status": "pass" if status else "fail"}
        for name, observed, expected, status in qc_rows
    ])
    if (qc["status"] == "fail").any():
        abort("G04 hard QC failed: " + ", ".join(qc.loc[qc["status"] == "fail", "check"].astype(str)))

    output_panel = args.output_dir / "ml_below_threshold_repo_month_panel.csv.gz"
    output_support = args.output_dir / "ml_below_threshold_support.csv"
    output_repro = args.output_dir / "ml_below_threshold_reproduction_audit.csv"
    output_qc = args.output_dir / "ml_below_threshold_qc.csv"
    output_meta = args.output_dir / "ml_below_threshold_metadata.csv"

    panel.to_csv(output_panel, index=False, compression="gzip")
    support.to_csv(output_support, index=False)
    reproduction_audit.to_csv(output_repro, index=False)
    qc.to_csv(output_qc, index=False)

    metadata = pd.DataFrame([
        ("run", "experiment", EXPERIMENT_NAME),
        ("run", "implementation_version", IMPLEMENTATION_VERSION),
        ("input", "a04_file", str(args.a04_file)),
        ("input", "a04_sha256", sha256_file(args.a04_file)),
        ("input", "d02_file", str(args.d02_file)),
        ("input", "d02_sha256", sha256_file(args.d02_file)),
        ("input", "b06_file", str(args.b06_file)),
        ("input", "b06_sha256", sha256_file(args.b06_file)),
        ("input", "d05_reference_file", str(args.d05_reference_file)),
        ("input", "d05_reference_sha256", sha256_file(args.d05_reference_file)),
        ("definition", "ml_metric", ML_METRIC),
        ("definition", "ml_threshold", ML_THRESHOLD),
        ("definition", "eligibility_rule", "finite token-weighted ML AGC share"),
        ("definition", "above_rule", "finite weighted ML AGC share > 0.50"),
        ("definition", "below_rule", "finite weighted ML AGC share <= 0.50"),
        ("definition", "unclassified_rule", "weighted ML AGC share missing or non-finite; excluded from G04 subset"),
        ("identity", "file_identity", "snapshot_id + relative_path + file_sha256; missing SHA preserved and matched by explicit sentinel after snapshot/path audit"),
        ("identity", "a04_missing_file_sha256_files", missing_sha_audit["a04_missing_sha_files"]),
        ("identity", "d02_missing_file_sha256_files", missing_sha_audit["d02_missing_sha_files"]),
        ("identity", "missing_sha_key_mismatches", missing_sha_audit["d02_only_missing_sha_keys"] + missing_sha_audit["a04_only_missing_sha_keys"]),
        ("output", "downstream_experiment", "run-x-g05"),
        ("output", "g05_quality_column", "log1p_selected_issue_total"),
        ("output", "g05_file_count_column", "selected_file_rows"),
        ("output", "g05_issue_count_column", "selected_issue_total"),
        ("audit", "b06_issue_total_policy", "audit-only because D02 canonical alias policy differs from B06 whole-snapshot aggregation"),
        ("audit", "b06_issue_mismatch_repo_months", b06_issue_mismatch_rows),
        ("audit", "b06_minus_d02_issue_stock", b06_issue_delta_sum),
        ("support", "eligible_issue_stock", eligible_issue_stock),
        ("support", "above_issue_stock", above_issue_stock),
        ("support", "below_issue_stock", below_issue_stock),
        ("support", "unclassified_issue_stock", unclassified_issue_stock),
        ("support", "below_unique_historical_files", below_unique),
        ("support", "below_zero_burden_repo_month_share", below_zero_share),
        ("support", "below_within_quality_variation_repositories", below_variation_repos),
    ], columns=["section", "metric", "value"])
    metadata.to_csv(output_meta, index=False)

    print("run-x-g04 ML below-threshold GMM input: PASS")
    print(f"All expanded file rows: {len(base)}")
    print(f"Finite-ML-share eligible rows: {int(eligible.sum())}")
    print(f"Above-threshold rows: {int(above.sum())}")
    print(f"Below-threshold rows: {int(below.sum())}")
    print(f"Unclassified rows: {int(unclassified.sum())}")
    print(f"A04/D02 missing file_sha256 files: {missing_sha_audit['a04_missing_sha_files']}/{missing_sha_audit['d02_missing_sha_files']} (identity mismatches=0)")
    print(f"Eligible unique historical files: {eligible_unique}")
    print(f"Above-threshold unique historical files: {above_unique}")
    print(f"Below-threshold unique historical files: {below_unique}")
    print(f"Above-threshold issue stock: {above_issue_stock:.0f}")
    print(f"Below-threshold issue stock: {below_issue_stock:.0f}")
    print(f"Below-threshold zero-burden repo-month share: {below_zero_share:.6f}")
    print(f"Below-threshold within-quality-variation repositories: {below_variation_repos}")
    print(f"B06-D02 issue-stock delta: {b06_issue_delta_sum:.0f} across {b06_issue_mismatch_rows} repo-months (audit-only)")
    print(f"Output panel: {output_panel}")


if __name__ == "__main__":
    main()
