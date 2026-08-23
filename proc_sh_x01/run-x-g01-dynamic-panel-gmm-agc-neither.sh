#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-g01 v3: neither-detector localized quality -> velocity GMM
# ============================================================
#
# Inputs:
#   D02: canonical repo-month/file SonarQube burden + NPR file score
#   A04: ML file score table
#   B06: authoritative whole-Python velocity/timing/covariate panel
#   D03: NPR primary reference used only for exact reproduction QC
#   D05: ML primary reference used only for exact reproduction QC
#
# Outputs:
#   1. Exact all-Python minus (NPR OR ML) complement aggregated to 1,954 repo-months.
#   2. Detector overlap/support and exact D03/D05 reproduction audits.
#   3. G01 two-step difference-GMM result and diagnostics.
#
# This wrapper is standalone and does not call any previous experiment shell.
# ============================================================

RUN_PREFIX="run-x-g01"
IMPLEMENTATION_VERSION="v3"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"

PYTHON_BIN="${PYTHON_BIN:-python}"
RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/build_agc_detector_neither_gmm_panel.py}"
R_SCRIPT="${R_SCRIPT:-proc_script_x01/dynamic_panel_gmm_agc_neither.R}"

D02_FILE="${D02_FILE:-repo_x01/run-x-d02/python_fun_file_quality_burden.csv.gz}"
A04_FILE="${A04_FILE:-../../ai_detector/src/app/data_did_agc_analysis/run-x-a04/python_ml_fun_file_scores.csv}"
B06_FILE="${B06_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
D03_REFERENCE_FILE="${D03_REFERENCE_FILE:-repo_x01/run-x-d03/quality_fun_npr_threshold_repo_month_panel.csv.gz}"
D05_REFERENCE_FILE="${D05_REFERENCE_FILE:-repo_x01/run-x-d05/quality_ml_fun_repo_month_panel.csv.gz}"
OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-g01}"
LOG_DIR="${LOG_DIR:-logs}"

EXPECTED_D02_ROWS="${EXPECTED_D02_ROWS:-510297}"
EXPECTED_A04_ROWS="${EXPECTED_A04_ROWS:-494592}"
EXPECTED_B06_ROWS="${EXPECTED_B06_ROWS:-1954}"
EXPECTED_NEITHER_EXPANDED_ROWS="${EXPECTED_NEITHER_EXPANDED_ROWS:-456852}"
EXPECTED_NEITHER_UNIQUE_FILES="${EXPECTED_NEITHER_UNIQUE_FILES:-443390}"
EXPECTED_UNION_EXPANDED_ROWS="${EXPECTED_UNION_EXPANDED_ROWS:-53445}"
EXPECTED_UNION_UNIQUE_FILES="${EXPECTED_UNION_UNIQUE_FILES:-51202}"
EXPECTED_UNION_ISSUE_STOCK="${EXPECTED_UNION_ISSUE_STOCK:-64901}"
EXPECTED_REPOSITORIES="${EXPECTED_REPOSITORIES:-167}"
EXPECTED_TREATMENT_REPOSITORIES="${EXPECTED_TREATMENT_REPOSITORIES:-63}"
EXPECTED_CONTROL_REPOSITORIES="${EXPECTED_CONTROL_REPOSITORIES:-104}"
EXPECTED_ACTIVE_ROWS="${EXPECTED_ACTIVE_ROWS:-1631}"
EXPECTED_ACTIVE_REPOSITORIES="${EXPECTED_ACTIVE_REPOSITORIES:-146}"
EXPECTED_LEGACY_MISMATCH_ROWS="${EXPECTED_LEGACY_MISMATCH_ROWS:-11}"
EXPECTED_LEGACY_MISMATCH_REPOSITORIES="${EXPECTED_LEGACY_MISMATCH_REPOSITORIES:-3}"
CONFIDENCE_LEVEL="${CONFIDENCE_LEVEL:-0.95}"

# Frozen upstream hashes. These gates ensure G01 uses the same authoritative
# artifacts as the validated NPR and ML analyses.
EXPECTED_D02_SHA256="${EXPECTED_D02_SHA256:-443a9ce29969a60b186fdb3cc02a48410753d2a9f408ef95145ceb2a569945df}"
EXPECTED_A04_SHA256="${EXPECTED_A04_SHA256:-b04db6462e74dfd3161d1680425a0335361e86093754ee2341f5c9e0e84e6518}"
EXPECTED_B06_SHA256="${EXPECTED_B06_SHA256:-e34c56d1dda8342106a87314a9425c0ab2323ed0414c533a0f17c9c88e4f5027}"
EXPECTED_D03_SHA256="${EXPECTED_D03_SHA256:-91def6a5e5b2b611d0b4875db8d348b3d1c61a91924b30a6f63f37b5b2be20af}"
EXPECTED_D05_SHA256="${EXPECTED_D05_SHA256:-970919c66c06c9e0c0eb88d459a9fcd916728ff4483ae7a9af559702785ebbd1}"

NPR_THRESHOLD="1.571637"
ML_THRESHOLD="0.50"

PROJECT_ROOT="$(pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/${RUN_LABEL}-dynamic-panel-gmm-agc-neither-${TIMESTAMP}.log"

for required_file in "${PY_SCRIPT}" "${R_SCRIPT}" "${D02_FILE}" "${A04_FILE}" "${B06_FILE}" "${D03_REFERENCE_FILE}" "${D05_REFERENCE_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

exec > >(tee -a "${LOG_FILE}") 2>&1

PYTHON_VERSION="$(${PYTHON_BIN} --version 2>&1)"
R_VERSION="$(${RSCRIPT_BIN} --version 2>&1 | head -n 1)"
PY_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
R_SHA256="$(sha256sum "${R_SCRIPT}" | awk '{print $1}')"
D02_SHA256="$(sha256sum "${D02_FILE}" | awk '{print $1}')"
A04_SHA256="$(sha256sum "${A04_FILE}" | awk '{print $1}')"
B06_SHA256="$(sha256sum "${B06_FILE}" | awk '{print $1}')"
D03_SHA256="$(sha256sum "${D03_REFERENCE_FILE}" | awk '{print $1}')"
D05_SHA256="$(sha256sum "${D05_REFERENCE_FILE}" | awk '{print $1}')"

for hash_pair in \
  "D02:${D02_SHA256}:${EXPECTED_D02_SHA256}" \
  "A04:${A04_SHA256}:${EXPECTED_A04_SHA256}" \
  "B06:${B06_SHA256}:${EXPECTED_B06_SHA256}" \
  "D03:${D03_SHA256}:${EXPECTED_D03_SHA256}" \
  "D05:${D05_SHA256}:${EXPECTED_D05_SHA256}"; do
  IFS=':' read -r label observed expected <<< "${hash_pair}"
  if [[ "${observed}" != "${expected}" ]]; then
    echo "ERROR: ${label} SHA256 mismatch: expected ${expected}, observed ${observed}" >&2
    exit 1
  fi
done

cat <<EOF
============================================================
${RUN_LABEL}: neither-detector localized quality GMM
Started:                         $(date)
Project root:                    ${PROJECT_ROOT}
Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})
Rscript:                         $(command -v "${RSCRIPT_BIN}")
R version:                       ${R_VERSION}
Implementation version:          ${IMPLEMENTATION_VERSION}
Union audit rule:                NPR primary OR ML primary
Neither rule:                    all Python MINUS (NPR OR ML)
NPR rule:                        file NPR > ${NPR_THRESHOLD}
ML rule:                         weighted ML AGC share > ${ML_THRESHOLD}
Complement policy:               canonical D02/A04 all MINUS detector union
B06 issue-total comparison:      audit-only (alias-policy semantics)
D02 file burden:                 ${D02_FILE}
D02 SHA256:                      ${D02_SHA256}
A04 ML file scores:              ${A04_FILE}
A04 SHA256:                      ${A04_SHA256}
B06 panel:                       ${B06_FILE}
B06 SHA256:                      ${B06_SHA256}
D03 NPR reproduction reference:  ${D03_REFERENCE_FILE}
D03 SHA256:                      ${D03_SHA256}
D05 ML reproduction reference:   ${D05_REFERENCE_FILE}
D05 SHA256:                      ${D05_SHA256}
Output directory:                ${OUTPUT_DIR}
Estimator:                       two-step difference GMM, two-way effects
Instrument:                      lag(velocity,2); collapse=FALSE
Expected active rows/repos:      ${EXPECTED_ACTIVE_ROWS}/${EXPECTED_ACTIVE_REPOSITORIES}
Log file:                        ${LOG_FILE}
============================================================
EOF

printf '\n** Step 1: Build all-Python minus detector-union quality panel\n'
printf '%s\n' '------------------------------------------------------------'
"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"
"${PYTHON_BIN}" "${PY_SCRIPT}" \
  --d02-file "${D02_FILE}" \
  --a04-file "${A04_FILE}" \
  --b06-file "${B06_FILE}" \
  --d03-reference-file "${D03_REFERENCE_FILE}" \
  --d05-reference-file "${D05_REFERENCE_FILE}" \
  --output-dir "${OUTPUT_DIR}" \
  --expected-d02-rows "${EXPECTED_D02_ROWS}" \
  --expected-a04-rows "${EXPECTED_A04_ROWS}" \
  --expected-b06-rows "${EXPECTED_B06_ROWS}" \
  --expected-neither-expanded-rows "${EXPECTED_NEITHER_EXPANDED_ROWS}" \
  --expected-neither-unique-files "${EXPECTED_NEITHER_UNIQUE_FILES}" \
  --expected-union-expanded-rows "${EXPECTED_UNION_EXPANDED_ROWS}" \
  --expected-union-unique-files "${EXPECTED_UNION_UNIQUE_FILES}" \
  --expected-union-issue-stock "${EXPECTED_UNION_ISSUE_STOCK}"

NEITHER_PANEL="${OUTPUT_DIR}/agc_detector_neither_repo_month_panel.csv.gz"

printf '\n** Step 2: Fit G01 neither-selected dynamic panel GMM\n'
printf '%s\n' '------------------------------------------------------------'
"${RSCRIPT_BIN}" -e "parse(file='${R_SCRIPT}'); cat('R parse: PASS\\n')"
"${RSCRIPT_BIN}" "${R_SCRIPT}" \
  --input-file "${NEITHER_PANEL}" \
  --b06-panel-file "${B06_FILE}" \
  --output-dir "${OUTPUT_DIR}" \
  --script-path "${R_SCRIPT}" \
  --implementation-version "${IMPLEMENTATION_VERSION}" \
  --confidence-level "${CONFIDENCE_LEVEL}" \
  --expected-rows "${EXPECTED_B06_ROWS}" \
  --expected-repositories "${EXPECTED_REPOSITORIES}" \
  --expected-treatment-repositories "${EXPECTED_TREATMENT_REPOSITORIES}" \
  --expected-control-repositories "${EXPECTED_CONTROL_REPOSITORIES}" \
  --expected-active-rows "${EXPECTED_ACTIVE_ROWS}" \
  --expected-active-repositories "${EXPECTED_ACTIVE_REPOSITORIES}" \
  --expected-legacy-mismatch-rows "${EXPECTED_LEGACY_MISMATCH_ROWS}" \
  --expected-legacy-mismatch-repositories "${EXPECTED_LEGACY_MISMATCH_REPOSITORIES}" \
  --strict-expected-counts 1

printf '\n** Step 3: Verify G01 artifacts and hard QC\n'
printf '%s\n' '------------------------------------------------------------'
EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/agc_detector_neither_repo_month_panel.csv.gz"
  "${OUTPUT_DIR}/agc_detector_neither_support.csv"
  "${OUTPUT_DIR}/agc_detector_neither_reproduction_audit.csv"
  "${OUTPUT_DIR}/agc_detector_neither_join_audit.csv"
  "${OUTPUT_DIR}/agc_detector_neither_qc.csv"
  "${OUTPUT_DIR}/agc_detector_neither_metadata.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_coefficients.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_primary_summary.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_diagnostics.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_sample_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_instrument_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_b06_join_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_numeric_coercion_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_calendar_gap_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_legacy_flag_audit.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_qc.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_run_metadata.csv"
  "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_models.rds"
)
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output missing: ${output_file}" >&2
    exit 1
  fi
  echo "OK: ${output_file}"
done

"${PYTHON_BIN}" - "${OUTPUT_DIR}/agc_detector_neither_qc.csv" "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_qc.csv" <<'PY'
import csv
import sys
for path in sys.argv[1:]:
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    failed = [r for r in rows if r.get('status') == 'fail']
    if failed:
        raise SystemExit(f"Hard QC failure in {path}: {failed}")
print("Hard QC: PASS")
PY

printf '\n** Step 4: G01 neither support and GMM result\n'
printf '%s\n' '------------------------------------------------------------'
"${PYTHON_BIN}" - "${OUTPUT_DIR}/agc_detector_neither_support.csv" "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_primary_summary.csv" "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_diagnostics.csv" <<'PY'
import csv
import sys
support_path, primary_path, diagnostic_path = sys.argv[1:]
with open(support_path, newline='', encoding='utf-8') as f:
    support = list(csv.DictReader(f))
print("Detector selection support:")
for row in support:
    print(
        f"{row['selection']}: files={row['expanded_repo_month_file_rows']}, "
        f"unique={row['unique_historical_files']}, issues={row['issue_stock']}"
    )
with open(primary_path, newline='', encoding='utf-8') as f:
    primary = list(csv.DictReader(f))
if len(primary) != 1:
    raise SystemExit(f"Expected one primary coefficient row, found {len(primary)}")
r = primary[0]
print("Primary neither-quality coefficient:")
print(
    f"beta={r['estimate']}, se={r['std_error']}, ci=[{r['conf_low']}, {r['conf_high']}], "
    f"p={r['p_value']}, significant={r['significant']}"
)
with open(diagnostic_path, newline='', encoding='utf-8') as f:
    diagnostics = list(csv.DictReader(f))
print("Diagnostics:")
for row in diagnostics:
    print(f"{row['diagnostic']}: statistic={row['statistic']}, p={row['p_value']}, status={row['status']}")
PY

CAUTION_COUNT="$(${PYTHON_BIN} - "${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_qc.csv" <<'PY'
import csv, sys
with open(sys.argv[1], newline='', encoding='utf-8') as f:
    print(sum(1 for r in csv.DictReader(f) if r.get('status') == 'caution'))
PY
)"

cat <<EOF
============================================================
${RUN_LABEL}: SUCCESS
Finished:                        $(date)
Neither definition:              all Python MINUS (NPR > ${NPR_THRESHOLD} OR ML > ${ML_THRESHOLD})
D03 NPR reproduction:            PASS
D05 ML reproduction:             PASS
Complement algebra:              All = Union + Neither
QC caution rows:                 ${CAUTION_COUNT}
Primary result:                  ${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_primary_summary.csv
Detector overlap/support:        ${OUTPUT_DIR}/agc_detector_neither_support.csv
GMM diagnostics:                 ${OUTPUT_DIR}/dynamic_panel_gmm_agc_neither_diagnostics.csv
Log file:                        ${LOG_FILE}
============================================================
EOF
