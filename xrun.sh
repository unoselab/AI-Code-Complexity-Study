python - <<'PY'
import pandas as pd

df = pd.read_csv("data/repos.csv")

cols = [
    "repo_name",
    "repo_stars",
    "repo_size",
    "repo_primary_language",
]

cols = [c for c in cols if c in df.columns]

# Show smallest repos first
small = df.sort_values("repo_size")[cols].head(-1)

print(small.to_string(index=False))
PY