#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run10a: Borusyak DiD for SonarQube warning subcategories
# ============================================================
# Outcomes:
#   - bugs
#   - vulnerabilities
#   - code_smells
#
# Default:
#   - strict_1to3_unbalanced only
#
# To run all panels:
#   RUN_ALL=1 ./run10a-did-warning-subcategories-borusyak.sh
# ============================================================

LOG_DIR="${LOG_DIR:-logs}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run10a_did_warning_subcategories_borusyak_${RUN_TS}.log}"

RMD="${RMD:-proc_r/DiffInDiffBorusyak_warning_subcategories_v2.Rmd}"
SUMMARY_SCRIPT="${SUMMARY_SCRIPT:-proc_scripts/summarize_borusyak_warning_subcategories.py}"
PYTHON_BIN="${PYTHON_BIN:-python}"

DID_DIR="${DID_DIR:-tmp_jsts_test/data/jsts_did_final}"
OUT_ROOT="${OUT_ROOT:-${DID_DIR}/quality_did_borusyak_warning_subcategories}"
SUMMARY_DIR="${SUMMARY_DIR:-${OUT_ROOT}/summary}"

MAIN_UNBALANCED_PANEL="${MAIN_UNBALANCED_PANEL:-${DID_DIR}/panel_event_monthly_matched_final_clean_with_sonarqube_quality_did_input_complete.csv}"
MAIN_BALANCED_PANEL="${MAIN_BALANCED_PANEL:-${DID_DIR}/panel_event_monthly_matched_final_clean_balanced_with_sonarqube_quality_did_input_complete.csv}"
STRICT_UNBALANCED_PANEL="${STRICT_UNBALANCED_PANEL:-${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_with_sonarqube_quality_did_input_complete.csv}"
STRICT_BALANCED_PANEL="${STRICT_BALANCED_PANEL:-${DID_DIR}/panel_event_monthly_matched_final_clean_1to3_only_balanced_with_sonarqube_quality_did_input_complete.csv}"

RUN_ALL="${RUN_ALL:-0}"

mkdir -p "${LOG_DIR}" "${OUT_ROOT}" "${SUMMARY_DIR}"

render_one_panel() {
  local label="$1"
  local panel="$2"
  local out_dir="${OUT_ROOT}/${label}"

  echo
  echo "============================================================"
  echo "Rendering warning-subcategory Borusyak panel: ${label}"
  echo "Panel:      ${panel}"
  echo "Output dir: ${out_dir}"
  echo "============================================================"

  if [[ ! -f "${panel}" ]]; then
    echo "ERROR: panel file not found: ${panel}"
    exit 1
  fi

  mkdir -p "${out_dir}"

  PANEL_LABEL="${label}" \
  PANEL_PATH="${panel}" \
  OUT_DIR="${out_dir}" \
  RMD_PATH="${RMD}" \
  Rscript - <<'RS'
rmd <- Sys.getenv("RMD_PATH")
panel_label <- Sys.getenv("PANEL_LABEL")
panel_path <- Sys.getenv("PANEL_PATH")
out_dir <- Sys.getenv("OUT_DIR")

if (!file.exists(rmd)) {
  stop("Rmd file not found: ", rmd)
}

if (!requireNamespace("rmarkdown", quietly = TRUE)) {
  stop("Package 'rmarkdown' is required.")
}

rmarkdown::render(
  input = rmd,
  output_file = paste0("borusyak_warning_subcategories_", panel_label, ".html"),
  output_dir = out_dir,
  params = list(
    panel_label = panel_label,
    panel_path = panel_path,
    out_dir = out_dir,
    helpers_path = "diff_in_diff_borusyak_helpers.R"
  ),
  knit_root_dir = getwd(),
  envir = new.env(parent = globalenv()),
  quiet = FALSE
)
RS
}

{
  echo "============================================================"
  echo "run10a: JS/TS SonarQube warning-subcategory Borusyak DiD"
  echo "Started:        $(date)"
  echo "Rmd:            ${RMD}"
  echo "Summary script: ${SUMMARY_SCRIPT}"
  echo "DID dir:        ${DID_DIR}"
  echo "Output root:    ${OUT_ROOT}"
  echo "Summary dir:    ${SUMMARY_DIR}"
  echo "RUN_ALL:        ${RUN_ALL}"
  echo "Log file:       ${LOG_FILE}"
  echo "============================================================"
  echo

  if [[ ! -f "${RMD}" ]]; then
    echo "ERROR: Rmd file not found: ${RMD}"
    exit 1
  fi

  if [[ ! -f "${SUMMARY_SCRIPT}" ]]; then
    echo "ERROR: summary script not found: ${SUMMARY_SCRIPT}"
    exit 1
  fi

  if [[ "${RUN_ALL}" == "1" ]]; then
    render_one_panel "main_unbalanced" "${MAIN_UNBALANCED_PANEL}"
    render_one_panel "main_balanced" "${MAIN_BALANCED_PANEL}"
    render_one_panel "strict_1to3_unbalanced" "${STRICT_UNBALANCED_PANEL}"
    render_one_panel "strict_1to3_balanced" "${STRICT_BALANCED_PANEL}"
  else
    render_one_panel "strict_1to3_unbalanced" "${STRICT_UNBALANCED_PANEL}"
  fi

  echo
  echo "** Building combined warning-subcategory summaries"
  echo "------------------------------------------------------------"

  "${PYTHON_BIN}" "${SUMMARY_SCRIPT}" \
    --out-root "${OUT_ROOT}" \
    --summary-dir "${SUMMARY_DIR}"

  echo
  echo "============================================================"
  echo "run10a completed successfully."
  echo "Completed:       $(date)"
  echo "Output root:     ${OUT_ROOT}"
  echo "Summary dir:     ${SUMMARY_DIR}"
  echo "Log file:        ${LOG_FILE}"
  echo "============================================================"

} 2>&1 | tee "${LOG_FILE}"

echo "Saved log to ${LOG_FILE}"
