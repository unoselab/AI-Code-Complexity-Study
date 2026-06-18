import sys
from pathlib import Path
import pandas as pd

out_path = Path(sys.argv[1])
repo_names = sys.argv[2:]

src = Path("data/ts_repos_monthly.csv")

if not src.exists():
    raise SystemExit(f"Missing input file: {src}")

df = pd.read_csv(src)

required = ["repo_name", "month", "latest_commit"]
missing = [c for c in required if c not in df.columns]
if missing:
    raise SystemExit(f"Missing columns in {src}: {missing}")

rows = []

for repo_name in repo_names:
    one = df[df["repo_name"] == repo_name].copy()

    if one.empty:
        raise SystemExit(f"Repo not found in {src}: {repo_name}")

    one = one[
        one["latest_commit"].notna()
        & (one["latest_commit"].astype(str).str.len() > 0)
    ].copy()

    if one.empty:
        raise SystemExit(f"No valid latest_commit for repo: {repo_name}")

    # Use the latest available month for each repo.
    one = one.sort_values("month").tail(1)
    rows.append(one)

batch = pd.concat(rows, ignore_index=True)
out_path.parent.mkdir(parents=True, exist_ok=True)
batch.to_csv(out_path, index=False)

print("Wrote:", out_path)
print(batch[["repo_name", "month", "latest_commit"]].to_string(index=False))