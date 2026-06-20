# --- Step 1
# python proc_scripts/find_control_groups_v2.py \
#   --no-language-matching \
#   --max-control-repos 5000 \
#   --random-state 42

# --- Step 2
# python proc_scripts/find_control_groups_v2.py \
#   --language-matching \
#   --max-control-repos 10000 \
#   --random-state 42

# --- Step 3
RUN_TS="$(date +%Y%m%d-%H%M)"
OUTPUT_FILE="tmp_adoption_test/data/control_repos_to_clone_v2.txt"
CLONE_ROOT="/home/user1-system12/project-workspace/ai_code_complexity_control_repo_dataset"
LOG_DIR="logs"
MAX_CLONES=0

python proc_scripts/clone_repos_v2.py \
  --repos-file "${OUTPUT_FILE}" \
  --repo-column repo_name \
  --clone-root "${CLONE_ROOT}" \
  --logs-dir "${LOG_DIR}" \
  --log-prefix run5b_control_clone_log \
  --timestamp "${RUN_TS}" \
  --max-repos "${MAX_CLONES}" \
  --existing-action skip

  