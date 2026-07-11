#!/usr/bin/env bash
set -euo pipefail

echo
echo "--- Step 1 Create full treatment/control scan input ---"
echo
mkdir -p tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data
mkdir -p tmp_adoption_test/data/python_did_test/sonarqube_full_control/data

python - <<'PY'
import pandas as pd
from pathlib import Path

src = "tmp_adoption_test/data/python_did_test/sonarqube_input_check/sonarqube_scan_input_balanced_history_lookup.csv"

treat_out = "tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly.csv"
ctrl_out = "tmp_adoption_test/data/python_did_test/sonarqube_full_control/data/ts_repos_monthly.csv"

df = pd.read_csv(src)

required = {"repo_name", "time", "dataset_source", "latest_commit"}
missing = required - set(df.columns)
if missing:
    raise SystemExit(f"Missing required columns: {missing}")

df = df[df["latest_commit"].notna()].copy()

def make_scan_input(dataset_source, out_path):
    x = df[df["dataset_source"] == dataset_source].copy()
    x = x.rename(columns={"time": "month"})
    x = x[["repo_name", "month", "latest_commit"]]
    x = x.drop_duplicates()
    x = x.sort_values(["repo_name", "month"])
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    x.to_csv(out_path, index=False)
    print()
    print(dataset_source)
    print("saved:", out_path)
    print("rows:", len(x))
    print("repos:", x["repo_name"].nunique())
    print("months:", x["month"].min(), "to", x["month"].max())
    print("missing latest_commit:", x["latest_commit"].isna().sum())

make_scan_input("treatment", treat_out)
make_scan_input("control", ctrl_out)
PY

echo
echo "--- Step 2 Check duplicated commits before full SonarQube scan ---"
echo
python - <<'PY'
import pandas as pd

files = {
    "treatment": "tmp_adoption_test/data/python_did_test/sonarqube_full_treatment/data/ts_repos_monthly.csv",
    "control": "tmp_adoption_test/data/python_did_test/sonarqube_full_control/data/ts_repos_monthly.csv",
}

for name, path in files.items():
    df = pd.read_csv(path)
    print()
    print(name)
    print("rows:", len(df))
    print("repos:", df["repo_name"].nunique())
    print("unique repo-commit pairs:", df[["repo_name", "latest_commit"]].drop_duplicates().shape[0])
    print("same-commit repeated rows:", len(df) - df[["repo_name", "latest_commit"]].drop_duplicates().shape[0])
PY
