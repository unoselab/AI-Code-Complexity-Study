TOP_N=10000 \
MIN_PRE_MONTHS=6 \
MIN_POST_MONTHS=6 \
REQUIRE_CURSOR_EVIDENCE=true \
INSPECT_ONLY=true \
INSPECT_CLONE=false \
OUTPUT_FILE=tmp_adoption_test/data/top_10000_clone_candidates_typescript_pool.csv \
./run4a-detect-ai-adoption.sh

CLONE_LOG="$(ls -t logs/run4a_clone_log_*.csv | head -1)"

python proc_scripts/check_python_repo_clone.py \
  --candidates-file tmp_adoption_test/data/top_10000_clone_candidates_typescript_pool.csv \
  --clone-log "${CLONE_LOG}" \
  --output tmp_adoption_test/data/ai_adopt_repo_typescript.csv \
  --language TypeScript

python - <<'PY'
import pandas as pd

path = "tmp_adoption_test/data/ai_adopt_repo_typescript.csv"
df = pd.read_csv(path)

print("rows:", len(df))
print("repos:", df["repo_name"].nunique())
print()
print(df["repo_primary_language"].value_counts(dropna=False).head(20))
print()
print(df[["repo_name", "event_month", "repo_primary_language"]].head(20).to_string(index=False))
PY


