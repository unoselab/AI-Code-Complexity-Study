#!/usr/bin/env bash
set -euo pipefail

# Review all unique unresolved D01a blobs at source level.
#
# Inputs:
#   repo_x02/run-x-d01a/model_c_token_py_unresolved_after_d01a.csv
#   repo_x02/run-x-d01a/model_c_token_py_blob_resolution_review.csv
#   repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv
#
# Outputs:
#   Console diagnostics for each unique unresolved blob.
#   Temporary source files:
#     /tmp/d01a-unresolved-case-XX.py
#
# Usage:
#   chmod +x xrun.sh
#   ./xrun.sh
#
# Optional log capture:
#   ./xrun.sh |& tee d01a-16-unresolved-source-review.log

UNRESOLVED_CSV="repo_x02/run-x-d01a/model_c_token_py_unresolved_after_d01a.csv"
REVIEW_CSV="repo_x02/run-x-d01a/model_c_token_py_blob_resolution_review.csv"
MANIFEST_CSV="repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv"

MAIN_PYTHON="${MAIN_PYTHON:-python}"
PYTHON312="${PYTHON312:-/home/user1-system12/miniconda3/envs/agcparse312/bin/python}"
PYTHON313="${PYTHON313:-/home/user1-system12/miniconda3/envs/agcparse313/bin/python}"

for required_file in "${UNRESOLVED_CSV}" "${REVIEW_CSV}" "${MANIFEST_CSV}"; do
    if [[ ! -f "${required_file}" ]]; then
        echo "ERROR: Required input file not found: ${required_file}" >&2
        exit 1
    fi
done

if [[ ! -x "${PYTHON312}" ]]; then
    echo "ERROR: Python 3.12 interpreter not executable: ${PYTHON312}" >&2
    exit 1
fi

CASE_LIST_FILE="$(mktemp /tmp/d01a-unresolved-cases.XXXXXX.tsv)"
trap 'rm -f "${CASE_LIST_FILE}"' EXIT

# Build one row per unique unresolved blob in unresolved-CSV order.
# The Python code also extracts the parser error line from the review CSV.
UNRESOLVED_CSV="${UNRESOLVED_CSV}" \
REVIEW_CSV="${REVIEW_CSV}" \
MANIFEST_CSV="${MANIFEST_CSV}" \
"${MAIN_PYTHON}" - <<'PY' > "${CASE_LIST_FILE}"
import os
import re
import sys

import pandas as pd

unresolved_path = os.environ["UNRESOLVED_CSV"]
review_path = os.environ["REVIEW_CSV"]
manifest_path = os.environ["MANIFEST_CSV"]

unresolved = pd.read_csv(
    unresolved_path,
    dtype=str,
    keep_default_na=False,
)
review = pd.read_csv(
    review_path,
    dtype=str,
    keep_default_na=False,
)
manifest = pd.read_csv(
    manifest_path,
    dtype=str,
    keep_default_na=False,
)

required_unresolved = {
    "repo_name",
    "commit_sha",
    "path",
    "blob_oid",
}
required_review = {
    "blob_oid",
    "python312_ast_error_message",
}
required_manifest = {
    "repo_name",
    "latest_commit_effective",
    "clone_path",
}

for label, frame, required in (
    ("unresolved", unresolved, required_unresolved),
    ("review", review, required_review),
    ("manifest", manifest, required_manifest),
):
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SystemExit(
            f"{label} CSV is missing required columns: {missing}"
        )

unique_cases = unresolved.drop_duplicates(
    subset=["blob_oid"],
    keep="first",
).reset_index(drop=True)

review_by_blob = review.drop_duplicates(
    subset=["blob_oid"],
    keep="first",
).set_index("blob_oid")

rows = []

for index, row in unique_cases.iterrows():
    blob_oid = row["blob_oid"]
    repo_name = row["repo_name"]
    commit_sha = row["commit_sha"]
    file_path = row["path"]

    if blob_oid not in review_by_blob.index:
        raise SystemExit(
            f"Blob is missing from review CSV: {blob_oid}"
        )

    review_row = review_by_blob.loc[blob_oid]
    error_message = review_row["python312_ast_error_message"]

    line_match = re.search(r"\bline\s+(\d+)\b", error_message)
    if not line_match:
        raise SystemExit(
            "Could not extract an error line from "
            f"blob {blob_oid}: {error_message!r}"
        )
    error_line = int(line_match.group(1))

    exact_manifest = manifest[
        (manifest["repo_name"] == repo_name)
        & (manifest["latest_commit_effective"] == commit_sha)
    ]

    manifest_match = exact_manifest
    if manifest_match.empty:
        manifest_match = manifest[
            manifest["repo_name"] == repo_name
        ]

    clone_paths = (
        manifest_match["clone_path"]
        .loc[lambda values: values != ""]
        .drop_duplicates()
        .tolist()
    )

    if len(clone_paths) != 1:
        raise SystemExit(
            "Expected exactly one clone path for "
            f"{repo_name} at {commit_sha}; found {clone_paths}"
        )

    fields = [
        str(index + 1),
        str(len(unique_cases)),
        repo_name,
        commit_sha,
        file_path,
        blob_oid,
        str(error_line),
        clone_paths[0],
        error_message,
    ]

    if any("\t" in field or "\n" in field for field in fields):
        raise SystemExit(
            f"Unexpected tab or newline in case data for blob {blob_oid}"
        )

    rows.append(fields)

for fields in rows:
    print("\t".join(fields), file=sys.stdout)
PY

TOTAL_CASES="$(wc -l < "${CASE_LIST_FILE}")"

echo "D01a unresolved source-level review"
echo "==================================="
echo "Unique unresolved blobs: ${TOTAL_CASES}"
echo "Python 3.12: ${PYTHON312}"
if [[ -x "${PYTHON313}" ]]; then
    echo "Python 3.13: ${PYTHON313}"
else
    echo "Python 3.13: unavailable (${PYTHON313})"
fi
echo

while IFS=$'\t' read -r \
    CASE_NUMBER \
    CASE_TOTAL \
    REPO_NAME \
    COMMIT_SHA \
    FILE_PATH \
    BLOB_OID \
    ERROR_LINE \
    CLONE_PATH \
    ERROR_MESSAGE
do
    printf -v CASE_LABEL '%02d' "${CASE_NUMBER}"
    TMP_FILE="/tmp/d01a-unresolved-case-${CASE_LABEL}.py"

    echo "======================================================================"
    printf 'Case %02d / %02d\n' "${CASE_NUMBER}" "${CASE_TOTAL}"
    echo "Repository:       ${REPO_NAME}"
    echo "Commit:           ${COMMIT_SHA}"
    echo "Path:             ${FILE_PATH}"
    echo "Blob:             ${BLOB_OID}"
    echo "Reported error:   ${ERROR_MESSAGE}"
    echo "Reported line:    ${ERROR_LINE}"
    echo "Clone:            ${CLONE_PATH}"
    echo "Temporary source: ${TMP_FILE}"
    echo "======================================================================"
    echo

    if [[ ! -d "${CLONE_PATH}/.git" ]]; then
        echo "ERROR: Clone is not a Git repository: ${CLONE_PATH}" >&2
        exit 1
    fi

    if ! git -C "${CLONE_PATH}" cat-file -e "${BLOB_OID}^{blob}"; then
        echo "ERROR: Blob is unavailable in clone: ${BLOB_OID}" >&2
        exit 1
    fi

    git -C "${CLONE_PATH}" cat-file blob "${BLOB_OID}" > "${TMP_FILE}"

    echo "Blob verification"
    echo "-----------------"
    echo "Git object type: $(git -C "${CLONE_PATH}" cat-file -t "${BLOB_OID}")"
    echo "Git object size: $(git -C "${CLONE_PATH}" cat-file -s "${BLOB_OID}")"
    sha1sum "${TMP_FILE}"
    echo

    START_LINE=$((ERROR_LINE > 15 ? ERROR_LINE - 15 : 1))
    END_LINE=$((ERROR_LINE + 15))

    echo "Source around parser error"
    echo "--------------------------"
    nl -ba "${TMP_FILE}" |
        sed -n "${START_LINE},${END_LINE}p"
    echo

    echo "Named function declarations around the error"
    echo "--------------------------------------------"
    grep -nE \
        '^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+' \
        "${TMP_FILE}" |
        awk -F: -v line="${ERROR_LINE}" \
            '$1 >= line - 100 && $1 <= line + 100' || true
    echo

    echo "Python 3.12 parse result"
    echo "------------------------"
    if "${PYTHON312}" -m py_compile "${TMP_FILE}"; then
        echo "Python 3.12 parse: PASS"
    else
        echo "Python 3.12 parse: FAIL"
    fi
    echo

    echo "Python 3.13 parse result"
    echo "------------------------"
    if [[ -x "${PYTHON313}" ]]; then
        if "${PYTHON313}" -m py_compile "${TMP_FILE}"; then
            echo "Python 3.13 parse: PASS"
        else
            echo "Python 3.13 parse: FAIL"
        fi
    else
        echo "Python 3.13 parse: SKIPPED"
        echo "Interpreter not found: ${PYTHON313}"
    fi
    echo

done < "${CASE_LIST_FILE}"

echo "======================================================================"
echo "Review completed for ${TOTAL_CASES} unique unresolved blobs."
echo "Temporary source files remain under /tmp/d01a-unresolved-case-XX.py."
echo "======================================================================"
