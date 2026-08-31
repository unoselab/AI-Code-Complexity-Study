#!/usr/bin/env bash
# =============================================================================
# run-x-j02-build-sonarqube-complexity-detector-panel-v1.sh
#
# Delivery filename: versioned for experiment provenance.
# Canonical server runtime filename:
#   proc_sh_x01/run-x-j02-build-sonarqube-complexity-detector-panel.sh
#
# Purpose
# -------
# Build the cognitive-complexity measurement panel used to compare:
#   1. all historical Python files measured by J01,
#   2. frozen combined FUN+C_FUN NPR-selected files, and
#   3. frozen combined FUN+C_FUN ML-selected files.
#
# Reference implementation
# ------------------------
# This standalone wrapper follows the finalized I04/I08 threshold-panel wrapper
# conventions and the J01 provenance/QC conventions. It does not call any prior
# shell wrapper. Existing J01/I01/I02/I06/I07/B06 artifacts are immutable inputs;
# only the new J02 Python program is executed.
#
# Canonical runtime Python filename:
#   proc_script_x01/build_sonarqube_complexity_detector_panel.py
#
# Required inputs
# ---------------
# J01 file-level SonarQube metrics:
#   repo_x01/run-x-j01/python_sonarqube_file_complexity.csv.gz
#   repo_x01/run-x-j01/python_sonarqube_complexity_snapshot_counts.csv
#
# Combined NPR:
#   repo_x01/run-x-i01/python_fun_cfun_file_npr_scores.csv
#   repo_x01/run-x-i02/fun_cfun_npr_threshold_spec.csv
#
# Combined ML:
#   repo_x01/run-x-i06/python_ml_fun_cfun_file_scores.csv
#   repo_x01/run-x-i07/ml_fun_cfun_threshold_spec.csv
#   I07 must be the corrected v2 production output. The J02 Python program uses
#   exact integer AGC-token / total-token comparison for every ML threshold.
#
# Causal/timing base (measurement expansion only; no DiD is estimated here):
#   repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv
#
# Outputs
# -------
# Under repo_x01/run-x-j02:
#   python_sonarqube_file_complexity_detector_join.csv.gz
#   python_sonarqube_complexity_files_outside_detector_universe.csv
#   python_detector_files_without_sonarqube_complexity.csv
#   python_sonarqube_complexity_alignment_by_snapshot.csv
#   python_sonarqube_complexity_threshold_global_audit.csv
#   python_sonarqube_complexity_repo_month_panel.csv.gz
#   python_sonarqube_complexity_qc.csv
#   python_sonarqube_complexity_summary.csv
#   metadata.json
#
# Scientific boundary
# -------------------
# * No SonarQube rescan.
# * No NPR or ML rescoring.
# * No threshold recalibration.
# * No treatment-effect estimation.
# * No path alias remapping. Unmatched files are explicit audit outputs.
# * NPR non-finite files remain unclassified.
# * ML unscored files remain unclassified.
# * Primary burden is sum(file cognitive_complexity), then log1p at repo-month.
# * Cognitive-complexity-per-KLOC is retained only as normalization robustness.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-j02"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/build_sonarqube_complexity_detector_panel.py}"

J01_FILE="${J01_FILE:-repo_x01/run-x-j01/python_sonarqube_file_complexity.csv.gz}"
J01_SNAPSHOT_FILE="${J01_SNAPSHOT_FILE:-repo_x01/run-x-j01/python_sonarqube_complexity_snapshot_counts.csv}"
I01_FILE="${I01_FILE:-repo_x01/run-x-i01/python_fun_cfun_file_npr_scores.csv}"
I02_THRESHOLD_SPEC_FILE="${I02_THRESHOLD_SPEC_FILE:-repo_x01/run-x-i02/fun_cfun_npr_threshold_spec.csv}"
I06_FILE="${I06_FILE:-repo_x01/run-x-i06/python_ml_fun_cfun_file_scores.csv}"
I07_THRESHOLD_SPEC_FILE="${I07_THRESHOLD_SPEC_FILE:-repo_x01/run-x-i07/ml_fun_cfun_threshold_spec.csv}"
B06_FILE="${B06_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-j02}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-build-sonarqube-complexity-detector-panel-${RUN_TS}.log}"
STRICT_EXPECTED_COUNTS="${STRICT_EXPECTED_COUNTS:-1}"
SELF_TEST_ONLY="${SELF_TEST_ONLY:-0}"
OVERWRITE="${OVERWRITE:-0}"

for required_file in \
  "${PY_SCRIPT}" \
  "${J01_FILE}" "${J01_SNAPSHOT_FILE}" \
  "${I01_FILE}" "${I02_THRESHOLD_SPEC_FILE}" \
  "${I06_FILE}" "${I07_THRESHOLD_SPEC_FILE}" \
  "${B06_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required input not found: ${required_file}" >&2
    exit 2
  fi
done

PYTHON_VERSION="$(${PYTHON_BIN} -c 'import platform; print(platform.python_version())')"
PYTHON_MAJOR_MINOR="$(${PYTHON_BIN} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "${PYTHON_MAJOR_MINOR}" != "3.11" ]]; then
  echo "ERROR: J02 requires Python 3.11.x; found ${PYTHON_VERSION}" >&2
  exit 2
fi

mkdir -p "${LOG_DIR}"
if [[ -d "${OUTPUT_DIR}" && -n "$(find "${OUTPUT_DIR}" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  if [[ "${OVERWRITE}" != "1" ]]; then
    echo "ERROR: output directory is not empty: ${OUTPUT_DIR}" >&2
    echo "Set OVERWRITE=1 only when intentionally rebuilding J02." >&2
    exit 1
  fi
  rm -rf "${OUTPUT_DIR}"
fi
mkdir -p "${OUTPUT_DIR}"

PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
J01_SHA256="$(sha256sum "${J01_FILE}" | awk '{print $1}')"
J01_SNAPSHOT_SHA256="$(sha256sum "${J01_SNAPSHOT_FILE}" | awk '{print $1}')"
I01_SHA256="$(sha256sum "${I01_FILE}" | awk '{print $1}')"
I02_SPEC_SHA256="$(sha256sum "${I02_THRESHOLD_SPEC_FILE}" | awk '{print $1}')"
I06_SHA256="$(sha256sum "${I06_FILE}" | awk '{print $1}')"
I07_SPEC_SHA256="$(sha256sum "${I07_THRESHOLD_SPEC_FILE}" | awk '{print $1}')"
B06_SHA256="$(sha256sum "${B06_FILE}" | awk '{print $1}')"

exec > >(tee "${LOG_FILE}") 2>&1
START_EPOCH="$(date +%s)"

echo "================================================================================"
echo "${RUN_LABEL}: build SonarQube cognitive-complexity detector panel"
echo "Started:                         $(date)"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})"
echo "Python script:                   ${PY_SCRIPT}"
echo "Python script SHA256:            ${PY_SCRIPT_SHA256}"
echo "J01 file complexity:             ${J01_FILE}"
echo "J01 SHA256:                      ${J01_SHA256}"
echo "J01 snapshot reconciliation:     ${J01_SNAPSHOT_FILE}"
echo "J01 snapshot SHA256:             ${J01_SNAPSHOT_SHA256}"
echo "I01 combined NPR files:          ${I01_FILE}"
echo "I01 SHA256:                      ${I01_SHA256}"
echo "I02 NPR threshold spec:          ${I02_THRESHOLD_SPEC_FILE}"
echo "I02 spec SHA256:                 ${I02_SPEC_SHA256}"
echo "I06 combined ML files:           ${I06_FILE}"
echo "I06 SHA256:                      ${I06_SHA256}"
echo "I07-v2 ML threshold spec:        ${I07_THRESHOLD_SPEC_FILE}"
echo "I07 spec SHA256:                 ${I07_SPEC_SHA256}"
echo "B06 timing panel:                ${B06_FILE}"
echo "B06 SHA256:                      ${B06_SHA256}"
echo "Output directory:                ${OUTPUT_DIR}"
echo "NPR primary:                     > 1.571637 (frozen I02 spec)"
echo "ML primary:                      > 0.50 (exact integer ratio)"
echo "SonarQube rescan:                none"
echo "Detector rescoring:              none"
echo "DiD estimation:                  none"
echo "Path remapping:                  none; unmatched files audited"
echo "Strict expected counts:          ${STRICT_EXPECTED_COUNTS}"
echo "Log file:                        ${LOG_FILE}"
echo "================================================================================"

echo
echo "** Step 1: Run J02 structural self-test"
echo "----------------------------------------------------------------------------"
"${PYTHON_BIN}" "${PY_SCRIPT}" --self-test

echo
echo "** Step 2: Compile J02 Python program"
echo "----------------------------------------------------------------------------"
"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

if [[ "${SELF_TEST_ONLY}" == "1" ]]; then
  echo "SELF_TEST_ONLY=1: stopping after self-test and compile."
  exit 0
fi

echo
echo "** Step 3: Build exact file alignment and complexity panels"
echo "----------------------------------------------------------------------------"
COMMAND=(
  "${PYTHON_BIN}" "${PY_SCRIPT}"
  --j01-file "${J01_FILE}"
  --j01-snapshot-file "${J01_SNAPSHOT_FILE}"
  --i01-file "${I01_FILE}"
  --i06-file "${I06_FILE}"
  --i02-threshold-spec-file "${I02_THRESHOLD_SPEC_FILE}"
  --i07-threshold-spec-file "${I07_THRESHOLD_SPEC_FILE}"
  --b06-file "${B06_FILE}"
  --output-dir "${OUTPUT_DIR}"
)
if [[ "${STRICT_EXPECTED_COUNTS}" == "1" ]]; then
  COMMAND+=(--strict-expected-counts)
fi
printf 'Command:'; printf ' %q' "${COMMAND[@]}"; printf '\n\n'
"${COMMAND[@]}"

echo
echo "** Step 4: Verify J02 output artifacts"
echo "----------------------------------------------------------------------------"
EXPECTED_OUTPUTS=(
  python_sonarqube_file_complexity_detector_join.csv.gz
  python_sonarqube_complexity_files_outside_detector_universe.csv
  python_detector_files_without_sonarqube_complexity.csv
  python_sonarqube_complexity_alignment_by_snapshot.csv
  python_sonarqube_complexity_threshold_global_audit.csv
  python_sonarqube_complexity_repo_month_panel.csv.gz
  python_sonarqube_complexity_qc.csv
  python_sonarqube_complexity_summary.csv
  metadata.json
)
for name in "${EXPECTED_OUTPUTS[@]}"; do
  path="${OUTPUT_DIR}/${name}"
  if [[ ! -s "${path}" ]]; then
    echo "ERROR: expected non-empty output missing: ${path}" >&2
    exit 1
  fi
  ls -lh "${path}"
done

echo
echo "J02 QC checks:"
cat "${OUTPUT_DIR}/python_sonarqube_complexity_qc.csv"

echo
echo "J02 summary:"
cat "${OUTPUT_DIR}/python_sonarqube_complexity_summary.csv"

END_EPOCH="$(date +%s)"
ELAPSED="$((END_EPOCH - START_EPOCH))"
printf -v ELAPSED_TEXT '%02d:%02d:%02d' "$((ELAPSED / 3600))" "$(((ELAPSED % 3600) / 60))" "$((ELAPSED % 60))"

echo
echo "================================================================================"
echo "${RUN_LABEL} completed."
echo "Completed:                       $(date)"
echo "Elapsed:                         ${ELAPSED_TEXT}"
echo "File alignment:                  ${OUTPUT_DIR}/python_sonarqube_file_complexity_detector_join.csv.gz"
echo "J01-only scope exclusions:       ${OUTPUT_DIR}/python_sonarqube_complexity_files_outside_detector_universe.csv"
echo "Detector-only scope exclusions:  ${OUTPUT_DIR}/python_detector_files_without_sonarqube_complexity.csv"
echo "Threshold audit:                 ${OUTPUT_DIR}/python_sonarqube_complexity_threshold_global_audit.csv"
echo "Repo-month complexity panel:     ${OUTPUT_DIR}/python_sonarqube_complexity_repo_month_panel.csv.gz"
echo "QC output:                       ${OUTPUT_DIR}/python_sonarqube_complexity_qc.csv"
echo "Summary:                         ${OUTPUT_DIR}/python_sonarqube_complexity_summary.csv"
echo "Log file:                        ${LOG_FILE}"
echo "Next:                            inspect scope mismatches, then run complexity DiD"
echo "================================================================================"
