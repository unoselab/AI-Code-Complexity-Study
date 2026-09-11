#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-${PROJECT_ROOT}/proc_script_x01/summarize_python_velocity_did.py}"

FECS_INPUT="${FECS_INPUT:-${PROJECT_ROOT}/repo_x01/run-x-b03/specs/python_ncloc_adjusted/sonarqube/velocity_python_added_lines_sonarqube_python_ncloc_adjusted_static_effects.csv}"
FEOS_INPUT="${FEOS_INPUT:-${PROJECT_ROOT}/repo_x01/run-x-b03/specs/no_covariates/sonarqube/velocity_python_added_lines_sonarqube_no_covariates_static_effects.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/repo_x01/run-y-b02/python-velocity-did-table-v1}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/logs/run-y-b02}"

CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
EXPECTED_BACKEND="${EXPECTED_BACKEND:-sonarqube}"
EXPECTED_FECS_SPEC="${EXPECTED_FECS_SPEC:-python_ncloc_adjusted}"
EXPECTED_FEOS_SPEC="${EXPECTED_FEOS_SPEC:-no_covariates}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_TREATED_OBSERVATIONS="${EXPECTED_TREATED_OBSERVATIONS:-363}"
EXPECTED_FIRST_STAGE_OBSERVATIONS="${EXPECTED_FIRST_STAGE_OBSERVATIONS:-1591}"
EXPECTED_PANEL_OBSERVATIONS="${EXPECTED_PANEL_OBSERVATIONS:-1954}"
OVERWRITE="${OVERWRITE:-0}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" || "${1:-}" == "--self-test" ]]; then
  exec "${PYTHON_BIN}" "${PYTHON_SCRIPT}" "$@"
fi

for required_file in "${PYTHON_SCRIPT}" "${FECS_INPUT}" "${FEOS_INPUT}"; do
  if [[ ! -f "${required_file}" ]]; then
    printf 'ERROR: required file not found: %s\n' "${required_file}" >&2
    exit 2
  fi
done

mkdir -p "${LOG_DIR}"
RUN_STAMP="$(date -u +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/run-y-b02-v1-${RUN_STAMP}-$$.log"

ARGS=(
  --fecs-input "${FECS_INPUT}"
  --feos-input "${FEOS_INPUT}"
  --output-dir "${OUTPUT_DIR}"
  --confidence-level "${CONFIDENCE_LEVEL}"
  --expected-backend "${EXPECTED_BACKEND}"
  --expected-fecs-spec "${EXPECTED_FECS_SPEC}"
  --expected-feos-spec "${EXPECTED_FEOS_SPEC}"
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}"
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}"
  --expected-treated-observations "${EXPECTED_TREATED_OBSERVATIONS}"
  --expected-first-stage-observations "${EXPECTED_FIRST_STAGE_OBSERVATIONS}"
  --expected-panel-observations "${EXPECTED_PANEL_OBSERVATIONS}"
  --verify-manuscript-rounding
)

if [[ "${OVERWRITE}" == "1" ]]; then
  ARGS+=(--overwrite)
fi

printf 'run-y-b02 v1 | log: %s\n' "${LOG_FILE}"
"${PYTHON_BIN}" "${PYTHON_SCRIPT}" "${ARGS[@]}" "$@" 2>&1 | tee "${LOG_FILE}"
