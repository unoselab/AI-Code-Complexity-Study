#!/usr/bin/env bash
set -euo pipefail

# 1) dry run only — confirm the estimate is well under 1 GiB
echo "--- 1 CONTROL DRY RUN"
echo

python gharchive/test_fetch_gharchive_control_seeded.py \
  --project-id se-project-438721 \
  --repo VRSEN/agency-swarm \
  --repo helixml/helix \
  --repo different-ai/note-companion \
  --target-month 202501 \
  --history-start-month 202401 \
  --max-gib 1

# 2) once the bytes look safe, actually run it
echo "--- 2 CONTROL ACTUAL RUN"
echo
python gharchive/test_fetch_gharchive_control_seeded.py \
  --project-id se-project-438721 \
  --repos-file tmp_adoption_test/data/ai_adopt_repo_python.csv \
  --target-month 202501 \
  --history-start-month 202401 \
  --max-gib 1 \
  --execute









# echo "--- 1 CONTROL DRY RUN"
# echo

# python gharchive/test_fetch_gharchive_control_small.py \
#   --project-id se-project-438721 \
#   --target-month 202501 \
#   --history-start-month 202407 \
#   --candidate-limit 20 \
#   --min-stars 10 \
#   --sample-mod-numerator 1 \
#   --sample-mod-denominator 100 \
#   --max-gib 1


# echo
# echo "--- 2 CONTROL ACTUAL RUN"
# echo

# python gharchive/test_fetch_gharchive_control_small.py \
#   --project-id se-project-438721 \
#   --target-month 202501 \
#   --history-start-month 202407 \
#   --candidate-limit 20 \
#   --min-stars 10 \
#   --sample-mod-numerator 1 \
#   --sample-mod-denominator 100 \
#   --max-gib 1 \
#   --execute \
#   --output tmp_gharchive_test/control_repo_candidates_small_202501.csv
