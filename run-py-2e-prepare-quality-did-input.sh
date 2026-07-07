#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2e: Prepare Python quality DiD input
# ============================================================
# Purpose:
#   Convert merged Python SonarQube panels into quality DiD input files.
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
#   PANEL_VARIANT=strict bash run-py-2e-prepare-quality-did-input.sh
#   PANEL_VARIANT=flexible bash run-py-2e-prepare-quality-did-input.sh
#   PANEL_VARIANT=all      bash run-py-2e-prepare-quality-did-input.sh
#
# Outputs for each variant:
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube_quality_did_input.csv
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube_quality_did_input_complete.csv
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube_quality_did_input_qc.csv
#   repo_python/did_final/panel_event_matched_<variant>_with_sonarqube_quality_did_input_missing_core_quality.csv
#
# Combined outputs:
#   repo_python/did_final/quality_did_input_manifest_<variant>_<timestamp>.csv
#   repo_python/did_final/quality_did_input_qc_<variant>_long.csv
#   repo_python/did_final/quality_did_input_qc_<variant>_wide.csv
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2e_prepare_quality_did_input_${PANEL_VARIANT}_${RUN_TS}.log}"

DID_DIR="${DID_DIR:-repo_python/did_final}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_quality_did_input_v2.py}"

MANIFEST_FILE="${DID_DIR}/quality_did_input_manifest_${PANEL_VARIANT}_${RUN_TS}.csv"
COMBINED_QC_LONG="${DID_DIR}/quality_did_input_qc_${PANEL_VARIANT}_long.csv"
COMBINED_QC_WIDE="${DID_DIR}/quality_did_input_qc_${PANEL_VARIANT}_wide.csv"

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
  echo "run-py-2e: prepare Python quality DiD input"
  echo "Started:          $(date)"
  echo "Panel variant:    ${PANEL_VARIANT}"
  echo "Python script:    ${PY_SCRIPT}"
  echo "DID dir:          ${DID_DIR}"
  echo "Manifest:         ${MANIFEST_FILE}"
  echo "Combined QC long: ${COMBINED_QC_LONG}"
  echo "Combined QC wide: ${COMBINED_QC_WIDE}"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "ERROR: Python script not found: ${PY_SCRIPT}"
    exit 1
  fi

  python -m py_compile "${PY_SCRIPT}"

  echo "panel,input,output,complete_output,qc_output,missing_output" > "${MANIFEST_FILE}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: input merged SonarQube panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      echo
      echo "If this is flexible, first finish:"
      echo "  1. flexible treatment/control SonarQube scan"
      echo "  2. PANEL_VARIANT=flexible bash run-py-2c-merge-sonarqube-panel.sh"
      echo "  3. PANEL_VARIANT=flexible bash run-py-2d-check-sonarqube-panels.sh"
      exit 1
    fi

    BASE_FILE="${INPUT_FILE%.csv}"
    OUTPUT_FILE="${BASE_FILE}_quality_did_input.csv"
    COMPLETE_OUTPUT_FILE="${BASE_FILE}_quality_did_input_complete.csv"
    QC_OUTPUT_FILE="${BASE_FILE}_quality_did_input_qc.csv"
    MISSING_OUTPUT_FILE="${BASE_FILE}_quality_did_input_missing_core_quality.csv"

    echo
    echo "============================================================"
    echo "Preparing quality DiD input for panel: ${PANEL_LABEL}"
    echo "Input:           ${INPUT_FILE}"
    echo "Output:          ${OUTPUT_FILE}"
    echo "Complete output: ${COMPLETE_OUTPUT_FILE}"
    echo "QC output:       ${QC_OUTPUT_FILE}"
    echo "Missing output:  ${MISSING_OUTPUT_FILE}"
    echo "============================================================"

    python "${PY_SCRIPT}" \
      --panel-label "${PANEL_LABEL}" \
      --input "${INPUT_FILE}" \
      --output "${OUTPUT_FILE}" \
      --complete-output "${COMPLETE_OUTPUT_FILE}" \
      --qc-output "${QC_OUTPUT_FILE}" \
      --missing-output "${MISSING_OUTPUT_FILE}"

    printf '%s,%s,%s,%s,%s,%s\n' \
      "${PANEL_LABEL}" \
      "${INPUT_FILE}" \
      "${OUTPUT_FILE}" \
      "${COMPLETE_OUTPUT_FILE}" \
      "${QC_OUTPUT_FILE}" \
      "${MISSING_OUTPUT_FILE}" >> "${MANIFEST_FILE}"
  done

  echo
  echo "** Building combined quality DiD input QC"
  echo "------------------------------------------------------------"

  python - <<PY
from pathlib import Path
import pandas as pd

manifest_path = Path("${MANIFEST_FILE}")
combined_long_path = Path("${COMBINED_QC_LONG}")
combined_wide_path = Path("${COMBINED_QC_WIDE}")

manifest = pd.read_csv(manifest_path)

qc_frames = []
wide_rows = []

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
    qc_file = Path(row["qc_output"])
    missing_file = Path(row["missing_output"])
    output_file = Path(row["output"])
    complete_file = Path(row["complete_output"])

    qc = read_csv_if_possible(qc_file)
    if not qc.empty:
        qc.insert(0, "panel", panel)
        qc_frames.append(qc)

    output_df = pd.read_csv(output_file) if output_file.exists() else pd.DataFrame()
    complete_df = pd.read_csv(complete_file) if complete_file.exists() else pd.DataFrame()
    missing_df = read_csv_if_possible(missing_file)

    wide_rows.append({
        "panel": panel,
        "output_file": str(output_file),
        "complete_output_file": str(complete_file),
        "missing_output_file": str(missing_file),
        "output_rows": len(output_df),
        "complete_rows": len(complete_df),
        "missing_core_quality_rows": len(missing_df),
        "output_repos": output_df["repo_name"].nunique() if "repo_name" in output_df.columns else None,
        "complete_repos": complete_df["repo_name"].nunique() if "repo_name" in complete_df.columns else None,
        "missing_core_quality_repos": missing_df["repo_name"].nunique() if "repo_name" in missing_df.columns else 0,
    })

if qc_frames:
    combined_long = pd.concat(qc_frames, ignore_index=True)
else:
    combined_long = pd.DataFrame()

combined_wide = pd.DataFrame(wide_rows)

combined_long_path.parent.mkdir(parents=True, exist_ok=True)
combined_wide_path.parent.mkdir(parents=True, exist_ok=True)

combined_long.to_csv(combined_long_path, index=False)
combined_wide.to_csv(combined_wide_path, index=False)

print("Saved combined QC long:", combined_long_path)
print("Saved combined QC wide:", combined_wide_path)
print()
print("Combined QC wide:")
print(combined_wide.to_string(index=False))
PY

  echo
  echo "============================================================"
  echo "run-py-2e completed successfully."
  echo "Completed:        $(date)"
  echo "Panel variant:    ${PANEL_VARIANT}"
  echo "Manifest:         ${MANIFEST_FILE}"
  echo "Combined QC long: ${COMBINED_QC_LONG}"
  echo "Combined QC wide: ${COMBINED_QC_WIDE}"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9e_prepare_quality_did_input.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#
