#!/usr/bin/env bash
#
# Summarize the primary dynamic-panel GMM estimates in the paper table.
#
# Inputs:
#   - Whole-Python coefficient and diagnostic CSV files from run-x-e01.
#   - ML-RF coefficient and diagnostic CSV files from run-x-e03.
#   - ML-CM coefficient and diagnostic CSV files from run-x-k06.
#   - ML-RF+CM coefficient and diagnostic CSV files from run-x-k08.
#   - NPR RF/CM/RF+CM combined coefficient and diagnostic CSV files from
#     run-x-k11-v2, evaluated at the primary NPR threshold (1.515059).
#
# Outputs:
#   - tex/tb_gmm_dynamic_interactions.tex
#   - A machine-readable summary CSV.
#   - Reconciliation checks and run metadata CSV files.
#   - A timestamped execution log under logs/run-y-b10.
#
# The archive uses versioned script names. After copying the files into the
# server workspace, remove "-v1" from both script filenames. The fallback
# below also permits validation before renaming the Python script.

set -Eeuo pipefail

RUN_ID="run-y-b10"
IMPLEMENTATION_VERSION="v1"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_script_x01/summarize_gmm_dynamic_interactions.py}"
if [[ ! -f "${PYTHON_SCRIPT}" ]]; then
    PYTHON_SCRIPT="proc_script_x01/summarize_gmm_dynamic_interactions-v1.py"
fi

WHOLE_COEFFICIENTS="${WHOLE_COEFFICIENTS:-repo_x01/run-x-e01/dynamic_panel_gmm_coefficients.csv}"
WHOLE_DIAGNOSTICS="${WHOLE_DIAGNOSTICS:-repo_x01/run-x-e01/dynamic_panel_gmm_diagnostics.csv}"
ML_RF_COEFFICIENTS="${ML_RF_COEFFICIENTS:-repo_x01/run-x-e03/dynamic_panel_gmm_ml_coefficients.csv}"
ML_RF_DIAGNOSTICS="${ML_RF_DIAGNOSTICS:-repo_x01/run-x-e03/dynamic_panel_gmm_ml_diagnostics.csv}"
ML_CM_COEFFICIENTS="${ML_CM_COEFFICIENTS:-repo_x01/run-x-k06/dynamic_panel_gmm_ml_cm_coefficients.csv}"
ML_CM_DIAGNOSTICS="${ML_CM_DIAGNOSTICS:-repo_x01/run-x-k06/dynamic_panel_gmm_ml_cm_diagnostics.csv}"
ML_RF_CM_COEFFICIENTS="${ML_RF_CM_COEFFICIENTS:-repo_x01/run-x-k08/dynamic_panel_gmm_ml_rf_cm_coefficients.csv}"
ML_RF_CM_DIAGNOSTICS="${ML_RF_CM_DIAGNOSTICS:-repo_x01/run-x-k08/dynamic_panel_gmm_ml_rf_cm_diagnostics.csv}"
NPR_COEFFICIENTS="${NPR_COEFFICIENTS:-repo_x01/run-x-k11/npr-localization-gmm-v2/dynamic_panel_gmm_npr_localization_coefficients.csv}"
NPR_DIAGNOSTICS="${NPR_DIAGNOSTICS:-repo_x01/run-x-k11/npr-localization-gmm-v2/dynamic_panel_gmm_npr_localization_diagnostics.csv}"

OUTPUT_ROOT="${OUTPUT_ROOT:-repo_x01/run-y-b10/gmm-dynamic-interactions-table-v1}"
OUTPUT_TEX="${OUTPUT_TEX:-tex/tb_gmm_dynamic_interactions.tex}"
SUMMARY_CSV="${OUTPUT_ROOT}/gmm_dynamic_interactions_summary.csv"
CHECKS_CSV="${OUTPUT_ROOT}/gmm_dynamic_interactions_reconciliation_checks.csv"
METADATA_CSV="${OUTPUT_ROOT}/gmm_dynamic_interactions_run_metadata.csv"

LOG_DIR="logs/run-y-b10"
mkdir -p "${OUTPUT_ROOT}" "$(dirname "${OUTPUT_TEX}")" "${LOG_DIR}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/${RUN_ID}-${IMPLEMENTATION_VERSION}-${TIMESTAMP}.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

required_files=(
    "${PYTHON_SCRIPT}"
    "${WHOLE_COEFFICIENTS}" "${WHOLE_DIAGNOSTICS}"
    "${ML_RF_COEFFICIENTS}" "${ML_RF_DIAGNOSTICS}"
    "${ML_CM_COEFFICIENTS}" "${ML_CM_DIAGNOSTICS}"
    "${ML_RF_CM_COEFFICIENTS}" "${ML_RF_CM_DIAGNOSTICS}"
    "${NPR_COEFFICIENTS}" "${NPR_DIAGNOSTICS}"
)
for required_file in "${required_files[@]}"; do
    if [[ ! -s "${required_file}" ]]; then
        echo "ERROR: Required input is missing or empty: ${required_file}" >&2
        exit 1
    fi
done

echo "============================================================"
echo "${RUN_ID} ${IMPLEMENTATION_VERSION}: dynamic-panel GMM table summary"
echo "Started:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Project root:                  ${PROJECT_ROOT}"
echo "Python:                        $(${PYTHON_BIN} --version 2>&1)"
echo "Python script:                 ${PYTHON_SCRIPT}"
echo "Python script SHA256:          $(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"
echo "Whole-Python source:           ${WHOLE_COEFFICIENTS}"
echo "NPR source:                    ${NPR_COEFFICIENTS}"
echo "ML-RF source:                  ${ML_RF_COEFFICIENTS}"
echo "ML-CM source:                  ${ML_CM_COEFFICIENTS}"
echo "ML-RF+CM source:               ${ML_RF_CM_COEFFICIENTS}"
echo "Output table:                  ${OUTPUT_TEX}"
echo "Output root:                   ${OUTPUT_ROOT}"
echo "Log file:                      ${LOG_FILE}"
echo "============================================================"

"${PYTHON_BIN}" "${PYTHON_SCRIPT}" \
    --whole-coefficients "${WHOLE_COEFFICIENTS}" \
    --whole-diagnostics "${WHOLE_DIAGNOSTICS}" \
    --npr-coefficients "${NPR_COEFFICIENTS}" \
    --npr-diagnostics "${NPR_DIAGNOSTICS}" \
    --ml-rf-coefficients "${ML_RF_COEFFICIENTS}" \
    --ml-rf-diagnostics "${ML_RF_DIAGNOSTICS}" \
    --ml-cm-coefficients "${ML_CM_COEFFICIENTS}" \
    --ml-cm-diagnostics "${ML_CM_DIAGNOSTICS}" \
    --ml-rf-cm-coefficients "${ML_RF_CM_COEFFICIENTS}" \
    --ml-rf-cm-diagnostics "${ML_RF_CM_DIAGNOSTICS}" \
    --output-tex "${OUTPUT_TEX}" \
    --summary-csv "${SUMMARY_CSV}" \
    --checks-csv "${CHECKS_CSV}" \
    --metadata-csv "${METADATA_CSV}" \
    --implementation-version "${IMPLEMENTATION_VERSION}"

for output_file in "${OUTPUT_TEX}" "${SUMMARY_CSV}" "${CHECKS_CSV}" "${METADATA_CSV}"; do
    if [[ ! -s "${output_file}" ]]; then
        echo "ERROR: Expected output is missing or empty: ${output_file}" >&2
        exit 1
    fi
done

echo "============================================================"
echo "${RUN_ID} ${IMPLEMENTATION_VERSION}: SUCCESS"
echo "Finished:                      $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Table:                         ${OUTPUT_TEX}"
echo "Summary:                       ${SUMMARY_CSV}"
echo "Checks:                        ${CHECKS_CSV}"
echo "Metadata:                      ${METADATA_CSV}"
echo "Log:                           ${LOG_FILE}"
echo "============================================================"
