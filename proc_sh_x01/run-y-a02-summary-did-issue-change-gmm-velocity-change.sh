#!/usr/bin/env bash
# Standalone wrapper for run-y-a02.
#
# Purpose
# -------
# Summarize the primary combined RF+CM DiD issue-burden changes and the
# corresponding dynamic-panel GMM quality-to-velocity associations for the
# NPR and ML AGC localization approaches.
#
# Inputs
# ------
# - run-x-i05: NPR combined RF+CM primary DiD static results.
# - run-x-i09: ML combined RF+CM primary DiD static results.
# - run-x-k04: NPR combined RF+CM GMM coefficient results.
# - run-x-k08: ML combined RF+CM GMM coefficient results.
#
# Outputs
# -------
# - repo_x01/run-y-a02/did_issue_change_summary.csv
# - repo_x01/run-y-a02/gmm_velocity_change_summary.csv
# - repo_x01/run-y-a02/did_issue_change_gmm_velocity_change_summary.json
# - logs/run-y-a02-summary-did-issue-change-gmm-velocity-change-<timestamp>.log
#
# This wrapper is self-contained and does not source or call any existing
# experiment shell script.

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_script_x01/summarize_did_issue_change_gmm_velocity_change.py}"

NPR_DID="${NPR_DID:-repo_x01/run-x-i05/quality_fun_cfun_npr_primary_total_static.csv}"
ML_DID="${ML_DID:-repo_x01/run-x-i09/quality_ml_fun_cfun_primary_total_static.csv}"
NPR_GMM="${NPR_GMM:-repo_x01/run-x-k04/dynamic_panel_gmm_npr_rf_cm_coefficients.csv}"
ML_GMM="${ML_GMM:-repo_x01/run-x-k08/dynamic_panel_gmm_ml_rf_cm_coefficients.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-y-a02}"
BURDEN_INCREASE_PCT="${BURDEN_INCREASE_PCT:-10}"
LOG_DIR="${LOG_DIR:-logs}"
TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE="${LOG_DIR}/run-y-a02-summary-did-issue-change-gmm-velocity-change-${TIMESTAMP}.log"

cd "${PROJECT_ROOT}"
mkdir -p "${OUTPUT_DIR}" "${LOG_DIR}"

for required_file in "${PYTHON_SCRIPT}" "${NPR_DID}" "${ML_DID}" "${NPR_GMM}" "${ML_GMM}"; do
    if [[ ! -f "${required_file}" ]]; then
        echo "ERROR: required file not found: ${required_file}" >&2
        exit 2
    fi
done

exec > >(tee -a "${LOG_FILE}") 2>&1

echo "=============================================================================="
echo "run-y-a02: summarize localized DiD issue change and GMM velocity change"
echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Python:                          ${PYTHON_BIN}"
echo "Python script:                   ${PYTHON_SCRIPT}"
echo "NPR DiD input:                   ${NPR_DID}"
echo "ML DiD input:                    ${ML_DID}"
echo "NPR GMM input:                   ${NPR_GMM}"
echo "ML GMM input:                    ${ML_GMM}"
echo "GMM burden increase scenario:    ${BURDEN_INCREASE_PCT}%"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Log file:                        ${LOG_FILE}"
echo "=============================================================================="

echo
echo "** Step 1: Run Python self-test"
echo "------------------------------------------------------------------------------"
"${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test

echo
echo "** Step 2: Generate manuscript-support summary"
echo "------------------------------------------------------------------------------"
"${PYTHON_BIN}" "${PYTHON_SCRIPT}" \
    --npr-did "${NPR_DID}" \
    --ml-did "${ML_DID}" \
    --npr-gmm "${NPR_GMM}" \
    --ml-gmm "${ML_GMM}" \
    --output-dir "${OUTPUT_DIR}" \
    --burden-increase-pct "${BURDEN_INCREASE_PCT}"

echo
echo "** Step 3: Verify output artifacts"
echo "------------------------------------------------------------------------------"
for output_file in \
    "${OUTPUT_DIR}/did_issue_change_summary.csv" \
    "${OUTPUT_DIR}/gmm_velocity_change_summary.csv" \
    "${OUTPUT_DIR}/did_issue_change_gmm_velocity_change_summary.json"; do
    if [[ ! -s "${output_file}" ]]; then
        echo "ERROR: expected non-empty output missing: ${output_file}" >&2
        exit 3
    fi
    echo "OK: ${output_file}"
done

echo "=============================================================================="
echo "run-y-a02 completed successfully."
echo "Completed:                       $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "=============================================================================="
