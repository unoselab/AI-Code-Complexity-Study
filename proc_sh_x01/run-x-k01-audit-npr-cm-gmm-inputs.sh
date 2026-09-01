#!/usr/bin/env bash
# Audit NPR-CM dynamic-panel GMM inputs before fitting the new CM interaction model.
#
# This wrapper is standalone. Its execution structure was copied from the existing
# run-x-h01 threshold-audit wrapper and adapted for K01 NPR-CM GMM-readiness checks.
# It does not call or depend on any previous shell wrapper.
#
# Versioned delivery files:
#   proc_script_x01/audit_npr_cm_gmm_inputs-v1.py
#   proc_sh_x01/run-x-k01-audit-npr-cm-gmm-inputs-v1.sh
#
# Canonical server filenames after deployment:
#   proc_script_x01/audit_npr_cm_gmm_inputs.py
#   proc_sh_x01/run-x-k01-audit-npr-cm-gmm-inputs.sh
#
# Required inputs:
#   repo_x01/run-x-h03/quality_cfun_npr_threshold_repo_month_panel.csv.gz
#       Existing CM/class-method NPR threshold x quality repo-month panel.
#   repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv
#       Authoritative 1,954-row Python panel containing velocity, treatment timing,
#       and time-varying controls used by the existing dynamic-panel analyses.
#
# K01 validates, without fitting a GMM model:
#   1. H03 primary full-sample NPR-CM threshold contract (tau_NPR=1.571637, strict >).
#   2. H03/B06 repo-month identity and treatment-timing agreement.
#   3. log1p(selected_issue_total) recomputation.
#   4. Finite velocity/covariate values.
#   5. Exact-calendar t-1/t-2 support used by the GMM design.
#   6. Expected active sample: 1,631 rows, 146 repos, 61 treated, 85 controls,
#      and 350 active post-adoption treated observations.
#
# Main outputs under repo_x01/run-x-k01/:
#   k01_npr_cm_gmm_input_checks.csv
#   k01_npr_cm_gmm_input_summary.csv
#   k01_npr_cm_exact_calendar_sample.csv.gz
#   summary.json
#   metadata.json
#
# Runtime:
#   Python 3.11.x; CPU only. Requires pandas and numpy already used by project scripts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "${PROJECT_ROOT}"
export PROJECT_ROOT

RUN_PREFIX="run-x-k01"
IMPLEMENTATION_VERSION="v1"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/audit_npr_cm_gmm_inputs.py}"
H03_PANEL_FILE="${H03_PANEL_FILE:-repo_x01/run-x-h03/quality_cfun_npr_threshold_repo_month_panel.csv.gz}"
B06_PANEL_FILE="${B06_PANEL_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-k01}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/${RUN_LABEL}-audit-npr-cm-gmm-inputs-${RUN_TS}.log}"
RUN_SELF_TEST="${RUN_SELF_TEST:-1}"

PRIMARY_THRESHOLD="1.571637"
EXPECTED_H03_LONG_ROWS="85118"
EXPECTED_PANEL_ROWS="1954"
EXPECTED_REPOSITORIES="167"
EXPECTED_TREATMENT_REPOSITORIES="63"
EXPECTED_CONTROL_REPOSITORIES="104"
EXPECTED_ACTIVE_ROWS="1631"
EXPECTED_ACTIVE_REPOSITORIES="146"
EXPECTED_ACTIVE_TREATMENT_REPOSITORIES="61"
EXPECTED_ACTIVE_CONTROL_REPOSITORIES="85"
EXPECTED_ACTIVE_POST_TREATED_ROWS="350"

for required_file in "${PY_SCRIPT}" "${H03_PANEL_FILE}" "${B06_PANEL_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 2
  fi
done

PYTHON_VERSION="$(${PYTHON_BIN} -c 'import platform; print(platform.python_version())')"
PYTHON_MAJOR_MINOR="$(${PYTHON_BIN} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "${PYTHON_MAJOR_MINOR}" != "3.11" ]]; then
  echo "ERROR: K01 requires Python 3.11.x; found ${PYTHON_VERSION}" >&2
  exit 2
fi

${PYTHON_BIN} - <<'PY'
import importlib.util
missing = [name for name in ("numpy", "pandas") if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit("ERROR: missing required Python packages: " + ", ".join(missing))
PY

mkdir -p "${OUTPUT_DIR}" "${LOG_DIR}"
PY_SCRIPT_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
H03_PANEL_SHA256="$(sha256sum "${H03_PANEL_FILE}" | awk '{print $1}')"
B06_PANEL_SHA256="$(sha256sum "${B06_PANEL_FILE}" | awk '{print $1}')"

exec > >(tee "${LOG_FILE}") 2>&1
START_EPOCH="$(date +%s)"

echo "============================================================================"
echo "${RUN_LABEL}: audit NPR-CM GMM inputs"
echo "Started:                         $(date)"
echo "Project root:                    ${PROJECT_ROOT}"
echo "Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})"
echo "Python script:                   ${PY_SCRIPT}"
echo "Python script SHA256:            ${PY_SCRIPT_SHA256}"
echo "H03 CM-NPR panel:                ${H03_PANEL_FILE}"
echo "H03 panel SHA256:                ${H03_PANEL_SHA256}"
echo "B06 Python panel:                ${B06_PANEL_FILE}"
echo "B06 panel SHA256:                ${B06_PANEL_SHA256}"
echo "Detector/scope:                  NPR / CM"
echo "Primary threshold:               ${PRIMARY_THRESHOLD}"
echo "Localized quality:               log1p_selected_issue_total"
echo "Velocity:                        log_lines_added_py_source"
echo "Exact-calendar rule:             require exact t-1 and t-2"
echo "Expected active rows/repos:      ${EXPECTED_ACTIVE_ROWS}/${EXPECTED_ACTIVE_REPOSITORIES}"
echo "Expected active T/C repos:       ${EXPECTED_ACTIVE_TREATMENT_REPOSITORIES}/${EXPECTED_ACTIVE_CONTROL_REPOSITORIES}"
echo "Expected active post-T rows:     ${EXPECTED_ACTIVE_POST_TREATED_ROWS}"
echo "GMM model fit:                   none (audit only)"
echo "Output directory:                ${OUTPUT_DIR}"
echo "Log file:                        ${LOG_FILE}"
echo "============================================================================"

if [[ "${RUN_SELF_TEST}" == "1" ]]; then
  echo
  echo "** Step 1: Run K01 structural self-test"
  echo "----------------------------------------------------------------------------"
  "${PYTHON_BIN}" "${PY_SCRIPT}" --self-test
fi

echo
echo "** Step 2: Compile K01 Python program"
echo "----------------------------------------------------------------------------"
"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"

echo
echo "** Step 3: Audit H03 NPR-CM and B06 GMM inputs"
echo "----------------------------------------------------------------------------"
set +e
"${PYTHON_BIN}" "${PY_SCRIPT}" \
  --h03-panel-file "${H03_PANEL_FILE}" \
  --b06-panel-file "${B06_PANEL_FILE}" \
  --output-dir "${OUTPUT_DIR}" \
  --primary-threshold "${PRIMARY_THRESHOLD}" \
  --expected-h03-long-rows "${EXPECTED_H03_LONG_ROWS}" \
  --expected-panel-rows "${EXPECTED_PANEL_ROWS}" \
  --expected-repositories "${EXPECTED_REPOSITORIES}" \
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}" \
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}" \
  --expected-active-rows "${EXPECTED_ACTIVE_ROWS}" \
  --expected-active-repositories "${EXPECTED_ACTIVE_REPOSITORIES}" \
  --expected-active-treatment-repositories "${EXPECTED_ACTIVE_TREATMENT_REPOSITORIES}" \
  --expected-active-control-repositories "${EXPECTED_ACTIVE_CONTROL_REPOSITORIES}" \
  --expected-active-post-treated-rows "${EXPECTED_ACTIVE_POST_TREATED_ROWS}"
EXIT_CODE=$?
set -e

END_EPOCH="$(date +%s)"
ELAPSED=$((END_EPOCH - START_EPOCH))
printf -v ELAPSED_TEXT '%02d:%02d:%02d' $((ELAPSED / 3600)) $(((ELAPSED % 3600) / 60)) $((ELAPSED % 60))

echo
echo "============================================================================"
echo "${RUN_LABEL} execution summary"
echo "Completed:        $(date)"
echo "Elapsed:          ${ELAPSED_TEXT}"
echo "Exit code:        ${EXIT_CODE}"
echo "Output directory: ${OUTPUT_DIR}"
echo "Log file:         ${LOG_FILE}"
for output_file in \
  k01_npr_cm_gmm_input_checks.csv \
  k01_npr_cm_gmm_input_summary.csv \
  k01_npr_cm_exact_calendar_sample.csv.gz \
  summary.json \
  metadata.json; do
  if [[ -f "${OUTPUT_DIR}/${output_file}" ]]; then
    echo "OK: ${OUTPUT_DIR}/${output_file}"
  else
    echo "MISSING: ${OUTPUT_DIR}/${output_file}"
  fi
done
echo "============================================================================"

exit "${EXIT_CODE}"
