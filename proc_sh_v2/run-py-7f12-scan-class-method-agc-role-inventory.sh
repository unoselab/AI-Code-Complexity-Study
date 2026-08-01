#!/usr/bin/env bash
set -euo pipefail

# Build an empirical inventory of AGC-like synchronous class methods.
#
# This stage is outcome-aligned but taxonomy-free. It reads exact Git blobs
# directly from the matched local clones, reproduces run-py-5a method
# identities, and records raw names, class context, decorators, parameters,
# paths, calls, docstrings, AST structures, and deterministic source samples.
# It does not assign final semantic roles and does not run DiD.
#
# Inputs:
#   - Frozen run-py-7a event classifications.
#   - run-py-5a-py312 function-event manifest.
#   - run-py-7e parse-clean focused panel used by run-py-7f.
#   - Exact commits in ../treatment-repos and ../control-repos.
#
# Outputs:
#   repo_python/run-py-7f12/strict/specifications/range100_200/
#     python_snapshot_ncloc/calendar_month/parse_clean/
#       run-py-7f12-class-method-event-context-inventory.csv
#       run-py-7f12-class-method-body-month-unit-inventory.csv
#       run-py-7f12-method-name-distribution.csv
#       run-py-7f12-method-name-token-distribution.csv
#       run-py-7f12-class-name-distribution.csv
#       run-py-7f12-class-name-token-distribution.csv
#       run-py-7f12-method-decorator-distribution.csv
#       run-py-7f12-class-base-distribution.csv
#       run-py-7f12-first-parameter-distribution.csv
#       run-py-7f12-path-token-distribution.csv
#       run-py-7f12-call-name-distribution.csv
#       run-py-7f12-docstring-term-distribution.csv
#       run-py-7f12-ast-node-distribution.csv
#       run-py-7f12-numeric-feature-summary.csv
#       run-py-7f12-deterministic-source-audit-samples.csv
#       qc/
#
# This wrapper is standalone and does not call another experiment wrapper.
# 
# Usage:
# proc_sh_v2/run-py-7f12-scan-class-method-agc-role-inventory.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-/home/user1-system12/miniconda3/envs/agcparse312/bin/python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_scripts/scan_class_method_agc_role_inventory.py}"

SPECIFICATION_NAME="${SPECIFICATION_NAME:-range100_200}"
EVENT_CLASSIFICATIONS="${EVENT_CLASSIFICATIONS:-repo_python/run-py-7a/strict/specifications/${SPECIFICATION_NAME}/agc_commit_function_npr_event_classifications.csv}"
FUNCTION_MANIFEST="${FUNCTION_MANIFEST:-repo_python/run-py-5a-py312/strict/commit_function_detection_manifest.csv}"
TREATMENT_CLONE_DIR="${TREATMENT_CLONE_DIR:-../treatment-repos}"
CONTROL_CLONE_DIR="${CONTROL_CLONE_DIR:-../control-repos}"
ANALYSIS_PANEL="${ANALYSIS_PANEL:-repo_python/run-py-7e/strict/specifications/${SPECIFICATION_NAME}/panel_event_monthly_regular_module_function_agc_unique_body_parse_clean.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_python/run-py-7f12/strict/specifications/${SPECIFICATION_NAME}/python_snapshot_ncloc/calendar_month/parse_clean}"

EXPECTED_PANEL_ROWS="${EXPECTED_PANEL_ROWS:-1536}"
EXPECTED_MODEL_ROWS="${EXPECTED_MODEL_ROWS:-1521}"
AUDIT_SAMPLE_SIZE="${AUDIT_SAMPLE_SIZE:-240}"
PROGRESS_EVERY="${PROGRESS_EVERY:-100}"

RUN_SELF_TEST="${RUN_SELF_TEST:-1}"
OVERWRITE_OUTPUT="${OVERWRITE_OUTPUT:-0}"
LOG_DIR="${LOG_DIR:-logs/run-py-7f12}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/run-py-7f12-class-method-role-inventory-${SPECIFICATION_NAME}-${RUN_TS}.log}"

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
if ! [[ "${PROGRESS_EVERY}" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: PROGRESS_EVERY must be a positive integer" >&2
    exit 2
fi
if ! command -v git >/dev/null 2>&1; then
    echo "ERROR: git command not found" >&2
    exit 2
fi

require_file "${PYTHON_SCRIPT}" "Python script"
require_file "${EVENT_CLASSIFICATIONS}" "run-py-7a event classifications"
require_file "${FUNCTION_MANIFEST}" "run-py-5a-py312 function manifest"
require_dir "${TREATMENT_CLONE_DIR}" "treatment clone directory"
require_dir "${CONTROL_CLONE_DIR}" "control clone directory"
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
    echo "run-py-7f12 execution summary"
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
echo "run-py-7f12: empirical class-method role inventory"
echo "Started:                         ${START_TEXT}"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Python:                          ${PYTHON_BIN}"
echo "Python version:                  ${PYTHON_VERSION}"
echo "Python script:                   ${PYTHON_SCRIPT}"
echo "Python script SHA:               ${SCRIPT_SHA}"
echo "Specification:                   ${SPECIFICATION_NAME}"
echo "Event classifications:          ${EVENT_CLASSIFICATIONS}"
echo "Function manifest:              ${FUNCTION_MANIFEST}"
echo "Treatment clones:               ${TREATMENT_CLONE_DIR}"
echo "Control clones:                 ${CONTROL_CLONE_DIR}"
echo "Analysis panel:                  ${ANALYSIS_PANEL}"
echo "Analysis scope:                  run-py-7f Python-NCLOC model-ready rows"
echo "Expected parse-clean rows:       ${EXPECTED_PANEL_ROWS}"
echo "Expected model-ready rows:       ${EXPECTED_MODEL_ROWS}"
echo "Audit sample size:               ${AUDIT_SAMPLE_SIZE}"
echo "Git blob progress interval:      ${PROGRESS_EVERY}"
echo "Function scope:                  AGC-like synchronous class methods"
echo "Semantic role taxonomy applied:  NO"
echo "Decorator features included:     YES (raw syntax only)"
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
    --treatment-clone-dir "${TREATMENT_CLONE_DIR}" \
    --control-clone-dir "${CONTROL_CLONE_DIR}" \
    --analysis-panel "${ANALYSIS_PANEL}" \
    --output-dir "${OUTPUT_DIR}" \
    --audit-sample-size "${AUDIT_SAMPLE_SIZE}" \
    --expected-panel-rows "${EXPECTED_PANEL_ROWS}" \
    --expected-model-rows "${EXPECTED_MODEL_ROWS}" \
    --progress-every "${PROGRESS_EVERY}" \
    "${OVERWRITE_ARGS[@]}"

SUMMARY_FILE="${OUTPUT_DIR}/qc/run-py-7f12-role-inventory-summary.json"
CHECKS_FILE="${OUTPUT_DIR}/qc/run-py-7f12-role-inventory-checks.csv"
require_file "${SUMMARY_FILE}" "run-py-7f12 summary"
require_file "${CHECKS_FILE}" "run-py-7f12 checks"

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
    raise SystemExit("run-py-7f12 must remain taxonomy-free")
if summary.get("decorator_features_included") is not True:
    raise SystemExit("Raw decorator features must be included")

print("================================================================================")
print("run-py-7f12 output verification")
print(f"Status:                         {summary['status']}")
print(f"Event contexts:                 {summary['model_scoped_event_contexts']}")
print(f"Body-month outcome units:       {summary['model_scoped_body_month_outcome_units']}")
print(f"Unique bodies:                  {summary['model_scoped_unique_bodies']}")
print(f"Multiple-name units:            {summary['body_month_units_with_multiple_function_names']}")
print(f"Source audit samples:           {summary['audit_sample_rows']}")
print(f"Git blobs scanned:              {summary['direct_git_blobs_scanned']}")
print(f"Direct clone scan errors:       {summary['direct_clone_scan_errors']}")
print(f"Failed checks:                  {summary['failed_checks']}")
print("================================================================================")
PY
