#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-${PROJECT_ROOT}/proc_script_x01/summarize_python_quality_burden_did.py}"
INPUT="${INPUT:-${PROJECT_ROOT}/repo_x01/run-x-b07/python_quality_static_effects.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/repo_x01/run-y-b03/python-quality-burden-did-table-v1}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/logs/run-y-b03}"

CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"
EXPECTED_FECS_SPEC="${EXPECTED_FECS_SPEC:-adjusted_burden}"
EXPECTED_FEOS_SPEC="${EXPECTED_FEOS_SPEC:-fe_only_burden}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_TREATED_OBSERVATIONS="${EXPECTED_TREATED_OBSERVATIONS:-363}"
EXPECTED_FIRST_STAGE_OBSERVATIONS="${EXPECTED_FIRST_STAGE_OBSERVATIONS:-1591}"
EXPECTED_PANEL_OBSERVATIONS="${EXPECTED_PANEL_OBSERVATIONS:-1954}"
OVERWRITE="${OVERWRITE:-0}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" || "${1:-}" == "--self-test" ]]; then
  exec "${PYTHON_BIN}" "${PYTHON_SCRIPT}" "$@"
fi

for required_file in "${PYTHON_SCRIPT}" "${INPUT}"; do
  if [[ ! -f "${required_file}" ]]; then
    printf 'ERROR: required file not found: %s\n' "${required_file}" >&2
    exit 2
  fi
done

mkdir -p "${LOG_DIR}"
RUN_STAMP="$(date -u +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/run-y-b03-v1-${RUN_STAMP}-$$.log"

ARGS=(
  --input "${INPUT}"
  --output-dir "${OUTPUT_DIR}"
  --confidence-level "${CONFIDENCE_LEVEL}"
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

printf 'run-y-b03 v1 | log: %s\n' "${LOG_FILE}"
"${PYTHON_BIN}" "${PYTHON_SCRIPT}" "${ARGS[@]}" "$@" 2>&1 | tee "${LOG_FILE}"
