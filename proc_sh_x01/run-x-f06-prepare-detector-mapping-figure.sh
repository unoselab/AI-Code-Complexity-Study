#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run-x-f06 v2: prepare NPR-vs-ML detector-mapping figure inputs
# ============================================================
#
# Purpose
# -------
# Prepare CSV inputs for a Sankey-style figure that maps Python files selected
# by the two frozen AGC detectors. The primary flow unit is a repo-month
# historical Python file occurrence, matching the longitudinal run-x-e panels.
#
# Figure universe
# ---------------
# A file occurrence is included when either detector selects it:
#   NPR: finite file_npr_fun_space_by_token_weighted > 1.571637
#   ML : scored file_ml_agc_share_space_by_token_weighted > 0.50
#
# The overall Sankey contains three flows:
#   1. NPR detected     -> ML detected      (Both / intersection)
#   2. NPR detected     -> ML not detected  (NPR-only)
#   3. NPR not detected -> ML detected      (ML-only)
#
# Files selected by neither detector are audited but intentionally excluded
# from the Sankey universe so that the large background class does not obscure
# the detector-overlap relationship.
#
# Inputs
# ------
# D02: canonical repo-month/file SonarQube burden table + NPR file metric.
# A04: frozen ML file score table.
# B06: authoritative repo-month panel used for repo/month metadata.
# D03: frozen NPR primary repo-month panel used only for exact reproduction QC.
# D05: frozen ML primary repo-month panel used only for exact reproduction QC.
#
# Outputs
# -------
# agc_detector_mapping_file_occurrences.csv.gz
#   Row-level union-selected file occurrences with detector scores and mapping.
# agc_detector_mapping_sankey_edges.csv
#   Overall three-edge Sankey input. Use file_occurrences as flow width.
# agc_detector_mapping_sankey_nodes.csv
#   Left/right node totals within the union universe.
# agc_detector_mapping_repo_month_edges.csv.gz
#   Repo-month-specific mapping edges for longitudinal follow-up plots/QC.
# agc_detector_mapping_repo_month_summary.csv
#   Zero-inclusive 1,954-row detector-overlap summary by repo-month.
# agc_detector_mapping_summary.csv
#   Global NPR, ML, intersection, detector-only, and union support.
# agc_detector_mapping_*_audit.csv / *_qc.csv / *_metadata.csv
#   Reproduction, join, hard-QC, and provenance artifacts.
#
# This wrapper is standalone. It reuses the validated E04 file-level selection
# logic but does not call any previous experiment shell or Python script.
# ============================================================

RUN_PREFIX="run-x-f06"
IMPLEMENTATION_VERSION="v2"
RUN_LABEL="${RUN_PREFIX}-${IMPLEMENTATION_VERSION}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PY_SCRIPT="${PY_SCRIPT:-proc_script_x01/prepare_agc_detector_mapping_figure_inputs.py}"

D02_FILE="${D02_FILE:-repo_x01/run-x-d02/python_fun_file_quality_burden.csv.gz}"
A04_FILE="${A04_FILE:-../../ai_detector/src/app/data_did_agc_analysis/run-x-a04/python_ml_fun_file_scores.csv}"
B06_FILE="${B06_FILE:-repo_x01/run-x-b06/panels/quality_did_panel_python_sonarqube.csv}"
D03_REFERENCE_FILE="${D03_REFERENCE_FILE:-repo_x01/run-x-d03/quality_fun_npr_threshold_repo_month_panel.csv.gz}"
D05_REFERENCE_FILE="${D05_REFERENCE_FILE:-repo_x01/run-x-d05/quality_ml_fun_repo_month_panel.csv.gz}"

OUTPUT_DIR="${OUTPUT_DIR:-repo_x01/run-x-f06-detector-mapping-figure}"
LOG_DIR="${LOG_DIR:-logs}"

EXPECTED_D02_ROWS="${EXPECTED_D02_ROWS:-510297}"
EXPECTED_A04_ROWS="${EXPECTED_A04_ROWS:-494592}"
EXPECTED_B06_ROWS="${EXPECTED_B06_ROWS:-1954}"

# Frozen upstream hashes from the validated E02-E05 lineage.
EXPECTED_D02_SHA256="${EXPECTED_D02_SHA256:-443a9ce29969a60b186fdb3cc02a48410753d2a9f408ef95145ceb2a569945df}"
EXPECTED_A04_SHA256="${EXPECTED_A04_SHA256:-b04db6462e74dfd3161d1680425a0335361e86093754ee2341f5c9e0e84e6518}"
EXPECTED_B06_SHA256="${EXPECTED_B06_SHA256:-e34c56d1dda8342106a87314a9425c0ab2323ed0414c533a0f17c9c88e4f5027}"
EXPECTED_D03_SHA256="${EXPECTED_D03_SHA256:-91def6a5e5b2b611d0b4875db8d348b3d1c61a91924b30a6f63f37b5b2be20af}"
EXPECTED_D05_SHA256="${EXPECTED_D05_SHA256:-970919c66c06c9e0c0eb88d459a9fcd916728ff4483ae7a9af559702785ebbd1}"

NPR_THRESHOLD="1.571637"
ML_THRESHOLD="0.50"

PROJECT_ROOT="$(pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/${RUN_LABEL}-prepare-agc-detector-mapping-figure-${TIMESTAMP}.log"

for required_file in \
  "${PY_SCRIPT}" \
  "${D02_FILE}" \
  "${A04_FILE}" \
  "${B06_FILE}" \
  "${D03_REFERENCE_FILE}" \
  "${D05_REFERENCE_FILE}"; do
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
${RUN_LABEL}: prepare AGC detector-mapping figure inputs
Started:                         $(date)
Project root:                    ${PROJECT_ROOT}
Python:                          $(command -v "${PYTHON_BIN}") (${PYTHON_VERSION})
Implementation version:          ${IMPLEMENTATION_VERSION}
Figure type:                     Sankey-style detector mapping
Primary flow unit:               repo-month Python file occurrence
Figure universe:                 NPR selected OR ML selected
NPR rule:                        file NPR > ${NPR_THRESHOLD}
ML rule:                         weighted ML AGC share > ${ML_THRESHOLD}
Neither-neither files:           excluded from Sankey, retained in audits
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
Python script SHA256:            ${PY_SHA256}
Output directory:                ${OUTPUT_DIR}
Log file:                        ${LOG_FILE}
============================================================
EOF

printf '\n** Step 1: Prepare detector-mapping CSV inputs\n'
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
  --expected-b06-rows "${EXPECTED_B06_ROWS}"

printf '\n** Step 2: Verify outputs and hard QC\n'
printf '%s\n' '------------------------------------------------------------'
EXPECTED_OUTPUTS=(
  "${OUTPUT_DIR}/agc_detector_mapping_file_occurrences.csv.gz"
  "${OUTPUT_DIR}/agc_detector_mapping_sankey_edges.csv"
  "${OUTPUT_DIR}/agc_detector_mapping_sankey_nodes.csv"
  "${OUTPUT_DIR}/agc_detector_mapping_repo_month_edges.csv.gz"
  "${OUTPUT_DIR}/agc_detector_mapping_repo_month_summary.csv"
  "${OUTPUT_DIR}/agc_detector_mapping_summary.csv"
  "${OUTPUT_DIR}/agc_detector_mapping_reproduction_audit.csv"
  "${OUTPUT_DIR}/agc_detector_mapping_join_audit.csv"
  "${OUTPUT_DIR}/agc_detector_mapping_qc.csv"
  "${OUTPUT_DIR}/agc_detector_mapping_metadata.csv"
)
for output_file in "${EXPECTED_OUTPUTS[@]}"; do
  if [[ ! -f "${output_file}" ]]; then
    echo "ERROR: expected output missing: ${output_file}" >&2
    exit 1
  fi
  echo "OK: ${output_file}"
done

"${PYTHON_BIN}" - "${OUTPUT_DIR}/agc_detector_mapping_reproduction_audit.csv" "${OUTPUT_DIR}/agc_detector_mapping_join_audit.csv" "${OUTPUT_DIR}/agc_detector_mapping_qc.csv" <<'PY'
import csv
import sys

for path in sys.argv[1:]:
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    failed = [row for row in rows if row.get("status") == "fail"]
    if failed:
        raise SystemExit(f"Hard QC failure in {path}: {failed}")
print("Hard QC: PASS")
PY

printf '\n** Step 3: Show overall Sankey mapping inputs\n'
printf '%s\n' '------------------------------------------------------------'
"${PYTHON_BIN}" - "${OUTPUT_DIR}/agc_detector_mapping_sankey_edges.csv" "${OUTPUT_DIR}/agc_detector_mapping_summary.csv" <<'PY'
import csv
import sys

edge_path, summary_path = sys.argv[1:]
print("Overall Sankey edges (primary value = repo-month file occurrences):")
with open(edge_path, newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
        print(
            f"{row['source']} -> {row['target']}: "
            f"files={row['file_occurrences']}, unique={row['unique_historical_files']}, "
            f"issues={row['issue_stock']}, class={row['mapping_class']}"
        )
print("Global detector support:")
with open(summary_path, newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
        print(
            f"{row['selection']}: files={row['file_occurrences']}, "
            f"unique={row['unique_historical_files']}, issues={row['issue_stock']}"
        )
PY

cat <<EOF
============================================================
${RUN_LABEL}: SUCCESS
Finished:                        $(date)
Figure universe:                 NPR > ${NPR_THRESHOLD} OR ML > ${ML_THRESHOLD}
Primary flow unit:               repo-month Python file occurrence
D03 NPR reproduction:            PASS
D05 ML reproduction:            PASS
Hard QC:                         PASS
Overall Sankey edges:            ${OUTPUT_DIR}/agc_detector_mapping_sankey_edges.csv
Sankey nodes:                    ${OUTPUT_DIR}/agc_detector_mapping_sankey_nodes.csv
Repo-month edges:                ${OUTPUT_DIR}/agc_detector_mapping_repo_month_edges.csv.gz
File-level provenance:           ${OUTPUT_DIR}/agc_detector_mapping_file_occurrences.csv.gz
Repo-month summary:              ${OUTPUT_DIR}/agc_detector_mapping_repo_month_summary.csv
Log file:                        ${LOG_FILE}
============================================================
EOF
