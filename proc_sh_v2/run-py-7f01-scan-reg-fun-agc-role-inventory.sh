#!/usr/bin/env bash
set -euo pipefail

# Build an empirical inventory of the exact functions contributing to run-py-7f.
#
# This stage is outcome-aligned but taxonomy-free. It scans observed function
# names, paths, docstrings, calls, AST structures, and deterministic source
# samples. It does not assign semantic roles and does not analyze decorators.
#
# Inputs:
#   - Frozen run-py-7a event classifications.
#   - run-py-5a-py312 function-event manifest and source artifacts.
#   - run-py-7e parse-clean focused panel used by run-py-7f.
#
# Outputs:
#   repo_python/run-py-7f01/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f01-function-event-context-inventory.csv
#       run-py-7f01-body-month-outcome-unit-inventory.csv
#       run-py-7f01-function-name-distribution.csv
#       run-py-7f01-function-name-token-distribution.csv
#       run-py-7f01-path-token-distribution.csv
#       run-py-7f01-call-name-distribution.csv
#       run-py-7f01-docstring-term-distribution.csv
#       run-py-7f01-ast-node-distribution.csv
#       run-py-7f01-numeric-feature-summary.csv
#       run-py-7f01-deterministic-source-audit-samples.csv
#       qc/
#
# This wrapper is standalone and does not call another experiment wrapper.
# 
# Usage:
# RUN_SELF_TEST=1 OVERWRITE_OUTPUT=1 bash proc_sh_v2/run-py-7f01-scan-reg-fun-agc-role-inventory.sh 

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-/home/user1-system12/miniconda3/envs/agcparse312/bin/python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/scan_reg_fun_agc_role_inventory.py}"

SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
EVENT_CLASSIFICATIONS="${EVENT_CLASSIFICATIONS:-repo_python/run-py-7a/strict/specifications/${SPECIFICATION_NAME}/agc_commit_function_npr_event_classifications.csv}"
FUNCTION_MANIFEST="${FUNCTION_MANIFEST:-repo_python/run-py-5a-py312/strict/commit_function_detection_manifest.csv}"
FUNCTION_SOURCE_ROOT="${FUNCTION_SOURCE_ROOT:-repo_python/run-py-5a-py312/strict/commit_function_sources}"
ANALYSIS_PANEL="${ANALYSIS_PANEL:-repo_python/run-py-7e/strict/specifications/${SPECIFICATION_NAME}/panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-7f01/strict/specifications/${SPECIFICATION_NAME}/python_snapshot_ncloc/calendar_month/parse_clean}"

EXPECTED_FULL_EVENT_ROWS="${EXPECTED_FULL_EVENT_ROWS:-2994}"
EXPECTED_FULL_UNIQUE_BODIES="${EXPECTED_FULL_UNIQUE_BODIES:-2463}"
EXPECTED_PANEL_ROWS="${EXPECTED_PANEL_ROWS:-1536}"
EXPECTED_MODEL_ROWS="${EXPECTED_MODEL_ROWS:-1521}"
EXPECTED_MODEL_BODY_MONTH_OCCURRENCES="${EXPECTED_MODEL_BODY_MONTH_OCCURRENCES:-2249}"
AUDIT_SAMPLE_SIZE="${AUDIT_SAMPLE_SIZE:-240}"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f01}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f01-role-inventory-${SPECIFICATION_NAME}-${RUN_TS}.log}"

require_file() {
    local path="$1"
    local label="$2"
    if [[ ! -f "${path}" ]]; then
        echo "ERROR: ${label} not found: ${path}" >&2
        exit 2
    fi
}

require_dir() {
    local path="$1"
    local label="$2"
    if [[ ! -d "${path}" ]]; then
        echo "ERROR: ${label} not found: ${path}" >&2
        exit 2
    fi
}

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi
if [[ "${RUN_SELF_TEST}" != "0" && "${RUN_SELF_TEST}" != "1" ]]; then
    echo "ERROR: RUN_SELF_TEST must be 0 or 1" >&2
    exit 2
fi
if [[ "${OVERWRITE_OUTPUT}" != "0" && "${OVERWRITE_OUTPUT}" != "1" ]]; then
    echo "ERROR: OVERWRITE_OUTPUT must be 0 or 1" >&2
    exit 2
fi

require_file "${PYTHON_SCRIPT}" "Python script"
require_file "${EVENT_CLASSIFICATIONS}" "run-py-7a event classifications"
require_file "${FUNCTION_MANIFEST}" "run-py-5a-py312 function manifest"
require_dir "${FUNCTION_SOURCE_ROOT}" "run-py-5a-py312 function source root"
require_file "${ANALYSIS_PANEL}" "run-py-7e parse-clean analysis panel"

mkdir -p "${LOG_DIR}"
START_EPOCH="$(date +%s)"
START_TEXT="$(date)"

finish() {
    local exit_code=$?
    local end_epoch elapsed hours minutes seconds
    end_epoch="$(date +%s)"
    elapsed=$((end_epoch - START_EPOCH))
    hours=$((elapsed / 3600))
    minutes=$(((elapsed % 3600) / 60))
    seconds=$((elapsed % 60))
    echo
    echo "================================================================================"
    echo "run-py-7f01 execution summary"
    echo "Started:              ${START_TEXT}"
    echo "Completed:            $(date)"
    printf 'Elapsed:              %02d:%02d:%02d\n' "${hours}" "${minutes}" "${seconds}"
    echo "Exit code:            ${exit_code}"
    echo "Log file:             ${LOG_FILE}"
    echo "Output directory:     ${OUTPUT_DIR}"
    echo "================================================================================"
    exit "${exit_code}"
}

trap finish EXIT
exec > >(tee -a "${LOG_FILE}") 2>&1

PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
SCRIPT_SHA="$(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"

echo "================================================================================"
echo "run-py-7f01: empirical function-role inventory"
echo "Started:                         ${START_TEXT}"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Python:                          ${PYTHON_BIN}"
echo "Python version:                  ${PYTHON_VERSION}"
echo "Python script:                   ${PYTHON_SCRIPT}"
echo "Python script SHA:               ${SCRIPT_SHA}"
echo "Specification:                   ${SPECIFICATION_NAME}"
echo "Event classifications:          ${EVENT_CLASSIFICATIONS}"
echo "Function manifest:              ${FUNCTION_MANIFEST}"
echo "Function source root:           ${FUNCTION_SOURCE_ROOT}"
echo "Analysis panel:                  ${ANALYSIS_PANEL}"
echo "Analysis scope:                  run-py-7f Python-NCLOC model-ready rows"
echo "Expected full AGC events:        ${EXPECTED_FULL_EVENT_ROWS}"
echo "Expected full unique bodies:     ${EXPECTED_FULL_UNIQUE_BODIES}"
echo "Expected parse-clean rows:       ${EXPECTED_PANEL_ROWS}"
echo "Expected model-ready rows:       ${EXPECTED_MODEL_ROWS}"
echo "Expected body-month units:       ${EXPECTED_MODEL_BODY_MONTH_OCCURRENCES}"
echo "Audit sample size:               ${AUDIT_SAMPLE_SIZE}"
echo "Semantic role taxonomy applied:  NO"
echo "Decorator features included:     NO"
echo "Run self-test:                   ${RUN_SELF_TEST}"
echo "Overwrite output:                ${OVERWRITE_OUTPUT}"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Log file:                        ${LOG_FILE}"
echo "================================================================================"

"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
    "${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test
fi

OVERWRITE_ARGS=()
if [[ "${OVERWRITE_OUTPUT}" == "1" ]]; then
    OVERWRITE_ARGS=(--overwrite-output)
fi

PYTHONUNBUFFERED=1 "${PYTHON_BIN}" "${PYTHON_SCRIPT}" \
    --event-classifications "${EVENT_CLASSIFICATIONS}" \
    --function-manifest "${FUNCTION_MANIFEST}" \
    --function-source-root "${FUNCTION_SOURCE_ROOT}" \
    --analysis-panel "${ANALYSIS_PANEL}" \
    --output-dir "${OUTPUT_DIR}" \
    --audit-sample-size "${AUDIT_SAMPLE_SIZE}" \
    --expected-full-event-rows "${EXPECTED_FULL_EVENT_ROWS}" \
    --expected-full-unique-bodies "${EXPECTED_FULL_UNIQUE_BODIES}" \
    --expected-panel-rows "${EXPECTED_PANEL_ROWS}" \
    --expected-model-rows "${EXPECTED_MODEL_ROWS}" \
    --expected-model-body-month-occurrences "${EXPECTED_MODEL_BODY_MONTH_OCCURRENCES}" \
    "${OVERWRITE_ARGS[@]}"

SUMMARY_FILE="${OUTPUT_DIR}/qc/run-py-7f01-role-inventory-summary.json"
CHECKS_FILE="${OUTPUT_DIR}/qc/run-py-7f01-role-inventory-checks.csv"
require_file "${SUMMARY_FILE}" "run-py-7f01 summary"
require_file "${CHECKS_FILE}" "run-py-7f01 checks"

"${PYTHON_BIN}" - "${SUMMARY_FILE}" "${CHECKS_FILE}" <<'PY'
import json
import sys

import pandas as pd

summary_path, checks_path = sys.argv[1:3]
with open(summary_path, "r", encoding="utf-8") as handle:
    summary = json.load(handle)
checks = pd.read_csv(checks_path)
failed = checks.loc[~checks["passed"].astype(bool)]

if summary.get("status") != "PASS":
    raise SystemExit(f"Summary status is not PASS: {summary}")
if not failed.empty:
    raise SystemExit("QC contains failed checks:\n" + failed.to_string(index=False))
if summary.get("taxonomy_applied") is not False:
    raise SystemExit("run-py-7f01 must remain taxonomy-free")
if summary.get("decorator_features_included") is not False:
    raise SystemExit("Decorator features must remain excluded")

print("================================================================================")
print("run-py-7f01 output verification")
print(f"Status:                         {summary['status']}")
print(f"Event contexts:                 {summary['model_scoped_event_contexts']}")
print(f"Body-month outcome units:       {summary['model_scoped_body_month_outcome_units']}")
print(f"Unique bodies:                  {summary['model_scoped_unique_bodies']}")
print(f"Multiple-name units:            {summary['body_month_units_with_multiple_function_names']}")
print(f"Source audit samples:           {summary['audit_sample_rows']}")
print(f"Source parse errors:            {summary['source_parse_errors']}")
print(f"Failed checks:                  {summary['failed_checks']}")
print("================================================================================")
PY

