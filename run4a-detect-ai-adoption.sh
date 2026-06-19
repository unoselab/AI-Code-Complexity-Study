#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# run4a: Select top clone candidates, optionally clone them
# ============================================================
export GIT_TERMINAL_PROMPT=0
LOG_DIR="${LOG_DIR:-logs}"
DATA_DIR="${DATA_DIR:-data_baseline_backup}"
OUTPUT_DIR="${OUTPUT_DIR:-tmp_adoption_test/data}"
OUTPUT_FILE="${OUTPUT_FILE:-${OUTPUT_DIR}/top_100_clone_candidates.csv}"
ALL_ELIGIBLE_FILE="${OUTPUT_FILE%.csv}_all_eligible.csv"

CLONE_ROOT="${CLONE_ROOT:-../ai_code_complexity_study_repo_dataset}"

TOP_N="${TOP_N:-100}"
MIN_PRE_MONTHS="${MIN_PRE_MONTHS:-3}"
MIN_POST_MONTHS="${MIN_POST_MONTHS:-3}"
RANK_BY="${RANK_BY:-high_contributor}"
REQUIRE_CURSOR_EVIDENCE="${REQUIRE_CURSOR_EVIDENCE:-true}"

# Modes:
# INSPECT_ONLY=true,  INSPECT_CLONE=false  -> only create/check candidate CSV
# INSPECT_ONLY=false, INSPECT_CLONE=true   -> create/check CSV, then clone repos

INSPECT_ONLY="${INSPECT_ONLY:-true}"
INSPECT_CLONE="${INSPECT_CLONE:-false}"

# Optional: limit clone count for testing.
# Use 0 to clone all rows in OUTPUT_FILE.

MAX_CLONES="${MAX_CLONES:-0}"

# Optional extra git clone args.
# Do NOT use --depth 1 because we need full Git history for adoption-date detection.
GIT_CLONE_EXTRA_ARGS="${GIT_CLONE_EXTRA_ARGS:-}"

is_true() {
case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
true|1|yes|y) return 0 ;;
*) return 1 ;;
esac
}

print_config() {
echo "============================================================"
echo "run4a: select top clone candidates for AI/Cursor adoption validation"
echo "Data dir:                 ${DATA_DIR}"
echo "Output dir:               ${OUTPUT_DIR}"
echo "Top candidates file:      ${OUTPUT_FILE}"
echo "All eligible file:        ${ALL_ELIGIBLE_FILE}"
echo "Clone root:               ${CLONE_ROOT}"
echo "Top N:                    ${TOP_N}"
echo "Min pre months:           ${MIN_PRE_MONTHS}"
echo "Min post months:          ${MIN_POST_MONTHS}"
echo "Rank by:                  ${RANK_BY}"
echo "Require Cursor evidence:  ${REQUIRE_CURSOR_EVIDENCE}"
echo "Inspect only:             ${INSPECT_ONLY}"
echo "Inspect clone:            ${INSPECT_CLONE}"
echo "Max clones:               ${MAX_CLONES}"
echo "============================================================"
echo
}

validate_mode() {
if is_true "${INSPECT_ONLY}" && is_true "${INSPECT_CLONE}"; then
echo "ERROR: INSPECT_ONLY and INSPECT_CLONE cannot both be true."
echo
echo "Use one of these:"
echo "  INSPECT_ONLY=true  INSPECT_CLONE=false ./run4a-detect-ai-adoption.sh"
echo "  INSPECT_ONLY=false INSPECT_CLONE=true  ./run4a-detect-ai-adoption.sh"
exit 1
fi
}

run_candidate_selection() {
mkdir -p "${OUTPUT_DIR}"

echo "** Select candidate repositories"
echo "------------------------------------------------------------"

cmd=(
python proc_scripts/find_repo_pre_post_ai_adoption.py
--data-dir "${DATA_DIR}"
--top-n "${TOP_N}"
--min-pre-months "${MIN_PRE_MONTHS}"
--min-post-months "${MIN_POST_MONTHS}"
--rank-by "${RANK_BY}"
--output "${OUTPUT_FILE}"
)

if is_true "${REQUIRE_CURSOR_EVIDENCE}"; then
cmd+=(--require-cursor-evidence)
fi

"${cmd[@]}"

echo
}

main() {
print_config
validate_mode
run_candidate_selection

if is_true "${INSPECT_CLONE}"; then
  echo "** Git-clone candidate repositories"
  echo "------------------------------------------------------------"

  python proc_scripts/clone_repos_v2.py \
    --repos-file "${OUTPUT_FILE}" \
    --repo-column repo_name \
    --clone-root "${CLONE_ROOT}" \
    --logs-dir "${LOG_DIR}" \
    --log-prefix run4a_clone_log \
    --max-repos "${MAX_CLONES}"
  
else
  echo "INSPECT_ONLY mode: candidate CSV was created, but repositories were not cloned."
  echo
  echo "To clone next, run:"
  echo "  INSPECT_ONLY=false INSPECT_CLONE=true ./run4a-detect-ai-adoption.sh"
  echo
fi

echo "run4a completed successfully."
}

main "$@"
