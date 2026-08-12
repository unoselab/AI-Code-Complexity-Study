#!/usr/bin/env bash
set -euo pipefail


REVIEW_CSV="repo_x02/run-x-d01a/model_c_token_py_blob_resolution_review.csv"

BLOB_OIDS=(
    # atopile/atopile: 9 unique blobs
    "14568e4e6d7958ae0d7bb1c84bce10f469aa597a"
    "1b3636ab38e901b74604da842eb54a6a66adfb53"
    "349d655d924d4b5194c15aa6244751f1ff98ace1"
    "73613c6951ca4bb5855cbae01bb6e3551b248bf4"
    "765f77c6d84bee9d31df4a5bcd86ec3fbb611339"
    "85af8f7f0e69888d747e260e869b05d9c67d629c"
    "9e6b9c6359392c560b0ed5139c7dc4b5fa86c071"
    "9f6e89558dcd738b4b05860f9a2696c8957ccd05"
    "c8cc049329150f0743a920006a87ca13da020c1c"

    # ericyuegu/hal: 1 unique blob
    "9512baaad8dfb8bf7e2bd89be5378d2ce4c09df4"

    # getsentry/sentry: 5 unique blobs
    "2348337c2b41c2152a78dbac927601a648eabe62"
    "380bf15b62c7348223e5eeb03cf435302be79344"
    "64f3fe81c81fb9b4bf587cdab13d12ba3f2d263e"
    "9b2605e2e75a9d6fed6a645a195d4c401cda8669"
    "e4e06bb6d4177c75f0a173d04a7371f044c4f2e1"

    # yagami1997/TradeMind: 1 unique blob
    "d9b802fdd9ff8575ac2e32ec8bf619dbc5a91582"
)

for index in "${!BLOB_OIDS[@]}"; do
    case_number=$((index + 1))
    blob_oid="${BLOB_OIDS[$index]}"

    printf '\n'
    printf '======================================================================\n'
    printf 'Case %02d / %02d\n' "${case_number}" "${#BLOB_OIDS[@]}"
    printf 'Blob: %s\n' "${blob_oid}"
    printf '======================================================================\n'

    REVIEW_CSV="${REVIEW_CSV}" \
    BLOB_OID="${blob_oid}" \
    python - <<'PY'
import os

import pandas as pd

review_csv = os.environ["REVIEW_CSV"]
blob_oid = os.environ["BLOB_OID"]

df = pd.read_csv(
    review_csv,
    dtype=str,
    keep_default_na=False,
)

matched = df[df["blob_oid"].eq(blob_oid)]

if matched.empty:
    raise SystemExit(f"Blob not found in review CSV: {blob_oid}")

print(matched.T.to_string(header=False))
PY
done



