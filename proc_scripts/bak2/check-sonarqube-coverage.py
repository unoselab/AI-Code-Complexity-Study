import pandas as pd
from pathlib import Path

files = {
    "treatment": "tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly_scanned.csv",
    "control": "tmp_adoption_test/data/python_did_test/sonarqube_full_control/data/ts_repos_monthly_scanned.csv",
}

metric_cols = [
    "ncloc",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "comment_lines_density",
    "cognitive_complexity",
    "technical_debt",
]

for name, path in files.items():
    print("=" * 72)
    print(name)
    print("=" * 72)

    p = Path(path)
    if not p.exists():
        print("MISSING FILE:", path)
        continue

    df = pd.read_csv(p)

    print("file:", path)
    print("rows:", len(df))
    print("repos:", df["repo_name"].nunique())
    print("months:", df["month"].min(), "to", df["month"].max())

    print("\nmetric coverage:")
    for col in metric_cols:
        if col in df.columns:
            print(f"{col}: {df[col].notna().sum()} / {len(df)}")
        else:
            print(f"{col}: MISSING")

    if all(c in df.columns for c in metric_cols):
        missing = df[df[metric_cols].isna().any(axis=1)]
        print("\nmissing rows:", len(missing))
        if len(missing):
            print(missing[["repo_name", "month", "latest_commit"]].head(100).to_string(index=False))

    print()
