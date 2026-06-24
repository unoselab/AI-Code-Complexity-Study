#!/usr/bin/env bash
set -euo pipefail

# This shell script wrapper should be simple since it calls another wrapper.
# For simplicity, use direct, hard-coded constants rather than variables,
#               minimize validation checkers which are inside callee wrapper.

# --- 1. Smoke test ---
# REPOS_FILE=tmp_jsts_test/data/jsts_treatment_clone_usable_repos_with_event_valid.csv \
# USABLE_REPOS_FILE=tmp_jsts_test/data/jsts_treatment_clone_usable_repos_with_event_valid.csv \
# SKIP_USABLE_REPO_CREATION=true \
# MAX_REPOS=5 \
# NUM_PROCESSES=1 \
# bash run7d1-analyze-ai-adoption-repo.sh

# --- 2. Actual run ---
REPOS_FILE=tmp_jsts_test/data/jsts_treatment_clone_usable_repos_with_event_valid.csv \
USABLE_REPOS_FILE=tmp_jsts_test/data/jsts_treatment_clone_usable_repos_with_event_valid.csv \
SKIP_USABLE_REPO_CREATION=true \
MAX_REPOS=0 \
NUM_PROCESSES=2 \
bash run7d1-analyze-ai-adoption-repo.sh
