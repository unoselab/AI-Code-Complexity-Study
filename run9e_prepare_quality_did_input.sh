#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs

RUN_TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_FILE:-logs/run9e_prepare_quality_did_input_${RUN_TS}.log}"

DID_DIR="${DID_DIR:-tmp_jsts_test/data/jsts_did_final}"
PY_SCRIPT="${PY_SCRIPT:-proc_scripts/prepare_quality_did_input_v2.py}"

MANIFEST_FILE="${DID_DIR}/quality_did_input_manifest_${RUN_TS}.csv"
COMBINED_QC_LONG="${DID_DIR}/quality_did_input_qc_all_long.csv"
COMBINED_QC_WIDE="${DID_DIR}/quality_did_input_qc_all_wide.csv"

PANELS=(
  "main_balanced|${DID_DIR}/panel_event_monthly_matched_final_clean_balanced_with_sonarqube.csv"
  "main_unbalanced|${DID_DIR}/panel_event_monthly_matched_final_clean_with_sonarqube.csv"
  "strict_1to3_balanced|${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_balanced_with_sonarqube.csv"
  "strict_1to3_unbalanced|${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_with_sonarqube.csv"
)

{
  echo "============================================================"
  echo "run9e: prepare quality DiD input for JS/TS panels"
  echo "Started:          $(date)"
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

  mkdir -p "${DID_DIR}"

  echo "panel,input,output,complete_output,qc_output,missing_output" > "${MANIFEST_FILE}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: Input panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      exit 1
    fi

    BASE_FILE="${INPUT_FILE%.csv}"
    OUTPUT_FILE="${BASE_FILE}_quality_did_input.csv"
    COMPLETE_OUTPUT_FILE="${BASE_FILE}_quality_did_input_complete.csv"
    QC_OUTPUT_FILE="${BASE_FILE}_quality_did_input_qc.csv"
    MISSING_OUTPUT_FILE="${BASE_FILE}_quality_did_input_missing_core_quality.csv"

    echo
    echo "============================================================"
    echo "Preparing panel: ${PANEL_LABEL}"
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
  echo "** Building combined run9e QC summaries"
  echo "------------------------------------------------------------"

  python - "${MANIFEST_FILE}" "${COMBINED_QC_LONG}" "${COMBINED_QC_WIDE}" <<'PY'
import sys
from pathlib import Path

import pandas as pd

manifest_path = Path(sys.argv[1])
combined_long_path = Path(sys.argv[2])
combined_wide_path = Path(sys.argv[3])

manifest = pd.read_csv(manifest_path)

qc_frames = []

for _, row in manifest.iterrows():
    panel = row["panel"]
    qc_path = Path(row["qc_output"])

    if not qc_path.exists():
        raise FileNotFoundError(f"QC file not found for {panel}: {qc_path}")

    qc = pd.read_csv(qc_path)
    qc.insert(0, "panel", panel)
    qc_frames.append(qc)

combined_long = pd.concat(qc_frames, ignore_index=True)

combined_wide = (
    combined_long
    .pivot_table(index="panel", columns="check", values="value", aggfunc="first")
    .reset_index()
)

priority_cols = [
    "panel",
    "input_rows",
    "output_rows",
    "row_count_preserved_in_full_output",
    "repos",
    "treatment_rows",
    "control_rows",
    "treatment_repos",
    "control_repos",
    "duplicate_repo_time_source_rows",
    "analysis_ready_did_base_rows",
    "analysis_ready_core_quality_rows",
    "analysis_ready_quality_did_rows",
    "missing_core_quality_rows",
    "complete_output_rows",
    "complete_output_repos",
    "sonarqube_latest_commit_missing",
    "sonarqube_all_raw_metrics_missing_sum",
    "sonarqube_ncloc_zero_sum",
    "static_analysis_warnings_nonmissing",
    "duplicate_line_density_nonmissing",
    "code_complexity_nonmissing",
    "warnings_per_kloc_nonmissing",
    "complexity_per_kloc_nonmissing",
    "code_smells_per_kloc_nonmissing",
]

existing_priority = [c for c in priority_cols if c in combined_wide.columns]
remaining = [c for c in combined_wide.columns if c not in existing_priority]
combined_wide = combined_wide[existing_priority + remaining]

combined_long_path.parent.mkdir(parents=True, exist_ok=True)
combined_wide_path.parent.mkdir(parents=True, exist_ok=True)

combined_long.to_csv(combined_long_path, index=False)
combined_wide.to_csv(combined_wide_path, index=False)

print("Combined QC wide:")
print(combined_wide[existing_priority].to_string(index=False))
print()
print(f"Saved combined QC long: {combined_long_path}")
print(f"Saved combined QC wide: {combined_wide_path}")
PY

  echo
  echo "============================================================"
  echo "run9e completed successfully."
  echo "Completed:        $(date)"
  echo "Manifest:         ${MANIFEST_FILE}"
  echo "Combined QC long: ${COMBINED_QC_LONG}"
  echo "Combined QC wide: ${COMBINED_QC_WIDE}"
  echo "Log file:         ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
