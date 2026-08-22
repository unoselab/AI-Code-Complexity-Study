#!/usr/bin/env python3
"""Prepare Sankey-style detector-mapping inputs for run-x-f06.

The target figure follows the visual logic of a Sankey mapping: categories from
AGCDetector_NPR are placed on the left, categories from AGCDetector_ML are
placed on the right, and flow width represents the number of repo-month Python
file occurrences.

The figure universe is the inclusive union of files selected by either frozen
primary detector definition:

    NPR selected: finite file_npr_fun_space_by_token_weighted > 1.571637
    ML selected: scored file_ml_agc_share_space_by_token_weighted > 0.50
    Figure universe: NPR selected OR ML selected

Within this universe, there are exactly three non-empty mappings:

    NPR detected     -> ML detected      : intersection / both
    NPR detected     -> ML not detected  : NPR-only
    NPR not detected -> ML detected      : ML-only

The "neither" category is intentionally excluded from the Sankey universe so
that the large background of files not selected by either detector does not
visually dominate the detector-overlap relationship. The complete D02/A04 file
universe is still audited and reported in metadata.

Counting unit
-------------
The primary Sankey value is an expanded repo-month historical-file occurrence.
A historical file appearing in multiple repo-month snapshots contributes once
per repo-month occurrence. This matches the longitudinal panel semantics used
by the run-x-e experiments. Unique historical-file counts and SonarQube issue
stock are also exported as secondary measures.

Inputs
------
D02:
    Canonical repo-month/file SonarQube burden table containing the frozen NPR
    file metric and exact historical-file identity.
A04:
    Frozen ML file-score table containing the file-level weighted AGC share.
B06:
    Authoritative 1,954-row repo-month panel used to attach repo/month labels
    and guarantee the same longitudinal panel universe.
D03 reference:
    Frozen NPR primary repo-month panel used for exact reproduction before any
    figure input is accepted.
D05 reference:
    Frozen ML primary repo-month panel used for exact reproduction before any
    figure input is accepted.

Outputs
-------
agc_detector_mapping_file_occurrences.csv.gz
    One row per union-selected repo-month file occurrence with exact file keys,
    NPR/ML scores, detector flags, mapping class, SonarQube issue burden, and
    repo-month metadata.
agc_detector_mapping_sankey_edges.csv
    Three overall Sankey edges with expanded rows as the primary flow value,
    plus unique-file and issue-stock secondary measures.
agc_detector_mapping_sankey_nodes.csv
    Left/right Sankey nodes and their totals within the union universe.
agc_detector_mapping_repo_month_edges.csv.gz
    Repo-month-specific Sankey edges, preserving the longitudinal granularity.
agc_detector_mapping_repo_month_summary.csv
    One row per B06 repo-month with NPR-only, both, ML-only, union, and overlap
    support counts.
agc_detector_mapping_summary.csv
    Global detector overlap/support summary.
agc_detector_mapping_reproduction_audit.csv
    Exact D03 NPR-primary and D05 ML-primary reproduction checks.
agc_detector_mapping_join_audit.csv
    Exact D02/A04 file-universe join diagnostics.
agc_detector_mapping_qc.csv
    Hard implementation and expected-support checks.
agc_detector_mapping_metadata.csv
    Frozen figure definitions, thresholds, counting unit, and provenance.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

IMPLEMENTATION_VERSION = "v2"
EXPERIMENT_NAME = "run-x-f06-prepare-detector-mapping-figure"

NPR_METRIC = "file_npr_fun_space_by_token_weighted"
NPR_THRESHOLD = 1.571637
ML_METRIC = "file_ml_agc_share_space_by_token_weighted"
ML_THRESHOLD = 0.50

FILE_KEYS = ("snapshot_id", "relative_path", "file_sha256")
REPO_TIME_KEYS = ("repo_id", "time_index")

EXPECTED_NPR_EXPANDED = 13739
EXPECTED_ML_EXPANDED = 43325
EXPECTED_BOTH_EXPANDED = 3619
EXPECTED_NPR_ONLY_EXPANDED = 10120
EXPECTED_ML_ONLY_EXPANDED = 39706
EXPECTED_UNION_EXPANDED = 53445

EXPECTED_NPR_UNIQUE = 12672
EXPECTED_ML_UNIQUE = 41905
EXPECTED_BOTH_UNIQUE = 3375
EXPECTED_NPR_ONLY_UNIQUE = 9297
EXPECTED_ML_ONLY_UNIQUE = 38530
EXPECTED_UNION_UNIQUE = 51202

EXPECTED_NPR_ISSUES = 20306.0
EXPECTED_ML_ISSUES = 48478.0
EXPECTED_BOTH_ISSUES = 3883.0
EXPECTED_NPR_ONLY_ISSUES = 16423.0
EXPECTED_ML_ONLY_ISSUES = 44595.0
EXPECTED_UNION_ISSUES = 64901.0


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


def infer_ml_scored_mask(frame: pd.DataFrame) -> pd.Series:
    if "ml_fun_status" in frame.columns:
        return frame["ml_fun_status"].astype(str).eq("scored")
    if "file_ml_fun_status" in frame.columns:
        return frame["file_ml_fun_status"].astype(str).eq("scored")
    return pd.to_numeric(frame[ML_METRIC], errors="coerce").notna()


def extract_reference(
    frame: pd.DataFrame,
    label: str,
    filters: dict[str, object],
    threshold_filter: float | None = None,
) -> pd.DataFrame:
    data = frame.copy()
    for column, value in filters.items():
        if column not in data.columns:
            abort(f"{label} is missing filter column {column}")
        data = data.loc[data[column].astype(str) == str(value)].copy()

    if threshold_filter is not None:
        threshold_column = None
        for candidate in ("threshold", "threshold_value", "npr_threshold"):
            if candidate in data.columns:
                threshold_column = candidate
                break
        if threshold_column is None:
            abort(f"{label} does not expose an NPR threshold column")
        values = pd.to_numeric(data[threshold_column], errors="coerce")
        data = data.loc[np.isclose(values, threshold_filter, atol=1e-12, rtol=0)].copy()

    if data.empty:
        abort(f"{label} reference filter produced zero rows")

    if "selected_file_rows" not in data.columns:
        if "selected_file_count" in data.columns:
            data["selected_file_rows"] = data["selected_file_count"]
        else:
            abort(f"{label} is missing selected_file_rows/selected_file_count")

    require_columns(
        data,
        ["repo_id", "time_index", "selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"],
        label,
    )
    data = normalize_repo_time_keys(data, label)
    for column in ("selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"):
        data[column] = pd.to_numeric(data[column], errors="raise")
    if data.duplicated(list(REPO_TIME_KEYS)).any():
        abort(f"{label} reference contains duplicate repo-month keys")

    return data[list(REPO_TIME_KEYS) + ["selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"]]


def compare_reproduction(
    reference: pd.DataFrame,
    reconstructed: pd.DataFrame,
    detector: str,
) -> pd.DataFrame:
    check = reference.merge(
        reconstructed[list(REPO_TIME_KEYS) + ["selected_file_rows", "selected_issue_total", "log1p_selected_issue_total"]],
        on=list(REPO_TIME_KEYS),
        how="outer",
        suffixes=("_reference", "_new"),
        indicator=True,
        validate="one_to_one",
    )
    key_mismatch = int((check["_merge"] != "both").sum())
    row_mismatch = int(
        (~np.isclose(
            check["selected_file_rows_reference"],
            check["selected_file_rows_new"],
            atol=0,
            rtol=0,
            equal_nan=False,
        )).sum()
    )
    issue_mismatch = int(
        (~np.isclose(
            check["selected_issue_total_reference"],
            check["selected_issue_total_new"],
            atol=1e-9,
            rtol=0,
            equal_nan=False,
        )).sum()
    )
    log_mismatch = int(
        (~np.isclose(
            check["log1p_selected_issue_total_reference"],
            check["log1p_selected_issue_total_new"],
            atol=1e-12,
            rtol=0,
            equal_nan=False,
        )).sum()
    )
    return pd.DataFrame(
        [
            {
                "detector": detector,
                "reference_rows": len(reference),
                "new_rows": len(reconstructed),
                "key_mismatches": key_mismatch,
                "selected_file_row_mismatches": row_mismatch,
                "selected_issue_total_mismatches": issue_mismatch,
                "log1p_mismatches": log_mismatch,
                "status": "pass" if (key_mismatch + row_mismatch + issue_mismatch + log_mismatch) == 0 else "fail",
            }
        ]
    )


def aggregate_repo_month(frame: pd.DataFrame, mask: pd.Series, prefix: str) -> pd.DataFrame:
    selected = frame.loc[mask, ["repo_id", "time_index", "sonar_issue_total"]].copy()
    if selected.empty:
        return pd.DataFrame(columns=["repo_id", "time_index", f"{prefix}_file_rows", f"{prefix}_issue_total"])
    return selected.groupby(["repo_id", "time_index"], as_index=False).agg(
        **{
            f"{prefix}_file_rows": ("sonar_issue_total", "size"),
            f"{prefix}_issue_total": ("sonar_issue_total", "sum"),
        }
    )


def unique_file_count(frame: pd.DataFrame) -> int:
    return int(frame[list(FILE_KEYS)].drop_duplicates().shape[0])


def edge_row(
    frame: pd.DataFrame,
    mapping_class: str,
    source: str,
    target: str,
    order: int,
) -> dict[str, object]:
    part = frame.loc[frame["mapping_class"] == mapping_class]
    return {
        "edge_order": order,
        "source": source,
        "target": target,
        "mapping_class": mapping_class,
        "file_occurrences": int(len(part)),
        "unique_historical_files": unique_file_count(part),
        "issue_stock": float(part["sonar_issue_total"].sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--d02-file", required=True, type=Path)
    parser.add_argument("--a04-file", required=True, type=Path)
    parser.add_argument("--b06-file", required=True, type=Path)
    parser.add_argument("--d03-reference-file", required=True, type=Path)
    parser.add_argument("--d05-reference-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-d02-rows", type=int, default=510297)
    parser.add_argument("--expected-a04-rows", type=int, default=494592)
    parser.add_argument("--expected-b06-rows", type=int, default=1954)
    args = parser.parse_args()

    for path in (
        args.d02_file,
        args.a04_file,
        args.b06_file,
        args.d03_reference_file,
        args.d05_reference_file,
    ):
        if not path.is_file():
            abort(f"Required input does not exist: {path}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading D02 canonical file burden: {args.d02_file}")
    d02 = normalize_repo_time_keys(read_table(args.d02_file), "D02")
    print(f"Reading A04 frozen ML file scores: {args.a04_file}")
    a04 = read_table(args.a04_file)
    print(f"Reading B06 authoritative panel: {args.b06_file}")
    b06 = normalize_repo_time_keys(read_table(args.b06_file), "B06")
    print(f"Reading D03 NPR reference: {args.d03_reference_file}")
    d03 = read_table(args.d03_reference_file)
    print(f"Reading D05 ML reference: {args.d05_reference_file}")
    d05 = read_table(args.d05_reference_file)

    if len(d02) != args.expected_d02_rows:
        abort(f"D02 row mismatch: expected {args.expected_d02_rows}, observed {len(d02)}")
    if len(a04) != args.expected_a04_rows:
        abort(f"A04 row mismatch: expected {args.expected_a04_rows}, observed {len(a04)}")
    if len(b06) != args.expected_b06_rows:
        abort(f"B06 row mismatch: expected {args.expected_b06_rows}, observed {len(b06)}")

    require_columns(d02, list(FILE_KEYS) + [NPR_METRIC, "sonar_issue_total"], "D02")
    require_columns(a04, list(FILE_KEYS) + [ML_METRIC], "A04")
    if a04.duplicated(list(FILE_KEYS)).any():
        abort("A04 must contain one row per exact snapshot/file identity")
    if b06.duplicated(list(REPO_TIME_KEYS)).any():
        abort("B06 contains duplicate repo-month keys")

    d02["sonar_issue_total"] = pd.to_numeric(d02["sonar_issue_total"], errors="raise")
    d02[NPR_METRIC] = pd.to_numeric(d02[NPR_METRIC], errors="coerce")
    if d02["sonar_issue_total"].isna().any() or (d02["sonar_issue_total"] < 0).any():
        abort("D02 sonar_issue_total must be complete and non-negative")

    a04_columns = list(FILE_KEYS) + [ML_METRIC]
    for optional in ("ml_fun_status", "file_ml_fun_status"):
        if optional in a04.columns:
            a04_columns.append(optional)
    a04_small = a04[a04_columns].copy()
    a04_small[ML_METRIC] = pd.to_numeric(a04_small[ML_METRIC], errors="coerce")

    merged = d02.merge(a04_small, on=list(FILE_KEYS), how="left", validate="many_to_one", indicator=True)
    joined_rows = int((merged["_merge"] == "both").sum())
    d02_only_rows = int((merged["_merge"] == "left_only").sum())
    merged.drop(columns=["_merge"], inplace=True)

    unique_d02_files = d02[list(FILE_KEYS)].drop_duplicates()
    unique_a04_files = a04[list(FILE_KEYS)].drop_duplicates()
    file_universe = unique_d02_files.merge(unique_a04_files, on=list(FILE_KEYS), how="outer", indicator=True)
    d02_unique_only = int((file_universe["_merge"] == "left_only").sum())
    a04_unique_only = int((file_universe["_merge"] == "right_only").sum())
    exact_unique_files = int((file_universe["_merge"] == "both").sum())

    if d02_only_rows != 0 or d02_unique_only != 0 or a04_unique_only != 0:
        abort(
            "D02 and A04 exact file universes do not reconcile: "
            f"expanded_d02_only={d02_only_rows}, unique_d02_only={d02_unique_only}, unique_a04_only={a04_unique_only}"
        )

    ml_scored = infer_ml_scored_mask(merged)
    npr_eligible = merged[NPR_METRIC].notna() & np.isfinite(merged[NPR_METRIC])
    npr_selected = npr_eligible & (merged[NPR_METRIC] > NPR_THRESHOLD)
    ml_selected = ml_scored & (merged[ML_METRIC] > ML_THRESHOLD)
    both_selected = npr_selected & ml_selected
    npr_only = npr_selected & ~ml_selected
    ml_only = ml_selected & ~npr_selected
    union_selected = npr_selected | ml_selected

    # Build the zero-inclusive repo-month support table first. This is also used
    # to reproduce the frozen D03 and D05 detector-specific panels.
    panel_keys = b06[["repo_id", "time_index"]].copy()
    for prefix, mask in {
        "npr_selected": npr_selected,
        "ml_selected": ml_selected,
        "intersection_selected": both_selected,
        "npr_only": npr_only,
        "ml_only": ml_only,
        "union_selected": union_selected,
    }.items():
        agg = aggregate_repo_month(merged, mask, prefix)
        panel_keys = panel_keys.merge(agg, on=list(REPO_TIME_KEYS), how="left", validate="one_to_one")
        panel_keys[f"{prefix}_file_rows"] = panel_keys[f"{prefix}_file_rows"].fillna(0).astype(int)
        panel_keys[f"{prefix}_issue_total"] = panel_keys[f"{prefix}_issue_total"].fillna(0.0)

    npr_reconstructed = panel_keys[
        ["repo_id", "time_index", "npr_selected_file_rows", "npr_selected_issue_total"]
    ].rename(
        columns={
            "npr_selected_file_rows": "selected_file_rows",
            "npr_selected_issue_total": "selected_issue_total",
        }
    )
    npr_reconstructed["log1p_selected_issue_total"] = np.log1p(npr_reconstructed["selected_issue_total"])

    ml_reconstructed = panel_keys[
        ["repo_id", "time_index", "ml_selected_file_rows", "ml_selected_issue_total"]
    ].rename(
        columns={
            "ml_selected_file_rows": "selected_file_rows",
            "ml_selected_issue_total": "selected_issue_total",
        }
    )
    ml_reconstructed["log1p_selected_issue_total"] = np.log1p(ml_reconstructed["selected_issue_total"])

    npr_reference = extract_reference(d03, "D03", {"sample_spec": "full_sample"}, threshold_filter=NPR_THRESHOLD)
    ml_reference = extract_reference(d05, "D05", {"sample_spec": "full_sample", "mapping_spec": "all_ml_files"})
    reproduction_audit = pd.concat(
        [
            compare_reproduction(npr_reference, npr_reconstructed, "NPR"),
            compare_reproduction(ml_reference, ml_reconstructed, "ML"),
        ],
        ignore_index=True,
    )
    if not (reproduction_audit["status"] == "pass").all():
        abort("Detector-only reproduction failed; mapping figure inputs are not trusted")

    # Keep only the union universe for the Sankey. The row-level output retains
    # exact detector scores and identities for later visual/QC work.
    union_files = merged.loc[union_selected].copy()
    union_files["npr_selected"] = npr_selected.loc[union_selected].astype(int).to_numpy()
    union_files["ml_selected"] = ml_selected.loc[union_selected].astype(int).to_numpy()
    union_files["mapping_class"] = np.select(
        [
            (union_files["npr_selected"] == 1) & (union_files["ml_selected"] == 1),
            (union_files["npr_selected"] == 1) & (union_files["ml_selected"] == 0),
            (union_files["npr_selected"] == 0) & (union_files["ml_selected"] == 1),
        ],
        ["Both", "NPR-only", "ML-only"],
        default="INVALID",
    )
    if (union_files["mapping_class"] == "INVALID").any():
        abort("Invalid union mapping class encountered")

    union_files["sankey_source"] = np.where(
        union_files["npr_selected"] == 1,
        "Detected by AGCDetector_NPR",
        "Not detected by AGCDetector_NPR",
    )
    union_files["sankey_target"] = np.where(
        union_files["ml_selected"] == 1,
        "Detected by AGCDetector_ML",
        "Not detected by AGCDetector_ML",
    )

    # Attach human-readable repo/month metadata from the authoritative B06 panel.
    b06_meta_columns = ["repo_id", "time_index"]
    for candidate in ("repo_name", "time", "dataset_source", "scope_role", "treatment_group"):
        if candidate in b06.columns:
            b06_meta_columns.append(candidate)
    b06_meta = b06[b06_meta_columns].copy()

    # D02 may already carry repo/month metadata such as repo_name. If those
    # columns are left in union_files, pandas adds _x/_y suffixes during the
    # B06 merge and the canonical unsuffixed column disappears. Drop only the
    # overlapping non-key metadata columns first so B06 remains authoritative.
    overlapping_metadata = [
        column
        for column in b06_meta_columns
        if column not in REPO_TIME_KEYS and column in union_files.columns
    ]
    if overlapping_metadata:
        union_files = union_files.drop(columns=overlapping_metadata)

    union_files = union_files.merge(
        b06_meta,
        on=list(REPO_TIME_KEYS),
        how="left",
        validate="many_to_one",
    )
    if "repo_name" in b06_meta.columns:
        if "repo_name" not in union_files.columns:
            abort("B06 repo_name metadata was not attached with its canonical column name")
        if union_files["repo_name"].isna().any():
            abort("Failed to attach B06 repo metadata to union-selected file occurrences")

    # Overall three-edge Sankey input. Expanded file occurrences are the primary
    # flow width; unique files and issue stock are retained for labels/tooltips.
    edges = pd.DataFrame(
        [
            edge_row(
                union_files,
                "Both",
                "Detected by AGCDetector_NPR",
                "Detected by AGCDetector_ML",
                1,
            ),
            edge_row(
                union_files,
                "NPR-only",
                "Detected by AGCDetector_NPR",
                "Not detected by AGCDetector_ML",
                2,
            ),
            edge_row(
                union_files,
                "ML-only",
                "Not detected by AGCDetector_NPR",
                "Detected by AGCDetector_ML",
                3,
            ),
        ]
    )
    edges["share_of_union_file_occurrences"] = edges["file_occurrences"] / float(len(union_files))
    edges["share_of_union_issue_stock"] = edges["issue_stock"] / float(union_files["sonar_issue_total"].sum())
    edges["primary_flow_value"] = edges["file_occurrences"]
    edges["primary_flow_unit"] = "repo_month_file_occurrences"

    # Sankey node totals are computed within the union universe, so the left and
    # right side each sum to the same union total.
    node_rows: list[dict[str, object]] = []
    for node_order, (side, node, mask) in enumerate(
        [
            ("left", "Detected by AGCDetector_NPR", union_files["npr_selected"] == 1),
            ("left", "Not detected by AGCDetector_NPR", union_files["npr_selected"] == 0),
            ("right", "Detected by AGCDetector_ML", union_files["ml_selected"] == 1),
            ("right", "Not detected by AGCDetector_ML", union_files["ml_selected"] == 0),
        ],
        start=1,
    ):
        part = union_files.loc[mask]
        node_rows.append(
            {
                "node_order": node_order,
                "side": side,
                "node": node,
                "file_occurrences": int(len(part)),
                "unique_historical_files": unique_file_count(part),
                "issue_stock": float(part["sonar_issue_total"].sum()),
            }
        )
    nodes = pd.DataFrame(node_rows)

    # Repo-month summary preserves all 1,954 months, including months with no
    # selected files. This makes the prepared data reusable for later temporal
    # or treatment/control detector-overlap figures.
    repo_month_summary = panel_keys.copy()
    repo_month_summary["union_jaccard_npr_ml"] = np.where(
        repo_month_summary["union_selected_file_rows"] > 0,
        repo_month_summary["intersection_selected_file_rows"] / repo_month_summary["union_selected_file_rows"],
        np.nan,
    )
    repo_month_summary = repo_month_summary.merge(b06_meta, on=list(REPO_TIME_KEYS), how="left", validate="one_to_one")

    repo_month_edge_parts: list[pd.DataFrame] = []
    class_to_nodes = {
        "Both": ("Detected by AGCDetector_NPR", "Detected by AGCDetector_ML"),
        "NPR-only": ("Detected by AGCDetector_NPR", "Not detected by AGCDetector_ML"),
        "ML-only": ("Not detected by AGCDetector_NPR", "Detected by AGCDetector_ML"),
    }
    for mapping_class, (source, target) in class_to_nodes.items():
        part = union_files.loc[union_files["mapping_class"] == mapping_class]
        grouped = part.groupby(["repo_id", "time_index"], as_index=False).agg(
            file_occurrences=("sonar_issue_total", "size"),
            issue_stock=("sonar_issue_total", "sum"),
        )
        grouped["mapping_class"] = mapping_class
        grouped["source"] = source
        grouped["target"] = target
        repo_month_edge_parts.append(grouped)
    repo_month_edges = pd.concat(repo_month_edge_parts, ignore_index=True)
    repo_month_edges = repo_month_edges.merge(b06_meta, on=list(REPO_TIME_KEYS), how="left", validate="many_to_one")
    repo_month_edges.sort_values(["repo_id", "time_index", "mapping_class"], inplace=True, ignore_index=True)

    # Global support summary contains both the selected detector sets and the
    # disjoint classes used by the figure.
    support_masks = {
        "NPR selected": npr_selected,
        "ML selected": ml_selected,
        "Both": both_selected,
        "NPR-only": npr_only,
        "ML-only": ml_only,
        "Union": union_selected,
    }
    summary_rows: list[dict[str, object]] = []
    for selection, mask in support_masks.items():
        part = merged.loc[mask]
        summary_rows.append(
            {
                "selection": selection,
                "file_occurrences": int(mask.sum()),
                "unique_historical_files": unique_file_count(part),
                "issue_stock": float(part["sonar_issue_total"].sum()),
            }
        )
    summary = pd.DataFrame(summary_rows)
    summary["jaccard_npr_ml"] = EXPECTED_BOTH_EXPANDED / EXPECTED_UNION_EXPANDED
    summary["npr_overlap_share"] = EXPECTED_BOTH_EXPANDED / EXPECTED_NPR_EXPANDED
    summary["ml_overlap_share"] = EXPECTED_BOTH_EXPANDED / EXPECTED_ML_EXPANDED

    expected_support = {
        "NPR selected": (EXPECTED_NPR_EXPANDED, EXPECTED_NPR_UNIQUE, EXPECTED_NPR_ISSUES),
        "ML selected": (EXPECTED_ML_EXPANDED, EXPECTED_ML_UNIQUE, EXPECTED_ML_ISSUES),
        "Both": (EXPECTED_BOTH_EXPANDED, EXPECTED_BOTH_UNIQUE, EXPECTED_BOTH_ISSUES),
        "NPR-only": (EXPECTED_NPR_ONLY_EXPANDED, EXPECTED_NPR_ONLY_UNIQUE, EXPECTED_NPR_ONLY_ISSUES),
        "ML-only": (EXPECTED_ML_ONLY_EXPANDED, EXPECTED_ML_ONLY_UNIQUE, EXPECTED_ML_ONLY_ISSUES),
        "Union": (EXPECTED_UNION_EXPANDED, EXPECTED_UNION_UNIQUE, EXPECTED_UNION_ISSUES),
    }

    qc_rows: list[dict[str, object]] = []
    for selection, (expected_rows, expected_unique, expected_issues) in expected_support.items():
        row = summary.loc[summary["selection"] == selection].iloc[0]
        for suffix, observed, expected, tolerance in (
            ("file_occurrences", int(row["file_occurrences"]), expected_rows, 0),
            ("unique_historical_files", int(row["unique_historical_files"]), expected_unique, 0),
            ("issue_stock", float(row["issue_stock"]), expected_issues, 1e-9),
        ):
            passed = abs(float(observed) - float(expected)) <= tolerance
            qc_rows.append(
                {
                    "check": f"{selection.lower().replace(' ', '_').replace('-', '_')}_{suffix}",
                    "observed": observed,
                    "expected": expected,
                    "status": "pass" if passed else "fail",
                }
            )

    structural_checks = [
        ("d03_npr_reproduction_failures", int((reproduction_audit.loc[reproduction_audit["detector"] == "NPR", "status"] != "pass").sum()), 0),
        ("d05_ml_reproduction_failures", int((reproduction_audit.loc[reproduction_audit["detector"] == "ML", "status"] != "pass").sum()), 0),
        ("union_file_occurrence_rows", len(union_files), EXPECTED_UNION_EXPANDED),
        ("sankey_edge_rows", len(edges), 3),
        ("sankey_node_rows", len(nodes), 4),
        ("repo_month_summary_rows", len(repo_month_summary), args.expected_b06_rows),
        ("invalid_mapping_class_rows", int((union_files["mapping_class"] == "INVALID").sum()), 0),
        ("left_node_total_mismatch", int(nodes.loc[nodes["side"] == "left", "file_occurrences"].sum() != len(union_files)), 0),
        ("right_node_total_mismatch", int(nodes.loc[nodes["side"] == "right", "file_occurrences"].sum() != len(union_files)), 0),
        ("edge_total_mismatch", int(edges["file_occurrences"].sum() != len(union_files)), 0),
    ]
    for name, observed, expected in structural_checks:
        qc_rows.append(
            {
                "check": name,
                "observed": observed,
                "expected": expected,
                "status": "pass" if observed == expected else "fail",
            }
        )
    qc = pd.DataFrame(qc_rows)

    join_audit = pd.DataFrame(
        [
            {"check": "d02_rows", "observed": len(d02), "expected": args.expected_d02_rows, "status": "pass" if len(d02) == args.expected_d02_rows else "fail"},
            {"check": "a04_rows", "observed": len(a04), "expected": args.expected_a04_rows, "status": "pass" if len(a04) == args.expected_a04_rows else "fail"},
            {"check": "expanded_d02_rows_joined_to_a04", "observed": joined_rows, "expected": len(d02), "status": "pass" if joined_rows == len(d02) else "fail"},
            {"check": "expanded_d02_rows_missing_a04", "observed": d02_only_rows, "expected": 0, "status": "pass" if d02_only_rows == 0 else "fail"},
            {"check": "unique_d02_files", "observed": len(unique_d02_files), "expected": args.expected_a04_rows, "status": "pass" if len(unique_d02_files) == args.expected_a04_rows else "fail"},
            {"check": "unique_a04_files", "observed": len(unique_a04_files), "expected": args.expected_a04_rows, "status": "pass" if len(unique_a04_files) == args.expected_a04_rows else "fail"},
            {"check": "exact_unique_file_matches", "observed": exact_unique_files, "expected": args.expected_a04_rows, "status": "pass" if exact_unique_files == args.expected_a04_rows else "fail"},
            {"check": "unique_d02_only", "observed": d02_unique_only, "expected": 0, "status": "pass" if d02_unique_only == 0 else "fail"},
            {"check": "unique_a04_only", "observed": a04_unique_only, "expected": 0, "status": "pass" if a04_unique_only == 0 else "fail"},
        ]
    )

    if (qc["status"] != "pass").any() or (join_audit["status"] != "pass").any():
        failed = qc.loc[qc["status"] != "pass", "check"].tolist() + join_audit.loc[join_audit["status"] != "pass", "check"].tolist()
        abort(f"run-x-f06 mapping-input QC failed: {failed}")

    metadata = pd.DataFrame(
        [
            ("run", "experiment", EXPERIMENT_NAME),
            ("run", "implementation_version", IMPLEMENTATION_VERSION),
            ("input", "d02_file", str(args.d02_file)),
            ("input", "d02_sha256", sha256_file(args.d02_file)),
            ("input", "a04_file", str(args.a04_file)),
            ("input", "a04_sha256", sha256_file(args.a04_file)),
            ("input", "b06_file", str(args.b06_file)),
            ("input", "b06_sha256", sha256_file(args.b06_file)),
            ("input", "d03_reference_file", str(args.d03_reference_file)),
            ("input", "d03_reference_sha256", sha256_file(args.d03_reference_file)),
            ("input", "d05_reference_file", str(args.d05_reference_file)),
            ("input", "d05_reference_sha256", sha256_file(args.d05_reference_file)),
            ("definition", "npr_rule", f"finite {NPR_METRIC} > {NPR_THRESHOLD}"),
            ("definition", "ml_rule", f"scored {ML_METRIC} > {ML_THRESHOLD:.2f}"),
            ("definition", "figure_universe", "NPR_selected OR ML_selected"),
            ("definition", "excluded_from_sankey", "files selected by neither detector"),
            ("definition", "primary_flow_measure", "repo-month historical Python file occurrences"),
            ("definition", "file_identity", "snapshot_id + relative_path + file_sha256"),
            ("definition", "mapping_class_1", "Both: NPR selected AND ML selected"),
            ("definition", "mapping_class_2", "NPR-only: NPR selected AND NOT ML selected"),
            ("definition", "mapping_class_3", "ML-only: NOT NPR selected AND ML selected"),
            ("definition", "issue_measure", "unresolved SonarQube issue stock"),
            ("support", "jaccard_npr_ml_expanded", EXPECTED_BOTH_EXPANDED / EXPECTED_UNION_EXPANDED),
            ("support", "npr_overlap_share_expanded", EXPECTED_BOTH_EXPANDED / EXPECTED_NPR_EXPANDED),
            ("support", "ml_overlap_share_expanded", EXPECTED_BOTH_EXPANDED / EXPECTED_ML_EXPANDED),
        ],
        columns=["section", "metric", "value"],
    )

    # Keep a compact, stable set of columns in the row-level figure input.
    row_output_columns = ["repo_id", "time_index"]
    for candidate in ("repo_name", "time", "dataset_source", "scope_role", "treatment_group"):
        if candidate in union_files.columns:
            row_output_columns.append(candidate)
    row_output_columns.extend(
        list(FILE_KEYS)
        + [
            NPR_METRIC,
            ML_METRIC,
            "npr_selected",
            "ml_selected",
            "mapping_class",
            "sankey_source",
            "sankey_target",
            "sonar_issue_total",
        ]
    )
    file_occurrences = union_files[row_output_columns].copy()
    file_occurrences.sort_values(["repo_id", "time_index", "mapping_class", "relative_path"], inplace=True, ignore_index=True)

    output_paths = {
        "file_occurrences": args.output_dir / "agc_detector_mapping_file_occurrences.csv.gz",
        "edges": args.output_dir / "agc_detector_mapping_sankey_edges.csv",
        "nodes": args.output_dir / "agc_detector_mapping_sankey_nodes.csv",
        "repo_month_edges": args.output_dir / "agc_detector_mapping_repo_month_edges.csv.gz",
        "repo_month_summary": args.output_dir / "agc_detector_mapping_repo_month_summary.csv",
        "summary": args.output_dir / "agc_detector_mapping_summary.csv",
        "reproduction": args.output_dir / "agc_detector_mapping_reproduction_audit.csv",
        "join": args.output_dir / "agc_detector_mapping_join_audit.csv",
        "qc": args.output_dir / "agc_detector_mapping_qc.csv",
        "metadata": args.output_dir / "agc_detector_mapping_metadata.csv",
    }

    file_occurrences.to_csv(output_paths["file_occurrences"], index=False, compression="gzip")
    edges.to_csv(output_paths["edges"], index=False)
    nodes.to_csv(output_paths["nodes"], index=False)
    repo_month_edges.to_csv(output_paths["repo_month_edges"], index=False, compression="gzip")
    repo_month_summary.to_csv(output_paths["repo_month_summary"], index=False)
    summary.to_csv(output_paths["summary"], index=False)
    reproduction_audit.to_csv(output_paths["reproduction"], index=False)
    join_audit.to_csv(output_paths["join"], index=False)
    qc.to_csv(output_paths["qc"], index=False)
    metadata.to_csv(output_paths["metadata"], index=False)

    print("run-x-f06 detector-mapping figure inputs: PASS")
    print(f"Figure universe (union) file occurrences: {len(file_occurrences)}")
    for row in edges.itertuples(index=False):
        print(
            f"{row.mapping_class}: {row.source} -> {row.target}; "
            f"file_occurrences={row.file_occurrences}; unique_files={row.unique_historical_files}; issues={row.issue_stock:.0f}"
        )
    print(f"Overall Sankey edges: {output_paths['edges']}")
    print(f"Repo-month edges: {output_paths['repo_month_edges']}")
    print(f"Row-level provenance: {output_paths['file_occurrences']}")


if __name__ == "__main__":
    main()
