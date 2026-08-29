#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# run-x-i08-v1: build combined-ML threshold x SonarQube quality-burden panel
# ============================================================================
#
# Purpose
# -------
# Prepare the threshold x sample x repo-month input for the downstream combined
# regular-function + class-method ML Borusyak DiD experiment. This wrapper does
# NOT estimate any treatment effect.
#
# This standalone wrapper was copied from the validated run-x-d07 ML threshold
# panel wrapper and adapted for the I06/I07 combined-ML lineage. It does not call
# D07, H07, I07, or any earlier shell wrapper.
#
# Versioned delivery files
# ------------------------
#   proc_script_x01/build_ml_fun_cfun_threshold_quality_burden_panel-v1.py
#   proc_sh_x01/run-x-i08-build-ml-fun-cfun-threshold-quality-burden-panel-v1.sh
#
# Canonical runtime copies
# ------------------------
#   proc_script_x01/build_ml_fun_cfun_threshold_quality_burden_panel.py
#   proc_sh_x01/run-x-i08-build-ml-fun-cfun-threshold-quality-burden-panel.sh
#
# Inputs
# ------
# I06 file scores:
#   repo_x01/run-x-i06/python_ml_fun_cfun_file_scores.csv
#   One row per historical Python file. Combined AGC share is backed by exact
#   integer AGC body-token and total body-token counts.
#
# I06 summary:
#   repo_x01/run-x-i06/summary.json
#   Must report run-x-i06-v1 with zero hard failures.
#
# Corrected I07-v2 threshold artifacts:
#   repo_x01/run-x-i07/ml_fun_cfun_threshold_spec.csv
#   repo_x01/run-x-i07/ml_fun_cfun_threshold_audit.csv
#   repo_x01/run-x-i07/ml_fun_cfun_threshold_checks.csv
#   repo_x01/run-x-i07/summary.json
#   I08 requires I07-v2 because v2 uses exact integer token arithmetic at every
#   threshold boundary. The primary >0.50 result is unchanged from I07-v1.
#
# D02 canonical file burden:
#   repo_x01/run-x-d02/python_fun_file_quality_burden.csv.gz
#   Historical snapshot/file unresolved SonarQube issue stock.
#
# D02 outside-scope artifact:
#   repo_x01/run-x-d02/python_sonarqube_issue_files_outside_a12.csv
#   Used only to freeze the two-repository scope-sensitivity sample before DiD.
#
# B06 panel:
#   repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv
#   Authoritative repo-month timing and DiD covariates.
#
# Threshold contract
# ------------------
#   Metric: file_ml_fun_cfun_agc_share_space_by_token_weighted
#   Grid:   0.10, 0.14, ..., 0.50, ..., 0.86, 0.90 (21 points)
#   Primary: strict > 0.50
#   Boundary implementation: exact integer AGC-token / total-token comparison.
#   No threshold is recalibrated from SonarQube or treatment-effect results.
#
# Outcome contract
# ----------------
#   Select files first at each threshold.
#   Sum raw unresolved SonarQube issue stock within repo-month.
#   Apply log1p only after repo-month summation.
#   Keep zero-selected and zero-issue repo-months in the panel.
#   No density outcome is computed.
#
# Samples
# -------
#   full_sample
#   exclude_scope_mismatch_repos
#
# Outputs under repo_x01/run-x-i08/
# ----------------------------------
#   quality_ml_fun_cfun_threshold_input_panel.csv.gz
#   quality_ml_fun_cfun_threshold_input_global_audit.csv
#   quality_ml_fun_cfun_threshold_input_by_treatment_timing.csv
#   quality_ml_fun_cfun_threshold_input_sample_summary.csv
#   quality_ml_fun_cfun_threshold_input_scope_sensitivity.csv
#   quality_ml_fun_cfun_threshold_input_outcome_spec.csv
#   quality_ml_fun_cfun_threshold_input_i07_reproduction.csv
#   quality_ml_fun_cfun_threshold_input_checks.csv
#   quality_ml_fun_cfun_threshold_input_summary.csv
#   quality_ml_fun_cfun_threshold_input_metadata.json
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-i08"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-build-ml-fun-cfun-threshold-quality-burden-panel-${RUN_TS}.log}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-proc_script_x01/build_ml_fun_cfun_threshold_quality_burden_panel.py}"

I06_ROOT="${I06_ROOT:-repo_x01/run-x-i06}"
I06_FILE="${I06_FILE:-${I06_ROOT}/python_ml_fun_cfun_file_scores.csv}"
I06_SUMMARY_FILE="${I06_SUMMARY_FILE:-${I06_ROOT}/summary.json}"

I07_ROOT="${I07_ROOT:-repo_x01/run-x-i07}"
I07_THRESHOLD_SPEC_FILE="${I07_THRESHOLD_SPEC_FILE:-${I07_ROOT}/ml_fun_cfun_threshold_spec.csv}"
I07_THRESHOLD_AUDIT_FILE="${I07_THRESHOLD_AUDIT_FILE:-${I07_ROOT}/ml_fun_cfun_threshold_audit.csv}"
I07_CHECKS_FILE="${I07_CHECKS_FILE:-${I07_ROOT}/ml_fun_cfun_threshold_checks.csv}"
I07_SUMMARY_FILE="${I07_SUMMARY_FILE:-${I07_ROOT}/summary.json}"

D02_ROOT="${D02_ROOT:-repo_x01/run-x-d02}"
D02_FILE="${D02_FILE:-${D02_ROOT}/python_fun_file_quality_burden.csv.gz}"
D02_OUTSIDE_SCOPE_FILE="${D02_OUTSIDE_SCOPE_FILE:-${D02_ROOT}/python_sonarqube_issue_files_outside_a12.csv}"
B06_FILE="${B06_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-i08}"
OVERWRITE="${OVERWRITE:-0}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"

# Frozen production input hashes already established upstream. I07-v2 artifact
# hashes are intentionally not pinned because summary/metadata timestamps change
# on the corrective rerun; I08 instead validates I07-v2 run identity and QC.
EXPECTED_I06_SHA256="${EXPECTED_I06_SHA256:-98734352a5f6abf27ca0e5e8421b361491e5113f5e606f97bd737e7f012b997a}"
EXPECTED_I06_SUMMARY_SHA256="${EXPECTED_I06_SUMMARY_SHA256:-df17cc8b282ce87d015c8ee26ab04407aca8a962751f081aaf97c08b3b169935}"
EXPECTED_D02_SHA256="${EXPECTED_D02_SHA256:-443a9ce29969a60b186fdb3cc02a48410753d2a9f408ef95145ceb2a569945df}"
EXPECTED_D02_OUTSIDE_SCOPE_SHA256="${EXPECTED_D02_OUTSIDE_SCOPE_SHA256:-1ea1ecfe2c7d65ed20cd901aa3eac61011b1bc4110d51e34c8a652d8dbe9eac1}"
EXPECTED_B06_SHA256="${EXPECTED_B06_SHA256:-e34c56d1dda8342106a87314a9425c0ab2323ed0414c533a0f17c9c88e4f5027}"

for tool in "${PYTHON_BIN}" sha256sum; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "ERROR: required executable not found: ${tool}" >&2
    exit 1
  fi
done

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -f "${path}" ]]; then
    echo "ERROR: missing ${label}: ${path}" >&2
    exit 1
  fi
}

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

for binary_value in "${OVERWRITE}" "${SELF_TEST_ONLY}" "${STRICT_EXPECTED_COUNTS}"; do
  if [[ "${binary_value}" != "0" && "${binary_value}" != "1" ]]; then
    echo "ERROR: Boolean options must be 0 or 1; observed ${binary_value}" >&2
    exit 1
  fi
done

require_file "${PYTHON_SCRIPT}" "I08 Python program"
mkdir -p "${LOG_DIR}"

{
  echo "================================================================================"
  echo "${RUN_LABEL}: build combined-ML threshold x SonarQube quality-burden panel"
  echo "Started:                         $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Project root:                    ${PROJECT_ROOT}"
  echo "Python:                          $(command -v "${PYTHON_BIN}") ($(${PYTHON_BIN} --version 2>&1))"
  echo "Python script:                   ${PYTHON_SCRIPT}"
  echo "Python script SHA256:            $(sha256sum "${PYTHON_SCRIPT}" | awk '{print $1}')"
  echo "I06 file scores:                 ${I06_FILE}"
  echo "I07 threshold source:            ${I07_THRESHOLD_SPEC_FILE}"
  echo "D02 file burden:                 ${D02_FILE}"
  echo "D02 scope exclusions:            ${D02_OUTSIDE_SCOPE_FILE}"
  echo "B06 panel:                       ${B06_FILE}"
  echo "Threshold grid:                  0.10:0.90 by 0.04 (21 points)"
  echo "Primary threshold:               > 0.50 (strict)"
  echo "Boundary comparison:             exact integer token ratio"
  echo "Samples:                         full_sample + exclude_scope_mismatch_repos"
  echo "Expected long rows:              81249"
  echo "Output directory:                ${OUTPUT_DIR}"
  echo "Log file:                        ${LOG_FILE}"
  echo "================================================================================"
} | tee "${LOG_FILE}"

{
  echo
  echo "** Step 1: Run I08 structural self-test"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
"${PYTHON_BIN}" "${PYTHON_SCRIPT}" --self-test 2>&1 | tee -a "${LOG_FILE}"

{
  echo
  echo "** Step 2: Compile I08 Python program"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
"${PYTHON_BIN}" -m py_compile "${PYTHON_SCRIPT}" 2>&1 | tee -a "${LOG_FILE}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "${RUN_LABEL}: SELF-TEST PASS" | tee -a "${LOG_FILE}"
  exit 0
fi

for required_file in \
  "${I06_FILE}" "${I06_SUMMARY_FILE}" \
  "${I07_THRESHOLD_SPEC_FILE}" "${I07_THRESHOLD_AUDIT_FILE}" "${I07_CHECKS_FILE}" "${I07_SUMMARY_FILE}" \
  "${D02_FILE}" "${D02_OUTSIDE_SCOPE_FILE}" "${B06_FILE}"; do
  require_file "${required_file}" "I08 production input"
done

# I08 intentionally refuses I07-v1 because v1 compared serialized float text
# against Decimal thresholds. I07-v2 corrects this using integer token ratios.
if ! grep -Eq '"run"[[:space:]]*:[[:space:]]*"run-x-i07-v2"' "${I07_SUMMARY_FILE}"; then
  echo "ERROR: I08 requires corrected run-x-i07-v2 outputs." >&2
  exit 1
fi
# Do not grep for a bare numeric 0 anywhere in the QC CSV. Normal PASS rows
# legitimately contain observed=0 or expected=0 fields. The I08 Python program
# validates the named `passed` column with pandas and requires every value to be 1.
# This keeps the preflight check schema-aware and avoids false failures.

{
  echo
  echo "** Step 3: Freeze and verify upstream provenance"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
check_sha256 "${I06_FILE}" "${EXPECTED_I06_SHA256}" "I06 file scores"
check_sha256 "${I06_SUMMARY_FILE}" "${EXPECTED_I06_SUMMARY_SHA256}" "I06 summary"
check_sha256 "${D02_FILE}" "${EXPECTED_D02_SHA256}" "D02 file burden"
check_sha256 "${D02_OUTSIDE_SCOPE_FILE}" "${EXPECTED_D02_OUTSIDE_SCOPE_SHA256}" "D02 outside-scope artifact"
check_sha256 "${B06_FILE}" "${EXPECTED_B06_SHA256}" "B06 panel"
echo "Pinned upstream SHA256: PASS" | tee -a "${LOG_FILE}"

if [[ -d "${OUTPUT_DIR}" && -n "$(find "${OUTPUT_DIR}" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  if [[ "${OVERWRITE}" != "1" ]]; then
    echo "ERROR: output directory is not empty: ${OUTPUT_DIR}" >&2
    echo "Set OVERWRITE=1 only when intentionally rebuilding I08." >&2
    exit 1
  fi
  rm -rf "${OUTPUT_DIR}"
fi
mkdir -p "${OUTPUT_DIR}"

COMMAND=(
  "${PYTHON_BIN}" "${PYTHON_SCRIPT}"
  --i06-file "${I06_FILE}"
  --i06-summary-file "${I06_SUMMARY_FILE}"
  --i07-threshold-spec-file "${I07_THRESHOLD_SPEC_FILE}"
  --i07-threshold-audit-file "${I07_THRESHOLD_AUDIT_FILE}"
  --i07-summary-file "${I07_SUMMARY_FILE}"
  --i07-checks-file "${I07_CHECKS_FILE}"
  --d02-file "${D02_FILE}"
  --d02-outside-scope-file "${D02_OUTSIDE_SCOPE_FILE}"
  --b06-file "${B06_FILE}"
  --output-dir "${OUTPUT_DIR}"
)
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  COMMAND+=(--strict-expected-counts)
fi

{
  echo
  echo "** Step 4: Build 21-threshold x 2-sample combined-ML quality panel"
  echo "----------------------------------------------------------------------------"
  printf 'Command:'; printf ' %q' "${COMMAND[@]}"; printf '\n\n'
} | tee -a "${LOG_FILE}"
"${COMMAND[@]}" 2>&1 | tee -a "${LOG_FILE}"

EXPECTED_OUTPUTS=(
  "quality_ml_fun_cfun_threshold_input_panel.csv.gz"
  "quality_ml_fun_cfun_threshold_input_global_audit.csv"
  "quality_ml_fun_cfun_threshold_input_by_treatment_timing.csv"
  "quality_ml_fun_cfun_threshold_input_sample_summary.csv"
  "quality_ml_fun_cfun_threshold_input_scope_sensitivity.csv"
  "quality_ml_fun_cfun_threshold_input_outcome_spec.csv"
  "quality_ml_fun_cfun_threshold_input_i07_reproduction.csv"
  "quality_ml_fun_cfun_threshold_input_checks.csv"
  "quality_ml_fun_cfun_threshold_input_summary.csv"
  "quality_ml_fun_cfun_threshold_input_metadata.json"
)

{
  echo
  echo "** Step 5: Verify I08 artifacts and hard QC"
  echo "----------------------------------------------------------------------------"
} | tee -a "${LOG_FILE}"
for name in "${EXPECTED_OUTPUTS[@]}"; do
  path="${OUTPUT_DIR}/${name}"
  if [[ ! -s "${path}" ]]; then
    echo "ERROR: expected non-empty output missing: ${path}" | tee -a "${LOG_FILE}" >&2
    exit 1
  fi
  echo "OK: ${path}" | tee -a "${LOG_FILE}"
done

"${PYTHON_BIN}" - "${OUTPUT_DIR}" <<'PY' | tee -a "${LOG_FILE}"
import csv
import gzip
import sys
from pathlib import Path

out = Path(sys.argv[1])
checks = out / "quality_ml_fun_cfun_threshold_input_checks.csv"
summary = out / "quality_ml_fun_cfun_threshold_input_summary.csv"
repro = out / "quality_ml_fun_cfun_threshold_input_i07_reproduction.csv"
panel = out / "quality_ml_fun_cfun_threshold_input_panel.csv.gz"

with checks.open(newline="") as handle:
    qc = list(csv.DictReader(handle))
if any(row["passed"].strip() != "1" for row in qc):
    raise SystemExit("ERROR: I08 hard QC contains a failed row")

with repro.open(newline="") as handle:
    rows = list(csv.DictReader(handle))
if len(rows) != 21 or any(row["match"].strip() != "1" for row in rows):
    raise SystemExit("ERROR: I08 does not reproduce corrected I07 support at all 21 thresholds")

with summary.open(newline="") as handle:
    values = {row["metric"]: row["value"] for row in csv.DictReader(handle)}
if values.get("status") != "PASS":
    raise SystemExit("ERROR: I08 summary status is not PASS")
if int(float(values.get("long_panel_rows", "-1"))) != 81249:
    raise SystemExit("ERROR: I08 long-panel row count is not 81249")

count = 0
with gzip.open(panel, "rt", newline="") as handle:
    reader = csv.DictReader(handle)
    for _ in reader:
        count += 1
if count != 81249:
    raise SystemExit(f"ERROR: expected 81249 panel rows, found {count}")

print("I08 output contract: PASS")
print("I07 21-threshold reproduction: PASS")
print("Long panel rows: 81249")
print("Hard QC: PASS")
PY

{
  echo "================================================================================"
  echo "${RUN_LABEL}: SUCCESS"
  echo "Finished:                        $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Thresholds:                      21"
  echo "Sample specifications:           2"
  echo "Primary cutoff:                  > 0.50"
  echo "I07-v2 threshold reproduction:   PASS"
  echo "Expected primary selected rows:  64153 expanded / 62319 unique"
  echo "Expected primary issue stock:    35765"
  echo "I09 input panel:                 ${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_input_panel.csv.gz"
  echo "Global audit:                    ${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_input_global_audit.csv"
  echo "Sample summary:                  ${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_input_sample_summary.csv"
  echo "QC:                              ${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_input_checks.csv"
  echo "Metadata:                        ${OUTPUT_DIR}/quality_ml_fun_cfun_threshold_input_metadata.json"
  echo "Log file:                        ${LOG_FILE}"
  echo "================================================================================"
} | tee -a "${LOG_FILE}"
