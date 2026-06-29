#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs

RUN_TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_FILE:-logs/run9f_did_borusyak_quality_${RUN_TS}.log}"

export PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"

DID_DIR="${DID_DIR:-tmp_jsts_test/data/jsts_did_final}"
RMD_FILE="${RMD_FILE:-proc_r/DiffInDiffBorusyak_quality_v2.Rmd}"
OUT_ROOT="${OUT_ROOT:-${DID_DIR}/quality_did_borusyak}"

MANIFEST_FILE="${OUT_ROOT}/borusyak_quality_manifest_${RUN_TS}.csv"
COMBINED_STATIC="${OUT_ROOT}/borusyak_quality_static_effects_all.csv"
COMBINED_DYNAMIC="${OUT_ROOT}/borusyak_quality_dynamic_effects_all.csv"
COMBINED_CHECKS="${OUT_ROOT}/borusyak_quality_panel_checks_all.csv"
COMBINED_INPUT_SUMMARY="${OUT_ROOT}/borusyak_quality_input_summary_all.csv"
COMBINED_ERRORS="${OUT_ROOT}/borusyak_quality_errors_all.csv"

PANELS=(
  "main_balanced|${DID_DIR}/panel_event_monthly_matched_final_clean_balanced_with_sonarqube_quality_did_input_complete.csv"
  "main_unbalanced|${DID_DIR}/panel_event_monthly_matched_final_clean_with_sonarqube_quality_did_input_complete.csv"
  "strict_1to3_balanced|${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_balanced_with_sonarqube_quality_did_input_complete.csv"
  "strict_1to3_unbalanced|${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_with_sonarqube_quality_did_input_complete.csv"
)

{
  echo "============================================================"
  echo "run9f: Borusyak DiD for JS/TS SonarQube quality outcomes"
  echo "Started:                $(date)"
  echo "PROJECT_ROOT:           ${PROJECT_ROOT}"
  echo "Rmd file:               ${RMD_FILE}"
  echo "DID dir:                ${DID_DIR}"
  echo "Output root:            ${OUT_ROOT}"
  echo "Manifest:               ${MANIFEST_FILE}"
  echo "Combined static:        ${COMBINED_STATIC}"
  echo "Combined dynamic:       ${COMBINED_DYNAMIC}"
  echo "Combined checks:        ${COMBINED_CHECKS}"
  echo "Combined input summary: ${COMBINED_INPUT_SUMMARY}"
  echo "Combined errors:        ${COMBINED_ERRORS}"
  echo "Log file:               ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${RMD_FILE}" ]]; then
    echo "ERROR: Rmd file not found: ${RMD_FILE}"
    exit 1
  fi

  if [[ ! -f "proc_r/diff_in_diff_borusyak_helpers.R" ]]; then
    echo "ERROR: Helper file not found: proc_r/diff_in_diff_borusyak_helpers.R"
    exit 1
  fi

  mkdir -p "${OUT_ROOT}"

  echo "panel,input,out_dir,html,static,dynamic,checks,input_summary,metadata,static_errors,dynamic_errors" > "${MANIFEST_FILE}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"
    PANEL_OUT_DIR="${OUT_ROOT}/${PANEL_LABEL}"
    HTML_FILE="${PANEL_OUT_DIR}/borusyak_quality_${PANEL_LABEL}.html"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: Input complete-case panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      exit 1
    fi

    mkdir -p "${PANEL_OUT_DIR}"

    echo
    echo "============================================================"
    echo "Running panel: ${PANEL_LABEL}"
    echo "Input:         ${INPUT_FILE}"
    echo "Output dir:    ${PANEL_OUT_DIR}"
    echo "HTML:          ${HTML_FILE}"
    echo "============================================================"

    PROJECT_ROOT="${PROJECT_ROOT}" \
    PANEL_LABEL="${PANEL_LABEL}" \
    PANEL_PATH="${INPUT_FILE}" \
    OUT_DIR="${PANEL_OUT_DIR}" \
    Rscript -e "rmarkdown::render(
      '${RMD_FILE}',
      output_dir = '${PANEL_OUT_DIR}',
      output_file = 'borusyak_quality_${PANEL_LABEL}.html',
      envir = new.env()
    )"

    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "${PANEL_LABEL}" \
      "${INPUT_FILE}" \
      "${PANEL_OUT_DIR}" \
      "${HTML_FILE}" \
      "${PANEL_OUT_DIR}/borusyak_quality_static_effects.csv" \
      "${PANEL_OUT_DIR}/borusyak_quality_dynamic_effects.csv" \
      "${PANEL_OUT_DIR}/borusyak_quality_panel_checks.csv" \
      "${PANEL_OUT_DIR}/borusyak_quality_input_summary.csv" \
      "${PANEL_OUT_DIR}/borusyak_quality_metadata.csv" \
      "${PANEL_OUT_DIR}/borusyak_quality_static_errors.csv" \
      "${PANEL_OUT_DIR}/borusyak_quality_dynamic_errors.csv" >> "${MANIFEST_FILE}"
  done

  echo
  echo "** Building combined run9f outputs"
  echo "------------------------------------------------------------"

  python - "${MANIFEST_FILE}" \
    "${COMBINED_STATIC}" \
    "${COMBINED_DYNAMIC}" \
    "${COMBINED_CHECKS}" \
    "${COMBINED_INPUT_SUMMARY}" \
    "${COMBINED_ERRORS}" <<'PY'
import sys
from pathlib import Path

import pandas as pd

manifest_path = Path(sys.argv[1])
combined_static_path = Path(sys.argv[2])
combined_dynamic_path = Path(sys.argv[3])
combined_checks_path = Path(sys.argv[4])
combined_input_summary_path = Path(sys.argv[5])
combined_errors_path = Path(sys.argv[6])

manifest = pd.read_csv(manifest_path)

def read_optional_csv(path, panel, kind):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame([{
            "panel": panel,
            "kind": kind,
            "missing_file": str(path),
        }])
    df = pd.read_csv(path)
    if "panel" not in df.columns:
        df.insert(0, "panel", panel)
    return df

static_frames = []
dynamic_frames = []
checks_frames = []
summary_frames = []
error_frames = []

for _, row in manifest.iterrows():
    panel = row["panel"]

    static_frames.append(read_optional_csv(row["static"], panel, "static"))
    dynamic_frames.append(read_optional_csv(row["dynamic"], panel, "dynamic"))
    checks_frames.append(read_optional_csv(row["checks"], panel, "checks"))
    summary_frames.append(read_optional_csv(row["input_summary"], panel, "input_summary"))

    static_error_path = Path(row["static_errors"])
    dynamic_error_path = Path(row["dynamic_errors"])

    if static_error_path.exists():
      err = pd.read_csv(static_error_path)
      if "panel" not in err.columns:
          err.insert(0, "panel", panel)
      err.insert(1, "model_type", "static")
      error_frames.append(err)

    if dynamic_error_path.exists():
      err = pd.read_csv(dynamic_error_path)
      if "panel" not in err.columns:
          err.insert(0, "panel", panel)
      err.insert(1, "model_type", "dynamic")
      error_frames.append(err)

combined_static = pd.concat(static_frames, ignore_index=True) if static_frames else pd.DataFrame()
combined_dynamic = pd.concat(dynamic_frames, ignore_index=True) if dynamic_frames else pd.DataFrame()
combined_checks = pd.concat(checks_frames, ignore_index=True) if checks_frames else pd.DataFrame()
combined_input_summary = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame()
combined_errors = pd.concat(error_frames, ignore_index=True) if error_frames else pd.DataFrame(columns=["panel", "model_type", "outcome", "error"])

combined_static_path.parent.mkdir(parents=True, exist_ok=True)

combined_static.to_csv(combined_static_path, index=False)
combined_dynamic.to_csv(combined_dynamic_path, index=False)
combined_checks.to_csv(combined_checks_path, index=False)
combined_input_summary.to_csv(combined_input_summary_path, index=False)
combined_errors.to_csv(combined_errors_path, index=False)

print("Combined static effects:")
print(combined_static.to_string(index=False))
print()

print("Combined dynamic effects rows:", len(combined_dynamic))
print("Combined panel checks rows:", len(combined_checks))
print("Combined input summary rows:", len(combined_input_summary))
print("Combined error rows:", len(combined_errors))
print()

print(f"Saved combined static effects: {combined_static_path}")
print(f"Saved combined dynamic effects: {combined_dynamic_path}")
print(f"Saved combined panel checks: {combined_checks_path}")
print(f"Saved combined input summary: {combined_input_summary_path}")
print(f"Saved combined errors: {combined_errors_path}")
PY

  echo
  echo "============================================================"
  echo "run9f completed successfully."
  echo "Completed:                $(date)"
  echo "Manifest:                 ${MANIFEST_FILE}"
  echo "Combined static:          ${COMBINED_STATIC}"
  echo "Combined dynamic:         ${COMBINED_DYNAMIC}"
  echo "Combined checks:          ${COMBINED_CHECKS}"
  echo "Combined input summary:   ${COMBINED_INPUT_SUMMARY}"
  echo "Combined errors:          ${COMBINED_ERRORS}"
  echo "Log file:                 ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
