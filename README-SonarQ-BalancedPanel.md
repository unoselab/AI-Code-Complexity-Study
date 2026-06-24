# Progress Report: SonarQube and Balanced Panel Pipeline Work

## June 21–22

### 1. Context and Goal

The current task was to extend the AI code complexity study pipeline so that the balanced Difference-in-Differences panel can be connected to historical SonarQube quality metrics.

Before this work, we had a balanced monthly event panel with 738 repo-month rows covering 13 AI-adopting treatment repositories and 38 matched control repositories. The panel included activity outcomes such as commits, lines added, lines removed, and contributors, but it did not include historical commit hashes needed for SonarQube checkout and scanning.

The main goal for today was to determine how to generate valid SonarQube scan inputs from this balanced panel and then verify that SonarQube can scan actual historical repository snapshots.

### 2. SonarQube Infrastructure Check

We first checked whether SonarQube was running correctly.

The SonarQube server was reachable at `http://localhost:9000`, and the authentication token was valid. The connection test returned HTTP 200 for both server status and authentication validation.

A tiny local project scan was also run successfully. The SonarScanner CLI completed with return code 0, uploaded the analysis report, and SonarQube returned aggregate metrics through the API.

The tiny test confirmed that:

* The SonarQube Docker server is running.
* The `SONAR_HOST`, `SONAR_TOKEN`, and `SONAR_SCANNER_PATH` environment variables are configured.
* The scanner can upload analysis reports.
* The metrics API works.
* The issues API works.

This confirmed that the infrastructure was ready for real repository testing.

### 3. Balanced Panel and Missing `latest_commit`

We inspected the balanced panel:

```text
tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv
```

The panel had:

```text
rows: 738
repos: 51
latest_commit column: not present
```

The columns included treatment/control indicators, event-time variables, activity metrics, and matching provenance, but no commit hashes.

This is expected because the panel was built for DiD analysis, not for Git checkout or SonarQube scanning.

### 4. Direct Join Test

We then checked whether `latest_commit` could be recovered by directly joining the balanced panel with the existing time-series files:

```text
tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv
tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv
```

Both files contained:

```text
repo_name
month
latest_commit
cursor
commits
lines_added
lines_removed
contributors
```

The direct join used:

```text
repo_name + month/time
```

The result was:

```text
balanced panel rows: 738
rows with latest_commit by direct join: 324
rows missing latest_commit: 414
```

This showed that direct join only recovers commit hashes for active months. It does not cover zero-commit months that were added during balanced panel construction.

This was an important finding because dropping the missing rows would reduce the panel back to an active-month-only sample, which is not appropriate for the main balanced panel analysis.

### 5. Historical Lookup Approach

To solve the missing commit problem, we reused the existing script:

```text
proc_scripts/create_tmp_repo_timeseries_history.py
```

This script finds the latest commit at or before the end of each month using Git history:

```bash
git rev-list -n 1 --before <month-end> HEAD
```

This approach is better than direct join because it reconstructs the code snapshot at the end of each month, even when there were no new commits during that month.

We generated month lists and repository lists from the balanced panel:

```text
months: 2024-01 through 2025-08
treatment repos: 13
control repos: 38
```

Then we ran historical lookup separately for treatment and control repositories, using the correct clone roots:

```text
treatment clone root:
../ai_code_complexity_study_repo_dataset

control clone root:
../ai_code_complexity_control_repo_dataset
```

The historical lookup produced many warnings for months before a repository’s first commit. These warnings were expected and were not fatal.

After merging the lookup results back into the balanced panel, the final scan input had:

```text
rows: 738
repos: 51
has_checkout_commit = 1 for all 738 rows
missing treatment rows: 0
missing control rows: 0
```

The resulting file was:

```text
tmp_adoption_test/data/python_did_test/sonarqube_input_check/sonarqube_scan_input_balanced_history_lookup.csv
```

This means every row in the balanced panel now has a valid historical commit that can be checked out and scanned.

### 6. Review of Existing SonarQube Scripts

Before writing new scripts, we searched existing code under `scripts/*.py` and `proc_scripts/*.py`.

Important reusable scripts were identified:

```text
proc_scripts/create_tmp_repo_timeseries_history.py
proc_scripts/run_sonarqube_v2.py
proc_scripts/collect_sonarqube_warnings_v2.py
```

The historical input script already contained the month-end Git lookup logic. Therefore, we decided not to create a completely new commit lookup script from scratch.

The SonarQube runner script already handled:

* reading a time-series CSV,
* checking out each historical commit,
* running SonarScanner,
* waiting for SonarQube analysis completion,
* retrieving metrics from the SonarQube API,
* writing metrics back to CSV.

However, the original `run_sonarqube_v2.py` had a limitation: it used hard-coded clone directories.

### 7. Updating `run_sonarqube_v2.py`

We updated `proc_scripts/run_sonarqube_v2.py` to accept additional CLI arguments:

```text
--input-file
--output-file
--clone-dir
--num-processes
```

After the patch, the help output confirmed that these arguments were available.

This was an important improvement because our actual clone roots are:

```text
../ai_code_complexity_study_repo_dataset
../ai_code_complexity_control_repo_dataset
```

not the older smoke-test paths:

```text
../CursorRepos
../ControlRepos
```

The updated runner can now be used directly on the current project dataset without symlink workarounds.

### 8. Real Historical SonarQube Smoke Test

We then created a small real smoke-test input using one treatment repository:

```text
VRSEN/agency-swarm
```

We selected three months:

```text
2024-09
2024-10
2024-11
```

This was a useful test window because it includes a pre-adoption month, the adoption month, and a post-adoption month.

The input file was:

```text
tmp_adoption_test/data/python_did_test/sonarqube_real_smoke/data/ts_repos_monthly.csv
```

with three rows:

```text
VRSEN/agency-swarm,2024-09,f7d31f6c3adc7643c7cd2a8ecf179727eb472c4c
VRSEN/agency-swarm,2024-10,fbf3cb6670e5a8c4cba18f52353cd90fdf0505b1
VRSEN/agency-swarm,2024-11,85180da2f42fec93ac9252567feb3f02f0a86c44
```

We then ran:

```bash
python proc_scripts/run_sonarqube_v2.py \
  --aggregation month \
  --input-file tmp_adoption_test/data/python_did_test/sonarqube_real_smoke/data/ts_repos_monthly.csv \
  --output-file tmp_adoption_test/data/python_did_test/sonarqube_real_smoke/data/ts_repos_monthly_scanned.csv \
  --clone-dir ../ai_code_complexity_study_repo_dataset \
  --num-processes 1
```

The run completed successfully.

All three historical commits were checked out and scanned. SonarQube metrics were successfully retrieved for all three months.

### 9. SonarQube Metrics Collected

The output file was:

```text
tmp_adoption_test/data/python_did_test/sonarqube_real_smoke/data/ts_repos_monthly_scanned.csv
```

It contained the following columns:

```text
repo_name
month
latest_commit
ncloc
bugs
vulnerabilities
code_smells
duplicated_lines_density
comment_lines_density
cognitive_complexity
technical_debt
```

Metric coverage was complete:

```text
ncloc: 3 / 3
bugs: 3 / 3
vulnerabilities: 3 / 3
code_smells: 3 / 3
duplicated_lines_density: 3 / 3
comment_lines_density: 3 / 3
cognitive_complexity: 3 / 3
technical_debt: 3 / 3
```

The collected values were:

```text
2024-09:
  bugs = 1
  vulnerabilities = 2
  code_smells = 157
  ncloc = 5708
  duplicated_lines_density = 0.0
  comment_lines_density = 13.2
  cognitive_complexity = 1465
  technical_debt = 1578

2024-10:
  bugs = 1
  vulnerabilities = 2
  code_smells = 157
  ncloc = 5742
  duplicated_lines_density = 0.0
  comment_lines_density = 13.2
  cognitive_complexity = 1492
  technical_debt = 1605

2024-11:
  bugs = 1
  vulnerabilities = 2
  code_smells = 161
  ncloc = 7064
  duplicated_lines_density = 0.0
  comment_lines_density = 11.5
  cognitive_complexity = 1529
  technical_debt = 1655
```

This confirms that the real historical repository scan pipeline works.

### 10. Clarification About `static_analysis_warnings`

We also clarified where `static_analysis_warnings` should be computed.

The original SonarQube runner collects raw SonarQube metrics such as:

```text
bugs
vulnerabilities
code_smells
duplicated_lines_density
cognitive_complexity
technical_debt
```

It does not compute `static_analysis_warnings` directly.

In the original analysis workflow, `static_analysis_warnings` is derived later as:

```text
static_analysis_warnings = bugs + vulnerabilities + code_smells
```

Therefore, for reproducibility and consistency with the original workflow, we decided not to add this derived metric directly inside `run_sonarqube_v2.py` yet.

Instead, it should be computed later during the merge or analysis preparation step.

For the smoke-test rows, the derived values would be:

```text
2024-09: 160
2024-10: 160
2024-11: 164
```

### 11. Current Status

As of the end of this work session:

```text
Completed:
  SonarQube infrastructure validation
  Tiny project scan
  Balanced panel commit lookup design
  Direct join limitation diagnosis
  Historical lookup solution
  Historical commit lookup for all 738 balanced panel rows
  Update of run_sonarqube_v2.py CLI
  Real historical SonarQube smoke test on treatment repo
  Metric output validation

Not yet completed:
  Detailed warning record smoke test
  Control repo SonarQube smoke test
  Full treatment scan
  Full control scan
  Merge of SonarQube metrics into balanced panel
  Borusyak quality-outcome analysis using SonarQube metrics
```

### 12. Recommended Next Steps After Break

When resuming, the next steps should be:

1. Run detailed warning collection for the `VRSEN/agency-swarm` smoke-test output.
2. Run a control repository smoke test using the updated `--clone-dir` argument.
3. Create permanent wrapper scripts for:

   * historical scan input generation,
   * treatment SonarQube scanning,
   * control SonarQube scanning,
   * merge of SonarQube metrics into the balanced panel.
4. Keep raw SonarQube metrics separate from derived outcomes.
5. Compute `static_analysis_warnings` during the merge or analysis-preparation stage, not inside the scanner.
6. Only after treatment and control smoke tests pass, move to the full 738-row scan.

### 13. Main Takeaway

The most important result from today is that the balanced panel can now be connected to historical code snapshots.

Direct join was insufficient because it only recovered commits for active months. Historical lookup solved this by finding the latest commit at or before each month end. This preserved all 738 balanced repo-month rows and made them usable for SonarQube analysis.

The real repository smoke test confirmed that the updated SonarQube runner can scan historical commits and retrieve quality metrics successfully.
