## Progress Report: Figure 7 JavaScript/TypeScript Treatment Pipeline

### Objective

The current goal is to reproduce the **Figure 7-style JavaScript/TypeScript robustness setting** from the Cursor adoption paper. This setting should use a combined JavaScript/TypeScript treatment sample, not a TypeScript-only sample.

The main treatment candidate pool is:

```text
tmp_jsts_test/data/original_paper_treatment_jsts_repos.csv
```

This file contains:

```text
441 JavaScript/TypeScript treatment repositories
- TypeScript: 379
- JavaScript: 62
```

The strict balanced-window subset is:

```text
tmp_jsts_test/data/original_paper_treatment_jsts_repos_bw6.csv
```

This contains:

```text
92 repositories with balanced_window >= 6
```

The main Figure 7-style analysis should use the **441 unbalanced JS/TS treatment repositories**. The 92-repository balanced-window subset should be used later only as a robustness or sensitivity check.

### Completed Steps

The following scripts have been renamed and reorganized for the Figure 7 JS/TS pipeline:

```text
run7a-count-repo.sh
run7b-detect-ai-adoption-repo.sh
run7c-clone-ai-adoption-repo.sh
run7d-analyze-ai-adoption-repo.sh
```

The clone wrapper `run7c-clone-ai-adoption-repo.sh` should now be updated to produce a timestamped log under:

```text
logs/
```

The updated wrapper will call `run7b-detect-ai-adoption-repo.sh` in clone mode and preserve a timestamped backup of the clone-status CSV.

### Smoke Clone Result

A smoke clone test was run with:

```bash
MAX_CLONES=10 bash run7c-clone-ai-adoption-repo.sh
```

The result was:

```text
Candidate rows: 441
Clone log rows: 10
Processed repositories: 10
Usable repositories: 8
Failed repositories: 2
Not attempted yet: 431
```

The 431 missing rows are expected because `MAX_CLONES=10` was used. They are not failures.

The two failed repositories were:

```text
0xAquaWolf/portfolio
0xsend/sendapp
```

Both failed with `Repository not found`, so this appears to be a GitHub availability issue rather than a script error.

### Smoke Analysis Result

A smoke repository-history analysis was run with:

```bash
MAX_REPOS=8 NUM_PROCESSES=1 bash run7d-analyze-ai-adoption-repo.sh
```

The repository history analysis succeeded. It produced the following files:

```text
tmp_jsts_test/data/jsts_did_test/ts_repos_monthly.csv
tmp_jsts_test/data/jsts_did_test/ts_contributors_monthly.csv
tmp_jsts_test/data/jsts_did_test/cursor_commits.csv
tmp_jsts_test/data/jsts_did_test/ai_adoption_dates.csv
```

The key success signal was:

```text
Repos with Cursor adoption evidence: 8
```

This means that the pipeline successfully found Cursor adoption evidence in all 8 usable cloned repositories from the smoke test.

### Current Known Issue

The `run7d` script failed only at the adoption-month validation step:

```text
Missing candidate columns: ['event_month']
```

This is not a repository analysis failure. The cause is that the usable clone list:

```text
tmp_jsts_test/data/jsts_treatment_clone_usable_repos.csv
```

was generated from the clone-status file, which does not currently include the `event_month` column.

The fix should be applied after the full clone finishes. At that point, we should attach `event_month` metadata from the original panel or event-window summary to the usable cloned repository list, then rerun the validation step.

### Immediate Next Step

The next step is to start the full treatment clone process in `tmux`.

Recommended tmux session:

```bash
tmux new -s aicomplexity-did
```

Inside tmux:

```bash
cd ~/Documents/repro-test01/ai_code_complexity_study
conda activate aicomplexity
MAX_CLONES=0 bash run7c-clone-ai-adoption-repo.sh
```

Detach from tmux:

```text
Ctrl-b d
```

Reattach later:

```bash
tmux attach -t aicomplexity-did
```

Monitor the latest clone log from another terminal:

```bash
cd ~/Documents/repro-test01/ai_code_complexity_study
LATEST_LOG=$(ls -t logs/run7c_clone_ai_adoption_repo_*.log | head -1)
tail -f "${LATEST_LOG}"
```

### After Full Clone Finishes

After the full clone completes, we should inspect:

```text
tmp_jsts_test/data/jsts_treatment_clone_status.csv
logs/run7c_clone_ai_adoption_repo_<timestamp>.log
logs/run7b_clone_log_<timestamp>.csv
```

The next checks should be:

```text
1. Number of usable JS/TS treatment repositories
2. Number of failed repositories
3. TypeScript vs JavaScript distribution among usable repositories
4. Whether the usable count is close to the paper's Figure 7 JS/TS treatment count
5. Whether failed repositories are mostly deleted/private/nonexistent repositories
```

### Planned Next Stage

After the full treatment clone is complete:

```text
1. Create the final usable treatment repository file.
2. Add event_month metadata to the usable repository file.
3. Rerun run7d on all usable treatment repositories.
4. Validate git-detected adoption_month against event_month.
5. Move to JS/TS control matching and control clone.
```

So the immediate action is:

```bash
MAX_CLONES=0 bash run7c-clone-ai-adoption-repo.sh
```
