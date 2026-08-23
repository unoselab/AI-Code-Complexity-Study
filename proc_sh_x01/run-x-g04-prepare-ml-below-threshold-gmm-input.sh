#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-g04 v2: prepare ML-below-threshold GMM input only
#
# Purpose
# -------
# Build and validate the zero-inclusive repo-month quality panel that will be
# consumed later by run-x-g05. This wrapper DOES NOT fit any GMM model.
#
# Input lineage
# -------------
# A04: canonical historical-file token-weighted ML AGC share.
# D02: canonical repo-month/file SonarQube burden.
# B06: authoritative 1,954-row repo-month panel for file-count reconciliation.
# D05: validated primary ML-selected panel used for exact reproduction auditing.
#
# Output contract
# ---------------
# repo_x01/run-x-g04/ml_below_threshold_repo_month_panel.csv.gz
#   - one row per authoritative repo-month (1,954 rows)
#   - selected_* columns represent files with finite weighted ML AGC share <= 0.50
#   - missing/non-finite ML-share files remain unclassified and are excluded
#   - downstream run-x-g05 should join velocity/covariates from B06
#
# Additional outputs record support, D05 reproduction, hard QC, and provenance.
# ============================================================

RUN_PREFIX="run-x-g04"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/prepare_ml_below_threshold_gmm_input.py}"

A04_FILE="${A04_FILE:-../../ai_detector/src/app/data_did_agc_analysis/run-x-a04/python_ml_fun_file_scores.csv}"
D02_FILE="${D02_FILE:-repo_x01/run-x-d02/python_fun_file_quality_burden.csv.gz}"
B06_FILE="${B06_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
D05_REFERENCE_FILE="${D05_REFERENCE_FILE:-repo_x01/run-x-d05/quality_ml_fun_repo_month_panel.csv.gz}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-g04}"
LOG_DIR="${LOG_DIR:-logs}"

EXPECTED_A04_ROWS="${EXPECTED_A04_ROWS:-494592}"
EXPECTED_D02_ROWS="${EXPECTED_D02_ROWS:-510297}"
EXPECTED_D02_UNIQUE_FILES="${EXPECTED_D02_UNIQUE_FILES:-494592}"
EXPECTED_B06_ROWS="${EXPECTED_B06_ROWS:-1954}"
EXPECTED_ML_ELIGIBLE_ROWS="${EXPECTED_ML_ELIGIBLE_ROWS:-204509}"
EXPECTED_ML_ELIGIBLE_UNIQUE_FILES="${EXPECTED_ML_ELIGIBLE_UNIQUE_FILES:-196644}"
EXPECTED_ML_ABOVE_ROWS="${EXPECTED_ML_ABOVE_ROWS:-43325}"
EXPECTED_ML_ABOVE_UNIQUE_FILES="${EXPECTED_ML_ABOVE_UNIQUE_FILES:-41905}"
EXPECTED_ML_ABOVE_ISSUE_STOCK="${EXPECTED_ML_ABOVE_ISSUE_STOCK:-48478}"
EXPECTED_ML_BELOW_ROWS="${EXPECTED_ML_BELOW_ROWS:-161184}"
EXPECTED_ML_BELOW_UNIQUE_FILES="${EXPECTED_ML_BELOW_UNIQUE_FILES:-154739}"

EXPECTED_A04_SHA256="${EXPECTED_A04_SHA256:-b04db6462e74dfd3161d1680425a0335361e86093754ee2341f5c9e0e84e6518}"
EXPECTED_D02_SHA256="${EXPECTED_D02_SHA256:-443a9ce29969a60b186fdb3cc02a48410753d2a9f408ef95145ceb2a569945df}"
EXPECTED_B06_SHA256="${EXPECTED_B06_SHA256:-e34c56d1dda8342106a87314a9425c0ab2323ed0414c533a0f17c9c88e4f5027}"
EXPECTED_D05_SHA256="${EXPECTED_D05_SHA256:-970919c66c06c9e0c0eb88d459a9fcd916728ff4483ae7a9af559702785ebbd1}"

ML_THRESHOLD="0.50"
PROJECT_ROOT="$(pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/${RUN_LABEL}-prepare-ml-below-threshold-gmm-input-${TIMESTAMP}.log"

for required_file in "${PY_SCRIPT}" "${A04_FILE}" "${D02_FILE}" "${B06_FILE}" "${D05_REFERENCE_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

PYTHON_VERSION="$(${PYTHON_BIN} --version 2>&1)"
PY_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
A04_SHA256="$(sha256sum "${A04_FILE}" | awk '{print $1}')"
D02_SHA256="$(sha256sum "${D02_FILE}" | awk '{print $1}')"
B06_SHA256="$(sha256sum "${B06_FILE}" | awk '{print $1}')"
D05_SHA256="$(sha256sum "${D05_REFERENCE_FILE}" | awk '{print $1}')"

for hash_pair in \
  "A04:${A04_SHA256}:${EXPECTED_A04_SHA256}" \
  "D02:${D02_SHA256}:${EXPECTED_D02_SHA256}" \
  "B06:${B06_SHA256}:${EXPECTED_B06_SHA256}" \
  "D05:${D05_SHA256}:${EXPECTED_D05_SHA256}"; do
  IFS=':' read -r label observed expected <<< "${hash_pair}"
  if [[ "${observed}" != "${expected}" ]]; then
    echo "ERROR: ${label} SHA256 mismatch: expected ${expected}, observed ${observed}" >&2
    exit 1
  fi
done

cat <<EOF
============================================================
${RUN_LABEL}: prepare ML-below-threshold GMM input
Started:                         $(date)
Project root:                    ${PROJECT_ROOT}
Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})
Implementation version:          ${IMPLEMENTATION_VERSION}
Experiment role:                 GMM input preparation only
Downstream experiment:           run-x-g05
ML eligibility:                  finite token-weighted file AGC share
High-ML reference:               weighted ML AGC share > ${ML_THRESHOLD}
G04 subset:                      finite weighted ML AGC share <= ${ML_THRESHOLD}
Unclassified ML files:           excluded from G04 subset
A04 missing file SHA policy:      preserve/audit canonical missing SHA rows
A04 ML file scores:              ${A04_FILE}
A04 SHA256:                      ${A04_SHA256}
D02 file burden:                 ${D02_FILE}
D02 SHA256:                      ${D02_SHA256}
B06 panel:                       ${B06_FILE}
B06 SHA256:                      ${B06_SHA256}
D05 ML reproduction reference:   ${D05_REFERENCE_FILE}
D05 SHA256:                      ${D05_SHA256}
Expected eligible/above/below:   ${EXPECTED_ML_ELIGIBLE_ROWS}/${EXPECTED_ML_ABOVE_ROWS}/${EXPECTED_ML_BELOW_ROWS}
Expected unique elig/above/below:${EXPECTED_ML_ELIGIBLE_UNIQUE_FILES}/${EXPECTED_ML_ABOVE_UNIQUE_FILES}/${EXPECTED_ML_BELOW_UNIQUE_FILES}
Output directory:                ${OUTPUT_DIR}
Primary G05 input:               ${OUTPUT_DIR}/ml_below_threshold_repo_month_panel.csv.gz
Python script SHA256:            ${PY_SHA256}
Log file:                        ${LOG_FILE}
============================================================
EOF

printf '\n** Step 1: Build finite-ML-share below-threshold repo-month panel\n'
printf '%s\n' '------------------------------------------------------------'
"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"
"${PYTHON_BIN}" "${PY_SCRIPT}" \
  --a04-file "${A04_FILE}" \
  --d02-file "${D02_FILE}" \
  --b06-file "${B06_FILE}" \
  --d05-reference-file "${D05_REFERENCE_FILE}" \
  --output-dir "${OUTPUT_DIR}" \
  --expected-a04-rows "${EXPECTED_A04_ROWS}" \
  --expected-d02-rows "${EXPECTED_D02_ROWS}" \
  --expected-d02-unique-files "${EXPECTED_D02_UNIQUE_FILES}" \
  --expected-b06-rows "${EXPECTED_B06_ROWS}" \
  --expected-eligible-rows "${EXPECTED_ML_ELIGIBLE_ROWS}" \
  --expected-eligible-unique-files "${EXPECTED_ML_ELIGIBLE_UNIQUE_FILES}" \
  --expected-above-rows "${EXPECTED_ML_ABOVE_ROWS}" \
  --expected-above-unique-files "${EXPECTED_ML_ABOVE_UNIQUE_FILES}" \
  --expected-above-issue-stock "${EXPECTED_ML_ABOVE_ISSUE_STOCK}" \
  --expected-below-rows "${EXPECTED_ML_BELOW_ROWS}" \
  --expected-below-unique-files "${EXPECTED_ML_BELOW_UNIQUE_FILES}"

printf '\n** Step 2: Verify G04 artifacts, schema, and hard QC\n'
printf '%s\n' '------------------------------------------------------------'
EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/ml_below_threshold_repo_month_panel.csv.gz"
  "${OUTPUT_DIR}/ml_below_threshold_support.csv"
  "${OUTPUT_DIR}/ml_below_threshold_reproduction_audit.csv"
  "${OUTPUT_DIR}/ml_below_threshold_qc.csv"
  "${OUTPUT_DIR}/ml_below_threshold_metadata.csv"
)
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output missing: ${output_file}" >&2
    exit 1
  fi
  echo "OK: ${output_file}"
done

"${PYTHON_BIN}" - \
  "${OUTPUT_DIR}/ml_below_threshold_repo_month_panel.csv.gz" \
  "${OUTPUT_DIR}/ml_below_threshold_qc.csv" <<'PY'
import csv
import gzip
import sys

panel_path, qc_path = sys.argv[1:]
required_columns = {
    "repo_id",
    "time_index",
    "selected_file_rows",
    "selected_issue_total",
    "log1p_selected_issue_total",
    "ml_threshold",
    "ml_eligibility_rule",
    "ml_above_rule",
    "ml_below_rule",
    "ml_unclassified_rule",
}
with gzip.open(panel_path, "rt", newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    columns = set(reader.fieldnames or [])
    rows = list(reader)
missing = sorted(required_columns - columns)
if missing:
    raise SystemExit(f"G05 input contract missing columns: {missing}")
if len(rows) != 1954:
    raise SystemExit(f"G05 input row mismatch: expected 1954, observed {len(rows)}")
if any(row["ml_eligibility_rule"] != "finite_weighted_ML_AGC_share" for row in rows):
    raise SystemExit("Unexpected ML eligibility rule in G04 panel")
if any(row["ml_below_rule"] != "finite_ML_share_LE_primary_threshold" for row in rows):
    raise SystemExit("Unexpected ML below-threshold rule in G04 panel")
if any(abs(float(row["ml_threshold"]) - 0.50) > 1e-12 for row in rows):
    raise SystemExit("Unexpected ML threshold in G04 panel")

with open(qc_path, newline="", encoding="utf-8") as handle:
    qc_rows = list(csv.DictReader(handle))
failed = [row for row in qc_rows if row.get("status") == "fail"]
if failed:
    raise SystemExit(f"Hard QC failure in {qc_path}: {failed}")
print("G05 input contract: PASS")
print("Hard QC: PASS")
PY

printf '\n** Step 3: Show ML partition support\n'
printf '%s\n' '------------------------------------------------------------'
"${PYTHON_BIN}" - "${OUTPUT_DIR}/ml_below_threshold_support.csv" <<'PY'
import csv
import sys
with open(sys.argv[1], newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
for row in rows:
    print(
        f"{row['selection']}: files={row['expanded_repo_month_file_rows']}, "
        f"unique={row['unique_historical_files']}, issues={row['issue_stock']}, "
        f"repo_months={row['repo_months_with_files']}"
    )
PY

cat <<EOF
============================================================
${RUN_LABEL}: SUCCESS
Finished:                        $(date)
G04 definition:                  finite weighted ML AGC share <= ${ML_THRESHOLD}
Unclassified ML files:           excluded
D05 high-ML reproduction:        PASS
Threshold partition:             Eligible = Above + Below
G05 input contract:              PASS
Primary G05 input:               ${OUTPUT_DIR}/ml_below_threshold_repo_month_panel.csv.gz
Support:                         ${OUTPUT_DIR}/ml_below_threshold_support.csv
QC:                              ${OUTPUT_DIR}/ml_below_threshold_qc.csv
Metadata:                        ${OUTPUT_DIR}/ml_below_threshold_metadata.csv
Log file:                        ${LOG_FILE}
============================================================
EOF
