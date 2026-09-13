#!/usr/bin/env bash
# run-y-b11 v1: Plot and summarize K12 detector-localized GMM threshold sweeps.
# Adapted from a copy of run-y-b10; no other wrapper is invoked.
# Inputs: nine combined K12 v2 CSVs in INPUT_ROOT (see Python FILES).
# Outputs: six-panel and individual PDF/PNG figures in FIGURE_DIR; OUTPUT_TEX;
# plot-data, series/diagnostic summaries, significance runs and checks CSVs,
# and metadata JSON in OUTPUT_ROOT. Logs are timestamped under LOG_DIR.
# This reporting experiment does not re-estimate GMM or read old K09/K10 data.
# Deployment: remove -v1 from both script filenames on the server.
# Run: bash proc_sh_x01/run-y-b11-plot-gmm-localization-threshold-sensitivity.sh
# Optional Python arguments, including --overwrite, are passed last.
set -Eeuo pipefail
RUN_ID="run-y-b11"
IMPLEMENTATION_VERSION="v1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -z "${PYTHON_SCRIPT:-}" ]]; then
    PYTHON_SCRIPT="proc_script_x01/plot_gmm_localization_threshold_sensitivity.py"
    if [[ ! -f "${PYTHON_SCRIPT}" ]]; then
        PYTHON_SCRIPT="proc_script_x01/plot_gmm_localization_threshold_sensitivity-v1.py"
    fi
fi
INPUT_ROOT="${INPUT_ROOT:-repo_x01/run-x-k12/localization-threshold-gmm-v2}"
OUTPUT_ROOT="${OUTPUT_ROOT:-repo_x01/run-y-b11/gmm-localization-threshold-sensitivity-v1}"
FIGURE_DIR="${FIGURE_DIR:-repo_x01/run-y-b11/gmm-localization-threshold-sensitivity-v1/figure}"
OUTPUT_TEX="${OUTPUT_TEX:-tex/fig_gmm_localization_threshold_sensitivity-v1.tex}"
LOG_DIR="${LOG_DIR:-logs/run-y-b11}"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/${RUN_ID}-${IMPLEMENTATION_VERSION}-$(date +%Y%m%d-%H%M%S)-$$.log"
exec > >(tee -a "${LOG_FILE}") 2>&1
trap 'code=$?; echo "ERROR: run-y-b11 failed at line ${LINENO} (exit ${code}). See ${LOG_FILE}" >&2; exit "${code}"' ERR
[[ -s "${PYTHON_SCRIPT}" ]] || { echo "ERROR: Missing Python script: ${PYTHON_SCRIPT}"; exit 1; }
echo "${RUN_ID} ${IMPLEMENTATION_VERSION}: GMM threshold sensitivity (plotting only)"
echo "Started: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Project root: ${PROJECT_ROOT}"
echo "Python: $(${PYTHON_BIN} --version 2>&1)"
echo "Python script SHA256: $(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"
echo "Input root (default): ${INPUT_ROOT}"
echo "Output root (default): ${OUTPUT_ROOT}"
echo "Log: ${LOG_FILE}"
"${PYTHON_BIN}" "${PYTHON_SCRIPT}" \
    --input-root "${INPUT_ROOT}" --output-root "${OUTPUT_ROOT}" \
    --figure-dir "${FIGURE_DIR}" --output-tex "${OUTPUT_TEX}" \
    --implementation-version "${IMPLEMENTATION_VERSION}" \
    --npr-primary 1.515059 --ml-primary 0.50 \
    --npr-min 1.015059 --npr-max 2.015059 --npr-step 0.05 \
    --ml-min 0.10 --ml-max 0.90 --ml-step 0.04 \
    --confidence-level 0.95 --expected-thresholds 21 \
    --dpi "${DPI:-300}" --figure-width "${FIGURE_WIDTH:-7.1}" \
    --figure-height "${FIGURE_HEIGHT:-4.6}" "$@"
echo "${RUN_ID} ${IMPLEMENTATION_VERSION}: SUCCESS"
echo "Finished: $(date '+%Y-%m-%d %H:%M:%S %Z')"
