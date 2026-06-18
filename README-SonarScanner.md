## SonarQube Post-Setup Validation and Small-Batch Pipeline Testing

After completing the SonarQube setup, we validated that the local SonarQube server and scanner were functioning correctly and then moved from isolated scanner tests to a reusable small-batch pipeline test.

First, we confirmed that SonarQube was reachable at `http://localhost:9000`, that the authentication token worked, and that the scanner path from `.env` was correctly detected. We also confirmed that the SonarQube Docker container was stable, with memory usage remaining low relative to the available system memory.

Next, we created a reusable helper script:

```text
proc_scripts/create_tmp_repo_timeseries_input.py
```

This script generates a temporary time-series input file for SonarQube testing without relying on the original paper’s `data/ts_repos_monthly.csv`. The script reads the current `HEAD` commit from already cloned repositories and writes a minimal CSV containing:

```text
repo_name, month, latest_commit
```

This temporary file is used by the patched SonarQube runner:

```text
proc_scripts/run_sonarqube_v2.py
```

We then updated the small-batch smoke test so that the workflow became:

```text
1. Clone missing repositories
2. Create temporary time-series input from cloned repository HEAD commits
3. Run the SonarQube pipeline
4. Display resulting metrics
```

During testing, we found that the temporary input used `2026-06` as the test month, while the SonarQube runner was originally hardcoded to process only the original study window, from `2024-01` to `2025-08`. Because of this mismatch, the runner initially skipped the `2026-06` rows and produced missing metric values.

To fix this, we modified `run_sonarqube_v2.py` so that it infers the processing window directly from the input CSV:

```text
START_DATE = min(input month)
END_DATE   = max(input month)
```

This allowed the runner to process arbitrary temporary test months such as `2026-06`.
the dynamic date range patch worked correctly. The runner logged:

```text
Using input-derived date range: 2026-06 to 2026-06
```

We also observed a SonarQube timing issue: immediately after a scan completed, the analysis version was sometimes not yet visible through the SonarQube analysis API. We confirmed that this was due to SonarQube server-side Compute Engine processing, not a scanner failure. After the analysis became available, the same pipeline successfully retrieved metrics.

The final small-batch smoke test succeeded for three repositories:

```text
TheSethRose/Agent-Chat
utensils/mcp-nixos
nextml-code/pytorch-datastream
```

The pipeline successfully collected SonarQube metrics including:

```text
ncloc
bugs
vulnerabilities
code_smells
static_analysis_warnings
duplicated_lines_density
comment_lines_density
cognitive_complexity
technical_debt
```

The final result confirmed that:

```text
1. Repository cloning works.
2. Temporary time-series input generation works.
3. Dynamic input-derived date range handling works.
4. SonarQube scanner execution works.
5. SonarQube metric retrieval works.
6. Metrics are correctly written back to the temporary CSV.
```

We also confirmed an important methodological distinction. The current smoke test analyzes one month per repository using the current repository `HEAD` commit. This is useful for infrastructure validation, but it is not equivalent to the original paper pipeline.

The original paper analyzed multiple months per repository. For each repository-month, the pipeline should use the commit corresponding to that historical month.

Therefore, the next planned step is:

```text
run3a:
  multi-month smoke test with actual multiple-month history
  instead of repeating current HEAD across multiple months
  tests whether run_sonarqube_v2.py handles multiple periods per repo
```

The goal of `run3a` is to move closer to the original paper’s design by testing multiple historical months per repository with actual month-specific commits.
