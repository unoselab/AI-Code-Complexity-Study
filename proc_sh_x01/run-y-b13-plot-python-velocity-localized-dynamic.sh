#!/usr/bin/env bash
# run-y-b13 v1: Plot detector-localized monthly and weekly Python velocity effects.
#
# This wrapper was adapted from the reporting structure used by run-y-b11. It
# does not invoke or depend on another shell wrapper. The statistical models are
# not re-estimated here; the script validates and visualizes the established
# run-x-b08-v4 monthly estimates and run-x-b09-v2 weekly estimates.
#
# Inputs:
#   1. Monthly FECS/FEOS event-time estimates for NPR/ML and RF/CM/RF+CM.
#   2. Weekly exact-adoption-date estimates for the same detector/scope models.
#   3. Source QC results from the weekly sensitivity analysis.
#
# Outputs:
#   1. A double-column 2-by-3 PDF figure in the paper's figure directory.
#   2. A PNG preview and separate monthly/weekly PDF and PNG figures.
#   3. Plot data, series summaries, reconciliation checks, and run metadata.
#   4. A timestamped execution log.
#
# Deployment convention:
#   Remove "-v1" from both script filenames on the analysis server. This
#   wrapper first looks for the deployment filename and then the versioned name.
#
# Run after deployment:
#   bash proc_sh_x01/run-y-b13-plot-python-velocity-localized-dynamic.sh
#
# Use --overwrite to replace existing reporting outputs.
set -Eeuo pipefail

RUN_ID="run-y-b13"
IMPLEMENTATION_VERSION="v1"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -z "${PYTHON_SCRIPT:-}" ]]; then
    PYTHON_SCRIPT="proc_script_x01/plot_python_velocity_localized_dynamic.py"
    if [[ ! -f "${PYTHON_SCRIPT}" ]]; then
        PYTHON_SCRIPT="proc_script_x01/plot_python_velocity_localized_dynamic-v1.py"
    fi
fi

MONTHLY_EFFECTS_FILE="${MONTHLY_EFFECTS_FILE:-repo_x01/run-x-b08/detector-localized-python-velocity-v4/detector_localized_python_velocity_dynamic_effects.csv}"
WEEKLY_EFFECTS_FILE="${WEEKLY_EFFECTS_FILE:-repo_x01/run-x-b09/detector-localized-python-velocity-sensitivity-v2/detector_localized_velocity_weekly_dynamic_effects.csv}"
SOURCE_QC_FILE="${SOURCE_QC_FILE:-repo_x01/run-x-b09/detector-localized-python-velocity-sensitivity-v2/detector_localized_velocity_sensitivity_qc.csv}"

OUTPUT_ROOT="${OUTPUT_ROOT:-repo_x01/run-y-b13/python-velocity-localized-dynamic-v1}"
FIGURE_OUTPUT="${FIGURE_OUTPUT:-repo_x01/run-y-b13/python-velocity-localized-dynamic-v1/fig_did_velocity_python_localized_dynamic-v1.pdf}"
LOG_DIR="${LOG_DIR:-logs/run-y-b13}"

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/${RUN_ID}-${IMPLEMENTATION_VERSION}-$(date +%Y%m%d-%H%M%S)-$$.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

trap 'status=$?; echo "ERROR: run-y-b13 failed at line ${LINENO} (exit ${status}). See ${LOG_FILE}" >&2; exit "${status}"' ERR

[[ -s "${PYTHON_SCRIPT}" ]] || { echo "ERROR: Missing Python script: ${PYTHON_SCRIPT}" >&2; exit 1; }
[[ -s "${MONTHLY_EFFECTS_FILE}" ]] || { echo "ERROR: Missing monthly effects: ${MONTHLY_EFFECTS_FILE}" >&2; exit 1; }
[[ -s "${WEEKLY_EFFECTS_FILE}" ]] || { echo "ERROR: Missing weekly effects: ${WEEKLY_EFFECTS_FILE}" >&2; exit 1; }
[[ -s "${SOURCE_QC_FILE}" ]] || { echo "ERROR: Missing source QC: ${SOURCE_QC_FILE}" >&2; exit 1; }

echo "============================================================"
echo "${RUN_ID}-${IMPLEMENTATION_VERSION}: detector-localized velocity dynamics"
printf '%-30s %s\n' "Started:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
printf '%-30s %s\n' "Project root:" "${PROJECT_ROOT}"
printf '%-30s %s\n' "Python:" "$(${PYTHON_BIN} --version 2>&1)"
printf '%-30s %s\n' "Python script:" "${PYTHON_SCRIPT}"
printf '%-30s %s\n' "Python script SHA256:" "$(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"
printf '%-30s %s\n' "Monthly effects:" "${MONTHLY_EFFECTS_FILE}"
printf '%-30s %s\n' "Weekly effects:" "${WEEKLY_EFFECTS_FILE}"
printf '%-30s %s\n' "Source QC:" "${SOURCE_QC_FILE}"
printf '%-30s %s\n' "Specifications:" "FECS, FEOS"
printf '%-30s %s\n' "Detectors:" "NPR, ML"
printf '%-30s %s\n' "Scopes:" "RF, CM, RF+CM"
printf '%-30s %s\n' "Output root:" "${OUTPUT_ROOT}"
printf '%-30s %s\n' "Paper figure:" "${FIGURE_OUTPUT}"
printf '%-30s %s\n' "Log file:" "${LOG_FILE}"
echo "============================================================"

echo
echo "** Step 1: Parse and structural self-test"
"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"
echo "Python parse: PASS"
"${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test

echo
echo "** Step 2: Validate source estimates and create figures"
"${PYTHON_BIN}" "${PYTHON_SCRIPT}" \
    --monthly-effects-file "${MONTHLY_EFFECTS_FILE}" \
    --weekly-effects-file "${WEEKLY_EFFECTS_FILE}" \
    --source-qc-file "${SOURCE_QC_FILE}" \
    --output-root "${OUTPUT_ROOT}" \
    --figure-output "${FIGURE_OUTPUT}" \
    --implementation-version "${IMPLEMENTATION_VERSION}" \
    --confidence-level 0.95 \
    --expected-monthly-rows 144 \
    --expected-weekly-rows 288 \
    --expected-source-qc-rows 15 \
    --figure-width "${FIGURE_WIDTH:-7.1}" \
    --figure-height "${FIGURE_HEIGHT:-4.8}" \
    --dpi "${DPI:-300}" \
    "$@"

echo
echo "============================================================"
echo "${RUN_ID}-${IMPLEMENTATION_VERSION}: SUCCESS"
printf '%-30s %s\n' "Finished:" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
printf '%-30s %s\n' "Paper figure:" "${FIGURE_OUTPUT}"
printf '%-30s %s\n' "Output root:" "${OUTPUT_ROOT}"
printf '%-30s %s\n' "Log file:" "${LOG_FILE}"
echo "============================================================"
