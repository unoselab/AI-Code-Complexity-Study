#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-d07 v2: build ML-threshold x SonarQube burden panel
# ============================================================
#
# Purpose:
#   Prepare the threshold x sample x repo-month input consumed by run-x-d08.
#   This wrapper does NOT estimate Borusyak DiD models.
#
# Threshold contract:
#   file_ml_agc_share_space_by_token_weighted > threshold
#   21 thresholds: 0.10, 0.14, ..., 0.50, ..., 0.86, 0.90
#   primary threshold: strict > 0.50
#   function-level ML classifier boundary: unchanged
#
# Sample contract:
#   full_sample
#   exclude_scope_mismatch_repos
#
# Mapping contract:
#   all_ml_files only. Mapping-warning exclusion remains a separate D05/D06
#   robustness axis and is not mixed into the threshold-sensitivity lineage.
#
# Inputs:
#   A04 continuous file-level ML AGC share
#   D02 canonical file-level SonarQube issue burden
#   B06 authoritative quality DiD repo-month panel
#   D05 primary/scope-sensitivity reference for exact >0.50 reproduction
#
# Outputs:
#   repo_x01/run-x-d07/quality_ml_threshold_repo_month_panel.csv.gz
#   plus support, outcome, reproduction, QC, summary, and metadata artifacts.
#
# This wrapper is standalone and never calls an earlier shell wrapper.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"

RUN_PREFIX="run-x-d07"
IMPLEMENTATION_VERSION="v3"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-build-ml-threshold-quality-burden-panel-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_script_x01/build_ml_threshold_quality_burden_panel.py}"

A04_FILE="${A04_FILE:-../../ai_detector/src/app/data_did_agc_analysis/run-x-a04/python_ml_fun_file_scores.csv}"
D02_FILE="${D02_FILE:-repo_x01/run-x-d02/python_fun_file_quality_burden.csv.gz}"
B06_FILE="${B06_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
D05_REFERENCE_FILE="${D05_REFERENCE_FILE:-repo_x01/run-x-d05/quality_ml_fun_repo_month_panel.csv.gz}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-d07}"
THRESHOLDS="${THRESHOLDS:-0.10,0.14,0.18,0.22,0.26,0.30,0.34,0.38,0.42,0.46,0.50,0.54,0.58,0.62,0.66,0.70,0.74,0.78,0.82,0.86,0.90}"

EXPECTED_A04_SHA256="${EXPECTED_A04_SHA256:-b04db6462e74dfd3161d1680425a0335361e86093754ee2341f5c9e0e84e6518}"
EXPECTED_D02_SHA256="${EXPECTED_D02_SHA256:-443a9ce29969a60b186fdb3cc02a48410753d2a9f408ef95145ceb2a569945df}"
EXPECTED_B06_SHA256="${EXPECTED_B06_SHA256:-e34c56d1dda8342106a87314a9425c0ab2323ed0414c533a0f17c9c88e4f5027}"
EXPECTED_D05_SHA256="${EXPECTED_D05_SHA256:-970919c66c06c9e0c0eb88d459a9fcd916728ff4483ae7a9af559702785ebbd1}"

for tool in "${PYTHON_BIN}" sha256sum; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "ERROR: required executable not found: ${tool}" >&2
    exit 1
  fi
done

for required_file in "${PYTHON_SCRIPT}" "${A04_FILE}" "${D02_FILE}" "${B06_FILE}" "${D05_REFERENCE_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

check_sha256() {
  local path="$1"
  local expected="$2"
  local label="$3"
  local observed
  observed="$(sha256sum "${path}" | awk '{print $1}')"
  if [[ "${observed}" != "${expected}" ]]; then
    echo "ERROR: ${label} SHA256 mismatch" >&2
    echo "  expected: ${expected}" >&2
    echo "  observed: ${observed}" >&2
    echo "  file:     ${path}" >&2
    exit 1
  fi
}

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"
"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}"
check_sha256 "${A04_FILE}" "${EXPECTED_A04_SHA256}" "A04"
check_sha256 "${D02_FILE}" "${EXPECTED_D02_SHA256}" "D02"
check_sha256 "${B06_FILE}" "${EXPECTED_B06_SHA256}" "B06"
check_sha256 "${D05_REFERENCE_FILE}" "${EXPECTED_D05_SHA256}" "D05"

PYTHON_VERSION="$(${PYTHON_BIN} --version 2>&1)"
SCRIPT_SHA256="$(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"

{
  echo "================================================================================"
  echo "${RUN_LABEL}: build ML-threshold x SonarQube quality burden panel"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})"
  echo "Implementation version:          ${IMPLEMENTATION_VERSION}"
  echo "Experiment role:                 D08 input preparation only"
  echo "Threshold grid:                  ${THRESHOLDS}"
  echo "Primary file cutoff:             strict > 0.50"
  echo "Function ML boundary:            unchanged"
  echo "Mapping spec:                    all_ml_files"
  echo "Samples:                         full_sample + exclude_scope_mismatch_repos"
  echo "Density:                         not computed"
  echo "A04 ML file scores:              ${A04_FILE}"
  echo "A04 SHA256:                      ${EXPECTED_A04_SHA256}"
  echo "D02 file burden:                 ${D02_FILE}"
  echo "D02 SHA256:                      ${EXPECTED_D02_SHA256}"
  echo "B06 panel:                       ${B06_FILE}"
  echo "B06 SHA256:                      ${EXPECTED_B06_SHA256}"
  echo "D05 reproduction reference:      ${D05_REFERENCE_FILE}"
  echo "D05 SHA256:                      ${EXPECTED_D05_SHA256}"
  echo "Python script SHA256:            ${SCRIPT_SHA256}"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Primary D08 input:               ${OUTPUT_DIR}/quality_ml_threshold_repo_month_panel.csv.gz"
  echo "Expected long rows:              81249"
  echo "Pinned upstream SHA256:          PASS"
  echo "Log file:                        ${LOG_FILE}"
  echo "================================================================================"
} | tee "${LOG_FILE}"

COMMAND=(
  "${PYTHON_BIN}" "${PYTHON_SCRIPT}"
  --a04-file "${A04_FILE}"
  --d02-file "${D02_FILE}"
  --b06-file "${B06_FILE}"
  --d05-reference-file "${D05_REFERENCE_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --thresholds "${THRESHOLDS}"
)

{
  echo
  echo "** Step 1: Build 21-threshold x 2-sample ML quality panel"
  echo "----------------------------------------------------------------------------"
  printf 'Command:'; printf ' %q' "${COMMAND[@]}"; printf '\n\n'
} | tee -a "${LOG_FILE}"
"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/quality_ml_threshold_repo_month_panel.csv.gz"
  "${OUTPUT_DIR}/quality_ml_threshold_global_audit.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_by_treatment_timing.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_sample_summary.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_outcome_spec.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_d05_reproduction.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_checks.csv"
  "${OUTPUT_DIR}/quality_ml_threshold_summary.csv"
  "${OUTPUT_DIR}/metadata.json"
)

{
  echo
  echo "** Step 2: Verify D07 artifacts and hard QC"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -s "${output_file}" ]]; then
    echo "ERROR: expected non-empty output missing: ${output_file}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  echo "OK: ${output_file}" | tee -a "${LOG_FILE}"
done

if grep -q ',fail,' "${OUTPUT_DIR}/quality_ml_threshold_checks.csv" || \
   grep -q ',fail$' "${OUTPUT_DIR}/quality_ml_threshold_checks.csv"; then
  echo "ERROR: D07 hard QC contains failures" | tee -a "${LOG_FILE}" >&2
  exit 1
fi

"${PYTHON_BIN}" - "${OUTPUT_DIR}" <<'PY' | tee -a "${LOG_FILE}"
import csv
import gzip
import sys
from pathlib import Path

out = Path(sys.argv[1])
panel = out / "quality_ml_threshold_repo_month_panel.csv.gz"
summary = out / "quality_ml_threshold_summary.csv"
checks = out / "quality_ml_threshold_checks.csv"

with gzip.open(panel, "rt", newline="") as handle:
    reader = csv.DictReader(handle)
    rows = list(reader)

if len(rows) != 81249:
    raise SystemExit(f"ERROR: expected 81249 long-panel rows, found {len(rows)}")
keys = {(r["sample_spec"], r["threshold_spec_id"], r["repo_id"], r["time_index"]) for r in rows}
if len(keys) != len(rows):
    raise SystemExit("ERROR: duplicate D07 long-panel keys")
thresholds = sorted({float(r["threshold"]) for r in rows})
if len(thresholds) != 21:
    raise SystemExit(f"ERROR: expected 21 thresholds, found {len(thresholds)}")
if {r["sample_spec"] for r in rows} != {"full_sample", "exclude_scope_mismatch_repos"}:
    raise SystemExit("ERROR: unexpected D07 sample specs")

with checks.open(newline="") as handle:
    qc = list(csv.DictReader(handle))
if any(r["status"].strip().lower() != "pass" for r in qc):
    raise SystemExit("ERROR: non-pass D07 QC row")

with summary.open(newline="") as handle:
    s = {r["metric"]: r["value"] for r in csv.DictReader(handle)}
if s.get("status") != "PASS":
    raise SystemExit("ERROR: D07 summary status is not PASS")
print("D08 input contract: PASS")
print(f"Thresholds: {len(thresholds)}")
print(f"Long panel rows: {len(rows)}")
print("Hard QC: PASS")
PY

{
  echo "================================================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                        $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Thresholds:                      21"
  echo "Sample specifications:           2"
  echo "Primary cutoff:                  > 0.50"
  echo "D05 0.50 reproduction:           PASS"
  echo "D08 input contract:              PASS"
  echo "Primary D08 input:               ${OUTPUT_DIR}/quality_ml_threshold_repo_month_panel.csv.gz"
  echo "Global audit:                    ${OUTPUT_DIR}/quality_ml_threshold_global_audit.csv"
  echo "Sample summary:                  ${OUTPUT_DIR}/quality_ml_threshold_sample_summary.csv"
  echo "QC:                              ${OUTPUT_DIR}/quality_ml_threshold_checks.csv"
  echo "Metadata:                        ${OUTPUT_DIR}/metadata.json"
  echo "Log file:                        ${LOG_FILE}"
  echo "================================================================================"
} | tee -a "${LOG_FILE}"
