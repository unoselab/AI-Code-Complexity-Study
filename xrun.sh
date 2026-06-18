python - <<'PY'
import pandas as pd

# Load repository metadata and monthly time-series data
repos = pd.read_csv("data/repos.csv")
ts = pd.read_csv("data/ts_repos_monthly.csv")

# Keep only repos that actually appear in the monthly panel
valid_ts = ts[
    ts["latest_commit"].notna()
    & (ts["latest_commit"].astype(str).str.len() > 0)
].copy()

valid_repo_names = set(valid_ts["repo_name"].unique())

candidates = repos[repos["repo_name"].isin(valid_repo_names)].copy()

cols = [
    "repo_name",
    "repo_stars",
    "repo_size",
    "repo_primary_language",
]

cols = [c for c in cols if c in candidates.columns]

# Medium-size candidates: larger than tiny test, but still safe
medium = candidates[
    (candidates["repo_size"] >= 500)
    & (candidates["repo_size"] <= 50000000)
].sort_values("repo_size")

print(medium[cols].head(80).to_string(index=False))
PY