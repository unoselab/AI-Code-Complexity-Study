#!/usr/bin/env bash
set -euo pipefail

python proc_scripts/find_repo_pre_post_ai_adoption.py \
  --data-dir data_baseline_backup \
  --top-n 100 \
  --min-pre-months 1 \
  --min-post-months 1 \
  --output tmp_adoption_test/data/top_100_clone_candidates.csv


# mkdir -p tmp_adoption_test/data

# cat > tmp_adoption_test/data/repos.csv <<'REPOS'
# repo_name
# TheSethRose/Agent-Chat
# utensils/mcp-nixos
# nextml-code/pytorch-datastream
# REPOS

# python proc_scripts/analyze_repos_v2.py \
#   --repos-file tmp_adoption_test/data/repos.csv \
#   --clone-dir ../CursorRepos \
#   --output-dir tmp_adoption_test/data \
#   --aggregation month \
#   --num-processes 1
