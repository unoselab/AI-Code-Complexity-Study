#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-py-2f: Borusyak DiD for Python SonarQube quality outcomes
# ============================================================
# Purpose:
#   Run Borusyak DiD estimation for Python quality outcomes.
#
# Main strict input:
#   repo_python/did_final/panel_event_monthly_quality_py.csv
#
# Canonical strict presentation outputs:
#   proc_r/DiffInDiffBorusyak_quality_python_v2.html
#   proc_r/dynamic_effects_borusyak_quality_python_v2.pdf
#
# Core strict analysis outputs:
#   repo_python/did_final/quality_did_borusyak/strict/
#
# Extra diagnostic and combined outputs:
#   repo_python/tmp/
#
# Supported PANEL_VARIANT values:
#   strict
#   flexible
#   all
#
# Usage:
#   PANEL_VARIANT=strict bash run-py-2f-did-borusyak-quality.sh
#
# Notes:
#   This wrapper reuses the analysis flow of the existing run-py-2f
#   implementation, but it is independent and does not call another wrapper.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-${SCRIPT_DIR}}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
PANEL_VARIANT="${PANEL_VARIANT:-strict}"

if [[ "${PANEL_VARIANT}" != "strict" && "${PANEL_VARIANT}" != "flexible" && "${PANEL_VARIANT}" != "all" ]]; then
  echo "ERROR: PANEL_VARIANT must be strict, flexible, or all. Got: ${PANEL_VARIANT}"
  exit 1
fi

LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-2f_did_borusyak_quality_${PANEL_VARIANT}_${RUN_TS}.log}"

DID_DIR="${DID_DIR:-repo_python/did_final}"
PROC_R_DIR="${PROC_R_DIR:-proc_r}"
TMP_DIR="${TMP_DIR:-repo_python/tmp}"
RMD_FILE="${RMD_FILE:-${PROC_R_DIR}/DiffInDiffBorusyak_quality_python_v2.Rmd}"
HELPER_FILE="${HELPER_FILE:-${PROC_R_DIR}/diff_in_diff_borusyak_helpers.R}"
OUT_ROOT="${OUT_ROOT:-${DID_DIR}/quality_did_borusyak}"

STRICT_PANEL_FILE="${STRICT_PANEL_FILE:-${DID_DIR}/panel_event_monthly_quality_py.csv}"
FLEXIBLE_PANEL_FILE="${FLEXIBLE_PANEL_FILE:-${DID_DIR}/panel_event_matched_flexible_with_sonarqube_quality_did_input_complete.csv}"

STRICT_HTML_FILE="${STRICT_HTML_FILE:-${PROC_R_DIR}/DiffInDiffBorusyak_quality_python_v2.html}"
STRICT_PDF_FILE="${STRICT_PDF_FILE:-${PROC_R_DIR}/dynamic_effects_borusyak_quality_python_v2.pdf}"

MANIFEST_FILE="${TMP_DIR}/borusyak_quality_manifest_${PANEL_VARIANT}_${RUN_TS}.csv"
COMBINED_STATIC="${TMP_DIR}/borusyak_quality_static_effects_${PANEL_VARIANT}.csv"
COMBINED_DYNAMIC="${TMP_DIR}/borusyak_quality_dynamic_effects_${PANEL_VARIANT}.csv"
COMBINED_CHECKS="${TMP_DIR}/borusyak_quality_panel_checks_${PANEL_VARIANT}.csv"
COMBINED_INPUT_SUMMARY="${TMP_DIR}/borusyak_quality_input_summary_${PANEL_VARIANT}.csv"
COMBINED_ERRORS="${TMP_DIR}/borusyak_quality_errors_${PANEL_VARIANT}.csv"

PANELS=()

if [[ "${PANEL_VARIANT}" == "strict" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("strict|${STRICT_PANEL_FILE}")
fi

if [[ "${PANEL_VARIANT}" == "flexible" || "${PANEL_VARIANT}" == "all" ]]; then
  PANELS+=("flexible|${FLEXIBLE_PANEL_FILE}")
fi

mkdir -p "${LOG_DIR}" "${OUT_ROOT}" "${TMP_DIR}" "${PROC_R_DIR}"

{
  echo "============================================================"
  echo "run-py-2f: Python Borusyak DiD for SonarQube quality outcomes"
  echo "Started:                $(date)"
  echo "Panel variant:          ${PANEL_VARIANT}"
  echo "Project root:           ${PROJECT_ROOT}"
  echo "Rmd file:               ${RMD_FILE}"
  echo "Helper file:            ${HELPER_FILE}"
  echo "Strict input:           ${STRICT_PANEL_FILE}"
  echo "Flexible input:         ${FLEXIBLE_PANEL_FILE}"
  echo "Core output root:       ${OUT_ROOT}"
  echo "Strict HTML:            ${STRICT_HTML_FILE}"
  echo "Strict PDF:             ${STRICT_PDF_FILE}"
  echo "Extra output dir:       ${TMP_DIR}"
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

  if ! command -v Rscript >/dev/null 2>&1; then
    echo "ERROR: Rscript was not found in PATH."
    exit 1
  fi

  echo "panel,input,out_dir,html,pdf,static,dynamic,checks,input_summary,metadata,static_errors,dynamic_errors" > "${MANIFEST_FILE}"

  for entry in "${PANELS[@]}"; do
    PANEL_LABEL="${entry%%|*}"
    INPUT_FILE="${entry#*|}"
    PANEL_OUT_DIR="${OUT_ROOT}/${PANEL_LABEL}"

    if [[ ! -f "${INPUT_FILE}" ]]; then
      echo "ERROR: Input panel not found for ${PANEL_LABEL}: ${INPUT_FILE}"
      echo
      if [[ "${PANEL_LABEL}" == "strict" ]]; then
        echo "Create the strict paper-schema input first:"
        echo "  PANEL_VARIANT=strict bash run-py-2e-prepare-quality-did-input.sh --convert-paper-same-column TRUE --keep-overlap-paper-same-column TRUE"
      else
        echo "Create the flexible complete-case quality input first."
      fi
      exit 1
    fi

    mkdir -p "${PANEL_OUT_DIR}"

    GENERATED_PDF_FILE="${PANEL_OUT_DIR}/dynamic_effects_borusyak_quality.pdf"
    STATIC_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_effects.csv"
    DYNAMIC_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_effects.csv"
    CHECKS_FILE="${PANEL_OUT_DIR}/borusyak_quality_panel_checks.csv"
    INPUT_SUMMARY_FILE="${PANEL_OUT_DIR}/borusyak_quality_input_summary.csv"
    METADATA_FILE="${PANEL_OUT_DIR}/borusyak_quality_metadata.csv"
    GENERATED_STATIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_static_errors.csv"
    GENERATED_DYNAMIC_ERRORS_FILE="${PANEL_OUT_DIR}/borusyak_quality_dynamic_errors.csv"

    rm -f \
      "${GENERATED_PDF_FILE}" \
      "${GENERATED_STATIC_ERRORS_FILE}" \
      "${GENERATED_DYNAMIC_ERRORS_FILE}"

    if [[ "${PANEL_LABEL}" == "strict" ]]; then
      HTML_FILE="${STRICT_HTML_FILE}"
      PDF_FILE="${STRICT_PDF_FILE}"
      RENDER_OUTPUT_DIR="$(dirname "${HTML_FILE}")"
      RENDER_OUTPUT_FILE="$(basename "${HTML_FILE}")"
      STATIC_ERRORS_FILE="${TMP_DIR}/borusyak_quality_static_errors_strict_${RUN_TS}.csv"
      DYNAMIC_ERRORS_FILE="${TMP_DIR}/borusyak_quality_dynamic_errors_strict_${RUN_TS}.csv"
      rm -f "${HTML_FILE}" "${PDF_FILE}" "${STATIC_ERRORS_FILE}" "${DYNAMIC_ERRORS_FILE}"
    else
      HTML_FILE="${PANEL_OUT_DIR}/borusyak_quality_${PANEL_LABEL}.html"
      PDF_FILE="${GENERATED_PDF_FILE}"
      RENDER_OUTPUT_DIR="${PANEL_OUT_DIR}"
      RENDER_OUTPUT_FILE="$(basename "${HTML_FILE}")"
      STATIC_ERRORS_FILE="${TMP_DIR}/borusyak_quality_static_errors_${PANEL_LABEL}_${RUN_TS}.csv"
      DYNAMIC_ERRORS_FILE="${TMP_DIR}/borusyak_quality_dynamic_errors_${PANEL_LABEL}_${RUN_TS}.csv"
      rm -f "${HTML_FILE}" "${STATIC_ERRORS_FILE}" "${DYNAMIC_ERRORS_FILE}"
    fi

    echo
    echo "============================================================"
    echo "Running panel: ${PANEL_LABEL}"
    echo "Input:         ${INPUT_FILE}"
    echo "Core outputs:  ${PANEL_OUT_DIR}"
    echo "HTML:          ${HTML_FILE}"
    echo "PDF:           ${PDF_FILE}"
    echo "Extra outputs: ${TMP_DIR}"
    echo "============================================================"

    export PANEL_LABEL
    export PANEL_PATH="${INPUT_FILE}"
    export OUT_DIR="${PANEL_OUT_DIR}"
    export RMD_FILE
    export RENDER_OUTPUT_DIR
    export RENDER_OUTPUT_FILE

    Rscript - <<'RS'
rmd <- Sys.getenv("RMD_FILE")
render_output_dir <- Sys.getenv("RENDER_OUTPUT_DIR")
render_output_file <- Sys.getenv("RENDER_OUTPUT_FILE")

if (!file.exists(rmd)) {
  stop("Rmd file not found: ", rmd)
}

if (!requireNamespace("rmarkdown", quietly = TRUE)) {
  stop("Package 'rmarkdown' is required.")
}

rmarkdown::render(
  input = rmd,
  output_file = render_output_file,
  output_dir = render_output_dir,
  knit_root_dir = getwd(),
  envir = new.env(parent = globalenv()),
  quiet = FALSE
)
RS

    if [[ ! -f "${HTML_FILE}" ]]; then
      echo "ERROR: Expected HTML output was not created: ${HTML_FILE}"
      exit 1
    fi

    if [[ "${PANEL_LABEL}" == "strict" ]]; then
      if [[ ! -f "${GENERATED_PDF_FILE}" ]]; then
        echo "ERROR: Expected PDF output was not created: ${GENERATED_PDF_FILE}"
        exit 1
      fi
      mv -f "${GENERATED_PDF_FILE}" "${PDF_FILE}"
    fi

    if [[ -f "${GENERATED_STATIC_ERRORS_FILE}" ]]; then
      mv -f "${GENERATED_STATIC_ERRORS_FILE}" "${STATIC_ERRORS_FILE}"
    fi

    if [[ -f "${GENERATED_DYNAMIC_ERRORS_FILE}" ]]; then
      mv -f "${GENERATED_DYNAMIC_ERRORS_FILE}" "${DYNAMIC_ERRORS_FILE}"
    fi

    for required_output in \
      "${STATIC_FILE}" \
      "${DYNAMIC_FILE}" \
      "${CHECKS_FILE}" \
      "${INPUT_SUMMARY_FILE}" \
      "${METADATA_FILE}"; do
      if [[ ! -f "${required_output}" ]]; then
        echo "ERROR: Expected core output was not created: ${required_output}"
        exit 1
      fi
    done

    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "${PANEL_LABEL}" \
      "${INPUT_FILE}" \
      "${PANEL_OUT_DIR}" \
      "${HTML_FILE}" \
      "${PDF_FILE}" \
      "${STATIC_FILE}" \
      "${DYNAMIC_FILE}" \
      "${CHECKS_FILE}" \
      "${INPUT_SUMMARY_FILE}" \
      "${METADATA_FILE}" \
      "${STATIC_ERRORS_FILE}" \
      "${DYNAMIC_ERRORS_FILE}" >> "${MANIFEST_FILE}"
  done

  echo
  echo "** Building combined diagnostic outputs"
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


def read_required_csv(path: str, panel: str, kind: str) -> pd.DataFrame:
    """Read a required core output and attach panel metadata when needed."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing {kind} output for {panel}: {csv_path}")

    try:
        frame = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        frame = pd.DataFrame()

    if "panel" not in frame.columns:
        frame.insert(0, "panel", panel)

    return frame


def read_error_csv(path: str, panel: str, model_type: str) -> pd.DataFrame | None:
    """Read an optional model error file."""
    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return None

    try:
        frame = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        return None

    if "panel" not in frame.columns:
        frame.insert(0, "panel", panel)
    if "model_type" not in frame.columns:
        insert_pos = 1 if "panel" in frame.columns else 0
        frame.insert(insert_pos, "model_type", model_type)

    return frame


static_frames = []
dynamic_frames = []
checks_frames = []
summary_frames = []
error_frames = []

for _, row in manifest.iterrows():
    panel = str(row["panel"])

    static_frames.append(read_required_csv(row["static"], panel, "static"))
    dynamic_frames.append(read_required_csv(row["dynamic"], panel, "dynamic"))
    checks_frames.append(read_required_csv(row["checks"], panel, "checks"))
    summary_frames.append(read_required_csv(row["input_summary"], panel, "input summary"))

    for error_column, model_type in (
        ("static_errors", "static"),
        ("dynamic_errors", "dynamic"),
    ):
        error_frame = read_error_csv(row[error_column], panel, model_type)
        if error_frame is not None:
            error_frames.append(error_frame)

combined_static = pd.concat(static_frames, ignore_index=True) if static_frames else pd.DataFrame()
combined_dynamic = pd.concat(dynamic_frames, ignore_index=True) if dynamic_frames else pd.DataFrame()
combined_checks = pd.concat(checks_frames, ignore_index=True) if checks_frames else pd.DataFrame()
combined_input_summary = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame()
combined_errors = (
    pd.concat(error_frames, ignore_index=True)
    if error_frames
    else pd.DataFrame(columns=["panel", "model_type", "outcome", "error"])
)

for output_path in (
    combined_static_path,
    combined_dynamic_path,
    combined_checks_path,
    combined_input_summary_path,
    combined_errors_path,
):
    output_path.parent.mkdir(parents=True, exist_ok=True)

combined_static.to_csv(combined_static_path, index=False)
combined_dynamic.to_csv(combined_dynamic_path, index=False)
combined_checks.to_csv(combined_checks_path, index=False)
combined_input_summary.to_csv(combined_input_summary_path, index=False)
combined_errors.to_csv(combined_errors_path, index=False)

print("Combined static effects rows:", len(combined_static))
print("Combined dynamic effects rows:", len(combined_dynamic))
print("Combined panel checks rows:", len(combined_checks))
print("Combined input summary rows:", len(combined_input_summary))
print("Combined error rows:", len(combined_errors))
print()
print("Saved combined static effects:", combined_static_path)
print("Saved combined dynamic effects:", combined_dynamic_path)
print("Saved combined panel checks:", combined_checks_path)
print("Saved combined input summary:", combined_input_summary_path)
print("Saved combined errors:", combined_errors_path)
PY

  echo
  echo "============================================================"
  echo "run-py-2f completed successfully."
  echo "Completed:              $(date)"
  echo "Panel variant:          ${PANEL_VARIANT}"
  echo "Strict HTML:            ${STRICT_HTML_FILE}"
  echo "Strict PDF:             ${STRICT_PDF_FILE}"
  echo "Core output root:       ${OUT_ROOT}"
  echo "Extra output dir:       ${TMP_DIR}"
  echo "Manifest:               ${MANIFEST_FILE}"
  echo "Combined static:        ${COMBINED_STATIC}"
  echo "Combined dynamic:       ${COMBINED_DYNAMIC}"
  echo "Combined checks:        ${COMBINED_CHECKS}"
  echo "Combined input summary: ${COMBINED_INPUT_SUMMARY}"
  echo "Combined errors:        ${COMBINED_ERRORS}"
  echo "Log file:               ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"
