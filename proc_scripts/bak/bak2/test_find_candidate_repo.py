import pandas as pd

repos = pd.read_csv("data/repos.csv")
ts = pd.read_csv("data/ts_repos_monthly.csv")

valid_ts = ts[
    ts["latest_commit"].notna()
    & (ts["latest_commit"].astype(str).str.len() > 0)
]

candidates = repos[repos["repo_name"].isin(valid_ts["repo_name"].unique())].copy()

cols = ["repo_name", "repo_stars", "repo_size", "repo_primary_language"]
cols = [c for c in cols if c in candidates.columns]

print(
    candidates[
        (candidates["repo_size"] >= 500)
        & (candidates["repo_size"] <= 50000000)
    ].sort_values("repo_size")[cols].head(80).to_string(index=False)
)