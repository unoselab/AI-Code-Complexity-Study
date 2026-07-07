#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2f: Borusyak DiD for Python SonarQube quality outcomes
# ============================================================
# Purpose:
#   Run Borusyak DiD estimation for Python quality outcomes
#   using complete-case quality DiD input files from run-py-2e.
#
# Current naming convention:
#   strict:
#     repo_python/did_final/panel_event_matched_strict_with_sonarqube_quality_did_input_complete.csv
#
#   flexible:
#     repo_python/did_final/panel_event_matched_flexible_with_sonarqube_quality_did_input_complete.csv
#
# Supported PANEL_VARIANT values:
#   strict
#   flexible
#   all
#
# Usage:
#   PANEL_VARIANT=strict bash run-py-2f-did-borusyak-quality.sh
#   PANEL_VARIANT=flexible bash run-py-2f-did-borusyak-quality.sh
#   PANEL_VARIANT=all      bash run-py-2f-did-borusyak-quality.sh
#
# Outputs:
#   repo_python/did_final/quality_did_borusyak/<variant>/
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_manifest_<variant>_<timestamp>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_static_effects_<variant>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_dynamic_effects_<variant>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_panel_checks_<variant>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_input_summary_<variant>.csv
#   repo_python/did_final/quality_did_borusyak/borusyak_quality_errors_<variant>.csv
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2f_did_borusyak_quality_${PANEL_VARIANT}_${RUN_TS}.log}"

export PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"

DID_DIR="${DID_DIR:-repo_python/did_final}"
RMD_FILE="${RMD_FILE:-proc_r/DiffInDiffBorusyak_quality_v2.Rmd}"
HELPER_FILE="${HELPER_FILE:-proc_r/diff_in_diff_borusyak_helpers.R}"
OUT_ROOT="${OUT_ROOT:-${DID_DIR}/quality_did_borusyak}"

MANIFEST_FILE="${OUT_ROOT}/borusyak_quality_manifest_${PANEL_VARIANT}_${RUN_TS}.csv"
COMBINED_STATIC="${OUT_ROOT}/borusyak_quality_static_effects_${PANEL_VARIANT}.csv"
COMBINED_DYNAMIC="${OUT_ROOT}/borusyak_quality_dynamic_effects_${PANEL_VARIANT}.csv"
COMBINED_CHECKS="${OUT_ROOT}/borusyak_quality_panel_checks_${PANEL_VARIANT}.csv"
COMBINED_INPUT_SUMMARY="${OUT_ROOT}/borusyak_quality_input_summary_${PANEL_VARIANT}.csv"
COMBINED_ERRORS="${OUT_ROOT}/borusyak_quality_errors_${PANEL_VARIANT}.csv"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${DID_DIR}/panel_event_matched_strict_with_sonarqube_quality_did_input_complete.csv")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${DID_DIR}/panel_event_matched_flexible_with_sonarqube_quality_did_input_complete.csv")
fi

mkdir -p "${LOG_DIR}" "${OUT_ROOT}"

{
  echo "============================================================"
  echo "run-py-2f: Python Borusyak DiD for SonarQube quality outcomes"
  echo "Started:                $(date)"
  echo "Panel variant:          ${PANEL_VARIANT}"
  echo "PROJECT_ROOT:           ${PROJECT_ROOT}"
  echo "Rmd file:               ${RMD_FILE}"
  echo "Helper file:            ${HELPER_FILE}"
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

  if [[ ! -f "${HELPER_FILE}" ]]; then
    echo "ERROR: Helper file not found: ${HELPER_FILE}"
    exit 1
  fi

  echo "panel,input,out_dir,html,static,dynamic,checks,input_summary,metadata,static_errors,dynamic_errors" > "${MANIFEST_FILE}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"
    PANEL_OUT_DIR="${OUT_ROOT}/${PANEL_LABEL}"
    HTML_FILE="${PANEL_OUT_DIR}/borusyak_quality_${PANEL_LABEL}.html"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: Input complete-case panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      echo
      echo "If this is flexible, first finish:"
      echo "  1. flexible treatment/control scan"
      echo "  2. PANEL_VARIANT=flexible bash run-py-2c-merge-sonarqube-panel.sh"
      echo "  3. PANEL_VARIANT=flexible bash run-py-2d-check-sonarqube-panels.sh"
      echo "  4. PANEL_VARIANT=flexible bash run-py-2e-prepare-quality-did-input.sh"
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

    export PANEL_LABEL
    export PANEL_PATH="${INPUT_FILE}"
    export OUT_DIR="${PANEL_OUT_DIR}"
    export RMD_FILE

    Rscript -e "rmarkdown::render(
      input = Sys.getenv('RMD_FILE'),
      output_file = paste0('borusyak_quality_', Sys.getenv('PANEL_LABEL'), '.html'),
      output_dir = Sys.getenv('OUT_DIR'),
      params = list(
        panel_label = Sys.getenv('PANEL_LABEL'),
        panel_path = Sys.getenv('PANEL_PATH'),
        out_dir = Sys.getenv('OUT_DIR')
      ),
      knit_root_dir = getwd(),
      envir = new.env(parent = globalenv()),
      quiet = FALSE
    )"

    STATIC_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_effects.csv"
    DYNAMIC_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_effects.csv"
    CHECKS_FILE="${PANEL_OUT_DIR}/borusyak_quality_panel_checks.csv"
    INPUT_SUMMARY_FILE="${PANEL_OUT_DIR}/borusyak_quality_input_summary.csv"
    METADATA_FILE="${PANEL_OUT_DIR}/borusyak_quality_metadata.csv"
    STATIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_errors.csv"
    DYNAMIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_errors.csv"

    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "${PANEL_LABEL}" \
      "${INPUT_FILE}" \
      "${PANEL_OUT_DIR}" \
      "${HTML_FILE}" \
      "${STATIC_FILE}" \
      "${DYNAMIC_FILE}" \
      "${CHECKS_FILE}" \
      "${INPUT_SUMMARY_FILE}" \
      "${METADATA_FILE}" \
      "${STATIC_ERRORS_FILE}" \
      "${DYNAMIC_ERRORS_FILE}" >> "${MANIFEST_FILE}"
  done

  echo
  echo "** Combining Borusyak quality outputs"
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
    """Read one output CSV and add panel/kind only when missing."""
    path = Path(path)

    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame([{
            "panel": panel,
            "kind": kind,
            "missing_file": str(path),
        }])

    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame([{
            "panel": panel,
            "kind": kind,
            "empty_file": str(path),
        }])

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

    for error_col, model_type in [
        ("static_errors", "static"),
        ("dynamic_errors", "dynamic"),
    ]:
        error_path = Path(row[error_col])

        if not error_path.exists() or error_path.stat().st_size == 0:
            continue

        try:
            err = pd.read_csv(error_path)
        except pd.errors.EmptyDataError:
            continue

        if "panel" not in err.columns:
            err.insert(0, "panel", panel)

        if "model_type" not in err.columns:
            insert_pos = 1 if "panel" in err.columns else 0
            err.insert(insert_pos, "model_type", model_type)

        error_frames.append(err)


combined_static = pd.concat(static_frames, ignore_index=True) if static_frames else pd.DataFrame()
combined_dynamic = pd.concat(dynamic_frames, ignore_index=True) if dynamic_frames else pd.DataFrame()
combined_checks = pd.concat(checks_frames, ignore_index=True) if checks_frames else pd.DataFrame()
combined_input_summary = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame()
combined_errors = pd.concat(error_frames, ignore_index=True) if error_frames else pd.DataFrame(
    columns=["panel", "model_type", "outcome", "error"]
)

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
  echo "run-py-2f completed successfully."
  echo "Completed:              $(date)"
  echo "Panel variant:          ${PANEL_VARIANT}"
  echo "Manifest:               ${MANIFEST_FILE}"
  echo "Combined static:        ${COMBINED_STATIC}"
  echo "Combined dynamic:       ${COMBINED_DYNAMIC}"
  echo "Combined checks:        ${COMBINED_CHECKS}"
  echo "Combined input summary: ${COMBINED_INPUT_SUMMARY}"
  echo "Combined errors:        ${COMBINED_ERRORS}"
  echo "Log file:               ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
#
# This wrapper is adapted from the logic of run9f_did_borusyak_quality.sh,
# but it does NOT call the existing JS/TS shell wrapper.
#
