#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs

RUN_TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_FILE:-logs/run9d_check_sonarqube_panels_${RUN_TS}.log}"

DID_DIR="${DID_DIR:-tmp_jsts_test/data/jsts_did_final}"
CHECK_SCRIPT="${CHECK_SCRIPT:-proc_scripts/check_sonarqube_panel.py}"

MANIFEST_FILE="${DID_DIR}/sonarqube_panel_check_manifest_${RUN_TS}.csv"
COMBINED_SUMMARY="${DID_DIR}/sonarqube_panel_check_summary_all.csv"
COMBINED_QC="${DID_DIR}/sonarqube_panel_check_qc_all.csv"

PANELS=(
  "main_balanced|${DID_DIR}/panel_event_monthly_matched_final_clean_balanced_with_sonarqube.csv"
  "main_unbalanced|${DID_DIR}/panel_event_monthly_matched_final_clean_with_sonarqube.csv"
  "strict_1to3_balanced|${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_balanced_with_sonarqube.csv"
  "strict_1to3_unbalanced|${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_with_sonarqube.csv"
)

{
  echo "============================================================"
  echo "run9d: check merged JS/TS SonarQube panels"
  echo "Started:          $(date)"
  echo "Checker script:   ${CHECK_SCRIPT}"
  echo "DID dir:          ${DID_DIR}"
  echo "Manifest:         ${MANIFEST_FILE}"
  echo "Combined summary: ${COMBINED_SUMMARY}"
  echo "Combined QC:      ${COMBINED_QC}"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${CHECK_SCRIPT}" ]]; then
    echo "ERROR: Checker script not found: ${CHECK_SCRIPT}"
    exit 1
  fi

  mkdir -p "${DID_DIR}"

  echo "panel,input,summary,missing" > "${MANIFEST_FILE}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: Input panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      exit 1
    fi

    BASE_FILE="${INPUT_FILE%.csv}"
    SUMMARY_OUTPUT="${BASE_FILE}_check_summary.csv"
    MISSING_OUTPUT="${BASE_FILE}_missing_analysis_outcomes.csv"

    echo
    echo "============================================================"
    echo "Checking panel: ${PANEL_LABEL}"
    echo "Input:          ${INPUT_FILE}"
    echo "Summary output: ${SUMMARY_OUTPUT}"
    echo "Missing output: ${MISSING_OUTPUT}"
    echo "============================================================"

    python "${CHECK_SCRIPT}" \
      --input "${INPUT_FILE}" \
      --summary-output "${SUMMARY_OUTPUT}" \
      --missing-output "${MISSING_OUTPUT}"

    printf '%s,%s,%s,%s\n' \
      "${PANEL_LABEL}" \
      "${INPUT_FILE}" \
      "${SUMMARY_OUTPUT}" \
      "${MISSING_OUTPUT}" >> "${MANIFEST_FILE}"
  done

  echo
  echo "** Building combined run9d summaries"
  echo "------------------------------------------------------------"

  python - "${MANIFEST_FILE}" "${COMBINED_SUMMARY}" "${COMBINED_QC}" <<'PY'
import sys
from pathlib import Path

import pandas as pd

manifest_path = Path(sys.argv[1])
combined_summary_path = Path(sys.argv[2])
combined_qc_path = Path(sys.argv[3])

manifest = pd.read_csv(manifest_path)

summary_frames = []
qc_rows = []

def count_if_present(df, col, value=None):
    if col not in df.columns:
        return None
    if value is None:
        return int(df[col].notna().sum())
    return int((df[col] == value).sum())

def sum_if_present(df, col):
    if col not in df.columns:
        return None
    return int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())

for _, row in manifest.iterrows():
    panel = row["panel"]
    input_path = Path(row["input"])
    summary_path = Path(row["summary"])
    missing_path = Path(row["missing"])

    df = pd.read_csv(input_path)

    if summary_path.exists():
        summary = pd.read_csv(summary_path)
        summary.insert(0, "panel", panel)
        summary.insert(1, "input", str(input_path))
        summary_frames.append(summary)

    missing_rows = None
    if missing_path.exists():
        missing_rows = len(pd.read_csv(missing_path))

    duplicate_keys = None
    key_cols = ["repo_name", "time", "dataset_source"]
    if set(key_cols).issubset(df.columns):
        duplicate_keys = int(df.duplicated(key_cols).sum())

    qc_rows.append({
        "panel": panel,
        "input": str(input_path),
        "rows": len(df),
        "repos": df["repo_name"].nunique() if "repo_name" in df.columns else None,
        "treatment_rows": count_if_present(df, "dataset_source", "treatment"),
        "control_rows": count_if_present(df, "dataset_source", "control"),
        "treatment_repos": df.loc[df["dataset_source"] == "treatment", "repo_name"].nunique()
            if {"dataset_source", "repo_name"}.issubset(df.columns) else None,
        "control_repos": df.loc[df["dataset_source"] == "control", "repo_name"].nunique()
            if {"dataset_source", "repo_name"}.issubset(df.columns) else None,
        "months_min": df["time"].min() if "time" in df.columns else None,
        "months_max": df["time"].max() if "time" in df.columns else None,
        "duplicate_repo_time_source_rows": duplicate_keys,
        "missing_rows_from_checker": missing_rows,
        "sonarqube_latest_commit_missing": int(df["sonarqube_latest_commit"].isna().sum())
            if "sonarqube_latest_commit" in df.columns else None,
        "sonarqube_any_raw_metric_missing_rows": sum_if_present(df, "sonarqube_any_raw_metric_missing"),
        "sonarqube_all_raw_metrics_missing_rows": sum_if_present(df, "sonarqube_all_raw_metrics_missing"),
        "sonarqube_ncloc_zero_rows": sum_if_present(df, "sonarqube_ncloc_zero"),
        "sonarqube_static_warnings_missing_rows": sum_if_present(df, "sonarqube_static_warnings_missing"),
        "sonarqube_duplicate_density_missing_rows": sum_if_present(df, "sonarqube_duplicate_density_missing"),
        "sonarqube_cognitive_complexity_missing_rows": sum_if_present(df, "sonarqube_cognitive_complexity_missing"),
        "sonarqube_quality_outcomes_complete_rows": sum_if_present(df, "sonarqube_quality_outcomes_complete"),
        "static_analysis_warnings_nonmissing": count_if_present(df, "static_analysis_warnings"),
        "duplicate_line_density_nonmissing": count_if_present(df, "duplicate_line_density"),
        "code_complexity_nonmissing": count_if_present(df, "code_complexity"),
        "warnings_per_kloc_nonmissing": count_if_present(df, "warnings_per_kloc"),
        "complexity_per_kloc_nonmissing": count_if_present(df, "complexity_per_kloc"),
        "code_smells_per_kloc_nonmissing": count_if_present(df, "code_smells_per_kloc"),
    })

if summary_frames:
    combined_summary = pd.concat(summary_frames, ignore_index=True)
else:
    combined_summary = pd.DataFrame()

combined_qc = pd.DataFrame(qc_rows)

combined_summary_path.parent.mkdir(parents=True, exist_ok=True)
combined_qc_path.parent.mkdir(parents=True, exist_ok=True)

combined_summary.to_csv(combined_summary_path, index=False)
combined_qc.to_csv(combined_qc_path, index=False)

print("Combined QC:")
print(combined_qc.to_string(index=False))
print()
print(f"Saved combined checker summary: {combined_summary_path}")
print(f"Saved combined QC summary: {combined_qc_path}")
PY

  echo
  echo "============================================================"
  echo "run9d completed successfully."
  echo "Completed:        $(date)"
  echo "Combined summary: ${COMBINED_SUMMARY}"
  echo "Combined QC:      ${COMBINED_QC}"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
