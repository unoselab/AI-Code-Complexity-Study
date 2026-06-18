import sys
from pathlib import Path
import pandas as pd

repo_name = sys.argv[1]
aggregation = sys.argv[2]
time_period = sys.argv[3]

time_key = aggregation
src = Path(f"data/ts_repos_{aggregation}ly.csv")
dst = Path("tmp_sonar_one_repo/data") / f"ts_repos_{aggregation}ly.csv"
dst.parent.mkdir(parents=True, exist_ok=True)

if not src.exists():
    raise SystemExit(f"Missing input file: {src}")

df = pd.read_csv(src)

if "repo_name" not in df.columns:
    raise SystemExit(f"Missing repo_name column in {src}")

if time_key not in df.columns:
    raise SystemExit(f"Missing {time_key} column in {src}")

if "latest_commit" not in df.columns:
    raise SystemExit(f"Missing latest_commit column in {src}")

one = df[df["repo_name"] == repo_name].copy()

if one.empty:
    raise SystemExit(f"Repo not found in {src}: {repo_name}")

one = one[
    one["latest_commit"].notna()
    & (one["latest_commit"].astype(str).str.len() > 0)
].copy()

if one.empty:
    raise SystemExit(f"No valid latest_commit for repo: {repo_name}")

if time_period:
    one = one[one[time_key].astype(str) == time_period].copy()
    if one.empty:
        raise SystemExit(f"No row found for {repo_name} at {time_key}={time_period}")
else:
    one = one.sort_values(time_key).tail(1)

one.to_csv(dst, index=False)

print("Wrote:", dst)
print(one[["repo_name", time_key, "latest_commit"]].to_string(index=False))
