#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-g02 v2: prepare NPR-below-threshold GMM input only
#
# Purpose
# -------
# Build and validate the zero-inclusive repo-month quality panel that will be
# consumed later by run-x-g03. This wrapper DOES NOT fit any GMM model.
#
# Input lineage
# -------------
# D02: canonical repo-month/file SonarQube burden + continuous file NPR metric.
# B06: authoritative 1,954-row repo-month panel for file-count reconciliation.
# D03: validated high-NPR primary panel used for exact reproduction auditing.
#
# Output contract
# ---------------
# repo_x01/run-x-g02/npr_below_threshold_repo_month_panel.csv.gz
#   - one row per authoritative repo-month (1,954 rows)
#   - selected_* columns represent finite-NPR files with NPR <= 1.571637
#   - missing/non-finite NPR files remain unclassified and are excluded
#   - downstream run-x-g03 should join its velocity/covariates from B06
#
# Additional outputs record support, D03 reproduction, hard QC, and provenance.
# ============================================================

RUN_PREFIX="run-x-g02"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/prepare_npr_below_threshold_gmm_input.py}"

D02_FILE="${D02_FILE:-repo_x01/run-x-d02/python_fun_file_quality_burden.csv.gz}"
B06_FILE="${B06_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
D03_REFERENCE_FILE="${D03_REFERENCE_FILE:-repo_x01/run-x-d03/quality_fun_npr_threshold_repo_month_panel.csv.gz}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-g02}"
LOG_DIR="${LOG_DIR:-logs}"

EXPECTED_D02_ROWS="${EXPECTED_D02_ROWS:-510297}"
EXPECTED_D02_UNIQUE_FILES="${EXPECTED_D02_UNIQUE_FILES:-494592}"
EXPECTED_B06_ROWS="${EXPECTED_B06_ROWS:-1954}"
EXPECTED_NPR_ELIGIBLE_ROWS="${EXPECTED_NPR_ELIGIBLE_ROWS:-204508}"
EXPECTED_NPR_ABOVE_ROWS="${EXPECTED_NPR_ABOVE_ROWS:-13739}"
EXPECTED_NPR_ABOVE_ISSUE_STOCK="${EXPECTED_NPR_ABOVE_ISSUE_STOCK:-20306}"
EXPECTED_NPR_BELOW_ROWS="${EXPECTED_NPR_BELOW_ROWS:-190769}"

EXPECTED_D02_SHA256="${EXPECTED_D02_SHA256:-443a9ce29969a60b186fdb3cc02a48410753d2a9f408ef95145ceb2a569945df}"
EXPECTED_B06_SHA256="${EXPECTED_B06_SHA256:-e34c56d1dda8342106a87314a9425c0ab2323ed0414c533a0f17c9c88e4f5027}"
EXPECTED_D03_SHA256="${EXPECTED_D03_SHA256:-91def6a5e5b2b611d0b4875db8d348b3d1c61a91924b30a6f63f37b5b2be20af}"

NPR_THRESHOLD="1.571637"
PROJECT_ROOT="$(pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/${RUN_LABEL}-prepare-npr-below-threshold-gmm-input-${TIMESTAMP}.log"

for required_file in "${PY_SCRIPT}" "${D02_FILE}" "${B06_FILE}" "${D03_REFERENCE_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file not found: ${required_file}" >&2
    exit 1
  fi
done

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

PYTHON_VERSION="$(${PYTHON_BIN} --version 2>&1)"
PY_SHA256="$(sha256sum "${PY_SCRIPT}" | awk '{print $1}')"
D02_SHA256="$(sha256sum "${D02_FILE}" | awk '{print $1}')"
B06_SHA256="$(sha256sum "${B06_FILE}" | awk '{print $1}')"
D03_SHA256="$(sha256sum "${D03_REFERENCE_FILE}" | awk '{print $1}')"

for hash_pair in \
  "D02:${D02_SHA256}:${EXPECTED_D02_SHA256}" \
  "B06:${B06_SHA256}:${EXPECTED_B06_SHA256}" \
  "D03:${D03_SHA256}:${EXPECTED_D03_SHA256}"; do
  IFS=':' read -r label observed expected <<< "${hash_pair}"
  if [[ "${observed}" != "${expected}" ]]; then
    echo "ERROR: ${label} SHA256 mismatch: expected ${expected}, observed ${observed}" >&2
    exit 1
  fi
done

cat <<EOF
============================================================
${RUN_LABEL}: prepare NPR-below-threshold GMM input
Started:                         $(date)
Project root:                    ${PROJECT_ROOT}
Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})
Implementation version:          ${IMPLEMENTATION_VERSION}
Experiment role:                 GMM input preparation only
Downstream experiment:           run-x-g03
NPR eligibility:                 finite file NPR
High-NPR reference:              NPR > ${NPR_THRESHOLD}
G02 subset:                      finite NPR <= ${NPR_THRESHOLD}
Unclassified NPR files:          excluded from G02 subset
D02 file burden:                 ${D02_FILE}
D02 SHA256:                      ${D02_SHA256}
B06 panel:                       ${B06_FILE}
B06 SHA256:                      ${B06_SHA256}
D03 NPR reproduction reference:  ${D03_REFERENCE_FILE}
D03 SHA256:                      ${D03_SHA256}
Expected eligible/above/below:   ${EXPECTED_NPR_ELIGIBLE_ROWS}/${EXPECTED_NPR_ABOVE_ROWS}/${EXPECTED_NPR_BELOW_ROWS}
Output directory:                ${OUTPUT_DIR}
Primary G03 input:               ${OUTPUT_DIR}/npr_below_threshold_repo_month_panel.csv.gz
Python script SHA256:            ${PY_SHA256}
Log file:                        ${LOG_FILE}
============================================================
EOF

printf '\n** Step 1: Build finite-NPR below-threshold repo-month panel\n'
printf '%s\n' '------------------------------------------------------------'
"${PYTHON_BIN}" -m py_compile "${PY_SCRIPT}"
"${PYTHON_BIN}" "${PY_SCRIPT}" \
  --d02-file "${D02_FILE}" \
  --b06-file "${B06_FILE}" \
  --d03-reference-file "${D03_REFERENCE_FILE}" \
  --output-dir "${OUTPUT_DIR}" \
  --expected-d02-rows "${EXPECTED_D02_ROWS}" \
  --expected-d02-unique-files "${EXPECTED_D02_UNIQUE_FILES}" \
  --expected-b06-rows "${EXPECTED_B06_ROWS}" \
  --expected-eligible-rows "${EXPECTED_NPR_ELIGIBLE_ROWS}" \
  --expected-above-rows "${EXPECTED_NPR_ABOVE_ROWS}" \
  --expected-above-issue-stock "${EXPECTED_NPR_ABOVE_ISSUE_STOCK}" \
  --expected-below-rows "${EXPECTED_NPR_BELOW_ROWS}"

printf '\n** Step 2: Verify G02 artifacts, schema, and hard QC\n'
printf '%s\n' '------------------------------------------------------------'
EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/npr_below_threshold_repo_month_panel.csv.gz"
  "${OUTPUT_DIR}/npr_below_threshold_support.csv"
  "${OUTPUT_DIR}/npr_below_threshold_reproduction_audit.csv"
  "${OUTPUT_DIR}/npr_below_threshold_qc.csv"
  "${OUTPUT_DIR}/npr_below_threshold_metadata.csv"
)
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output missing: ${output_file}" >&2
    exit 1
  fi
  echo "OK: ${output_file}"
done

"${PYTHON_BIN}" - \
  "${OUTPUT_DIR}/npr_below_threshold_repo_month_panel.csv.gz" \
  "${OUTPUT_DIR}/npr_below_threshold_qc.csv" <<'PY'
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
    "npr_threshold",
    "npr_eligibility_rule",
    "npr_above_rule",
    "npr_below_rule",
    "npr_unclassified_rule",
}
with gzip.open(panel_path, "rt", newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    columns = set(reader.fieldnames or [])
    rows = list(reader)
missing = sorted(required_columns - columns)
if missing:
    raise SystemExit(f"G03 input contract missing columns: {missing}")
if len(rows) != 1954:
    raise SystemExit(f"G03 input row mismatch: expected 1954, observed {len(rows)}")
if any(row["npr_eligibility_rule"] != "finite_NPR" for row in rows):
    raise SystemExit("Unexpected NPR eligibility rule in G02 panel")
if any(row["npr_below_rule"] != "finite_NPR_LE_primary_threshold" for row in rows):
    raise SystemExit("Unexpected NPR below-threshold rule in G02 panel")

with open(qc_path, newline="", encoding="utf-8") as handle:
    qc_rows = list(csv.DictReader(handle))
failed = [row for row in qc_rows if row.get("status") == "fail"]
if failed:
    raise SystemExit(f"Hard QC failure in {qc_path}: {failed}")
print("G03 input contract: PASS")
print("Hard QC: PASS")
PY

printf '\n** Step 3: Show NPR partition support\n'
printf '%s\n' '------------------------------------------------------------'
"${PYTHON_BIN}" - "${OUTPUT_DIR}/npr_below_threshold_support.csv" <<'PY'
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
G02 definition:                  finite NPR <= ${NPR_THRESHOLD}
Unclassified NPR files:          excluded
D03 high-NPR reproduction:       PASS
Threshold partition:             Eligible = Above + Below
G03 input contract:              PASS
Primary G03 input:               ${OUTPUT_DIR}/npr_below_threshold_repo_month_panel.csv.gz
Support:                         ${OUTPUT_DIR}/npr_below_threshold_support.csv
QC:                              ${OUTPUT_DIR}/npr_below_threshold_qc.csv
Metadata:                        ${OUTPUT_DIR}/npr_below_threshold_metadata.csv
Log file:                        ${LOG_FILE}
============================================================
EOF
