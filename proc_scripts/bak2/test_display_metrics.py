# proc_scripts/test_display_metrics.py
import sys
from pathlib import Path
import pandas as pd

path = Path(sys.argv[1])
df = pd.read_csv(path)

if {"bugs", "vulnerabilities", "code_smells"}.issubset(df.columns):
    df["static_analysis_warnings"] = (
        df["bugs"].fillna(0)
        + df["vulnerabilities"].fillna(0)
        + df["code_smells"].fillna(0)
    )

cols = [
    "repo_name",
    "month",
    "latest_commit",
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "static_analysis_warnings",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "software_quality_maintainability_remediation_effort",
    "technical_debt",
]

cols = [c for c in cols if c in df.columns]
label_width = max(len(c) for c in cols)

for idx, row in df[cols].iterrows():
    print("=" * 90)
    print(f"Repository #{idx + 1}: {row.get('repo_name', '')}")
    print("=" * 90)

    for col in cols:
        value = row[col]

        if pd.isna(value):
            value = ""

        print(f"{col:<{label_width}} : {value}")

    print()

print("=" * 90)
print(f"Total repositories displayed: {len(df)}")
print("=" * 90)