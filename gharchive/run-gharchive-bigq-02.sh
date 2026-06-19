echo "--- 1 DRY RUN"
echo
python gharchive/test_fetch_gharchive_small.py \
  --project-id se-project-438721 \
  --repo VRSEN/agency-swarm \
  --repo helixml/helix \
  --repo different-ai/note-companion \
  --start-date 2025-01-01 \
  --end-date 2025-01-01

echo "--- 2 ACTUAL RUN"
echo
python gharchive/test_fetch_gharchive_small.py \
  --project-id se-project-438721 \
  --repo VRSEN/agency-swarm \
  --repo helixml/helix \
  --repo different-ai/note-companion \
  --start-date 2025-01-01 \
  --end-date 2025-01-01 \
  --max-gib 1 \
  --execute \
  --output tmp_gharchive_test/repo_events_small_20250101.csv



