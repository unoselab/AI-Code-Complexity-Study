#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2d: Check Python merged SonarQube matched panels
# ============================================================
#
# Purpose:
#   Check merged Python SonarQube panels created by run-py-2c.
#
# Current naming convention:
#   strict:
#     repo_python/did_final/panel_event_matched_strict_with_sonarqube.csv
#
#   flexible:
#     repo_python/did_final/panel_event_matched_flexible_with_sonarqube.csv
#
# Supported PANEL_VARIANT values:
#   strict
#   flexible
#   all
#
# Usage:
#   PANEL_VARIANT=strict bash run-py-2d-check-sonarqube-panels.sh
#   PANEL_VARIANT=flexible bash run-py-2d-check-sonarqube-panels.sh
#   PANEL_VARIANT=all      bash run-py-2d-check-sonarqube-panels.sh
#
# Outputs:
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube_check_summary.csv
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube_missing_analysis_outcomes.csv
#   repo_python/did_final/sonarqube_panel_check_manifest_<variant>_<timestamp>.csv
#   repo_python/did_final/sonarqube_panel_check_summary_<variant>.csv
#   repo_python/did_final/sonarqube_panel_check_qc_<variant>.csv
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2d_check_sonarqube_panels_${PANEL_VARIANT}_${RUN_TS}.log}"

DID_DIR="${DID_DIR:-repo_python/did_final}"
CHECK_SCRIPT="${CHECK_SCRIPT:-proc_scripts/check_sonarqube_panel.py}"

MANIFEST_FILE="${DID_DIR}/sonarqube_panel_check_manifest_${PANEL_VARIANT}_${RUN_TS}.csv"
COMBINED_SUMMARY="${DID_DIR}/sonarqube_panel_check_summary_${PANEL_VARIANT}.csv"
COMBINED_QC="${DID_DIR}/sonarqube_panel_check_qc_${PANEL_VARIANT}.csv"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${DID_DIR}/panel_event_matched_strict_with_sonarqube.csv")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${DID_DIR}/panel_event_matched_flexible_with_sonarqube.csv")
fi

mkdir -p "${LOG_DIR}" "${DID_DIR}"

{
  echo "============================================================"
  echo "run-py-2d: check Python merged SonarQube panels"
  echo "Started:          $(date)"
  echo "Panel variant:    ${PANEL_VARIANT}"
  echo "Checker script:   ${CHECK_SCRIPT}"
  echo "DID dir:          ${DID_DIR}"
  echo "Manifest:         ${MANIFEST_FILE}"
  echo "Combined summary: ${COMBINED_SUMMARY}"
  echo "Combined QC:      ${COMBINED_QC}"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${CHECK_SCRIPT}" ]]; then
    echo "ERROR: checker script not found: ${CHECK_SCRIPT}"
    exit 1
  fi

  python -m py_compile "${CHECK_SCRIPT}"

  echo "panel,input,summary,missing" > "${MANIFEST_FILE}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: input panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      echo
      echo "If this is flexible, first finish:"
      echo "  1. flexible treatment/control SonarQube scan"
      echo "  2. PANEL_VARIANT=flexible bash run-py-2c-merge-sonarqube-panel.sh"
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
  echo "** Building combined run-py-2d summaries"
  echo "------------------------------------------------------------"

  python - <<PY
from pathlib import Path
import pandas as pd

manifest_path = Path("${MANIFEST_FILE}")
combined_summary_path = Path("${COMBINED_SUMMARY}")
combined_qc_path = Path("${COMBINED_QC}")

manifest = pd.read_csv(manifest_path)

summary_frames = []
qc_rows = []

def read_csv_if_possible(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()

for _, row in manifest.iterrows():
    panel = row["panel"]
    input_file = Path(row["input"])
    summary_file = Path(row["summary"])
    missing_file = Path(row["missing"])

    summary = read_csv_if_possible(summary_file)
    if not summary.empty:
        summary.insert(0, "panel", panel)
        summary_frames.append(summary)

    missing = read_csv_if_possible(missing_file)

    input_df = pd.read_csv(input_file)
    qc_rows.append({
        "panel": panel,
        "input_file": str(input_file),
        "rows": len(input_df),
        "repos": input_df["repo_name"].nunique() if "repo_name" in input_df.columns else None,
        "treatment_rows": int((input_df["dataset_source"] == "treatment").sum()) if "dataset_source" in input_df.columns else None,
        "control_rows": int((input_df["dataset_source"] == "control").sum()) if "dataset_source" in input_df.columns else None,
        "missing_analysis_rows": len(missing),
        "missing_analysis_repos": missing["repo_name"].nunique() if "repo_name" in missing.columns else 0,
        "missing_output_file": str(missing_file),
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

print("Saved combined summary:", combined_summary_path)
print("Saved combined QC:", combined_qc_path)
print()
print("Combined QC:")
print(combined_qc.to_string(index=False))
PY

  echo
  echo "============================================================"
  echo "run-py-2d completed successfully."
  echo "Completed:        $(date)"
  echo "Panel variant:    ${PANEL_VARIANT}"
  echo "Manifest:         ${MANIFEST_FILE}"
  echo "Combined summary: ${COMBINED_SUMMARY}"
  echo "Combined QC:      ${COMBINED_QC}"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9d-check-sonarqube-panels.sh,
# but it does NOT call the existing JS/TS shell wrapper.
