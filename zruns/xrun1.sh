python - <<'PY'
from pathlib import Path

import pandas as pd


INPUT_FILE = Path(
    "repo_python/run-py-7a/strict/specifications/range100_200/"
    "agc_commit_function_npr_event_classifications.csv"
)

BODY_COLUMN = "function_body_sha256"
KIND_COLUMN = "function_kind"
AGC_COLUMN = "npr_agc_like"
HWC_COLUMN = "npr_hwc_like"

required_columns = {
    "function_event_id",
    BODY_COLUMN,
    KIND_COLUMN,
    AGC_COLUMN,
    HWC_COLUMN,
}

events = pd.read_csv(INPUT_FILE, low_memory=False)

missing_columns = sorted(required_columns - set(events.columns))
if missing_columns:
    raise RuntimeError(
        f"Missing required columns: {missing_columns}. "
        f"Available columns: {list(events.columns)}"
    )

events[BODY_COLUMN] = (
    events[BODY_COLUMN]
    .astype("string")
    .str.strip()
    .str.lower()
)

events[KIND_COLUMN] = (
    events[KIND_COLUMN]
    .astype("string")
    .str.strip()
    .str.lower()
)

for column in [AGC_COLUMN, HWC_COLUMN]:
    events[column] = pd.to_numeric(
        events[column],
        errors="raise",
    ).astype("int8")

partition_failures = int(
    (events[AGC_COLUMN] + events[HWC_COLUMN]).ne(1).sum()
)
if partition_failures:
    raise RuntimeError(
        f"AGC/HWC event partition failures: {partition_failures}"
    )

# A regular function is a synchronous function defined at module scope.
regular_events = events.loc[
    events[KIND_COLUMN].eq("module_function")
].copy()

print("=" * 72)
print("A. Regular module-level synchronous function events")
print("=" * 72)
print(f"Total event rows: {len(regular_events)}")
print(f"AGC-like event rows: {int(regular_events[AGC_COLUMN].sum())}")
print(f"HWC-like event rows: {int(regular_events[HWC_COLUMN].sum())}")
print(
    "Partition check:",
    int(regular_events[AGC_COLUMN].sum() + regular_events[HWC_COLUMN].sum()),
)

# Verify that every body hash has one stable AGC/HWC classification.
body_classification = (
    events.groupby(BODY_COLUMN, as_index=False)
    .agg(
        agc_min=(AGC_COLUMN, "min"),
        agc_max=(AGC_COLUMN, "max"),
        hwc_min=(HWC_COLUMN, "min"),
        hwc_max=(HWC_COLUMN, "max"),
    )
)

classification_conflicts = int(
    (
        body_classification["agc_min"].ne(
            body_classification["agc_max"]
        )
        | body_classification["hwc_min"].ne(
            body_classification["hwc_max"]
        )
    ).sum()
)

if classification_conflicts:
    raise RuntimeError(
        f"Body-level classification conflicts: {classification_conflicts}"
    )

body_classification = (
    body_classification
    .rename(
        columns={
            "agc_min": AGC_COLUMN,
            "hwc_min": HWC_COLUMN,
        }
    )
    [[BODY_COLUMN, AGC_COLUMN, HWC_COLUMN]]
    .set_index(BODY_COLUMN)
)

# Count bodies referenced by at least one regular module function event.
regular_hashes = set(
    regular_events[BODY_COLUMN].dropna().astype(str)
)

regular_bodies = body_classification.loc[
    body_classification.index.isin(regular_hashes)
]

print()
print("=" * 72)
print("B. Unique bodies referenced by regular module functions")
print("=" * 72)
print(f"Unique bodies: {len(regular_bodies)}")
print(f"AGC-like unique bodies: {int(regular_bodies[AGC_COLUMN].sum())}")
print(f"HWC-like unique bodies: {int(regular_bodies[HWC_COLUMN].sum())}")
print(
    "Partition check:",
    int(
        regular_bodies[AGC_COLUMN].sum()
        + regular_bodies[HWC_COLUMN].sum()
    ),
)

# Identify the set of function kinds associated with every body hash.
body_kind_sets = (
    events.groupby(BODY_COLUMN)[KIND_COLUMN]
    .agg(lambda values: tuple(sorted(set(values.dropna()))))
)

exclusive_regular_hashes = set(
    body_kind_sets.loc[
        body_kind_sets.map(
            lambda kinds: kinds == ("module_function",)
        )
    ].index
)

exclusive_regular_bodies = body_classification.loc[
    body_classification.index.isin(exclusive_regular_hashes)
]

cross_kind_regular_hashes = regular_hashes - exclusive_regular_hashes

print()
print("=" * 72)
print("C. Bodies used exclusively as regular module functions")
print("=" * 72)
print(f"Exclusive unique bodies: {len(exclusive_regular_bodies)}")
print(
    "AGC-like exclusive unique bodies:",
    int(exclusive_regular_bodies[AGC_COLUMN].sum()),
)
print(
    "HWC-like exclusive unique bodies:",
    int(exclusive_regular_bodies[HWC_COLUMN].sum()),
)
print(
    "Cross-kind bodies also observed as another function kind:",
    len(cross_kind_regular_hashes),
)

print()
print("=" * 72)
print("D. All function kinds in range100_200")
print("=" * 72)

kind_summary = (
    events.groupby(KIND_COLUMN, dropna=False)
    .agg(
        event_rows=("function_event_id", "size"),
        unique_bodies=(BODY_COLUMN, "nunique"),
        agc_event_rows=(AGC_COLUMN, "sum"),
        hwc_event_rows=(HWC_COLUMN, "sum"),
    )
    .reset_index()
    .sort_values(KIND_COLUMN)
)

print(kind_summary.to_string(index=False))

print()
print("Note: unique_bodies in section D may overlap across function kinds.")
PY
