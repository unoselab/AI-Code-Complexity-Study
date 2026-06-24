# AI Code Complexity Study: SonarQube, GitHub Discovery, and Adoption-Date Pipeline Notes

## 1. Purpose and Current Research Context

This document records the current technical status of the `AI-Code-Complexity-Study` project and the Phase 2 pipeline work.

The project is based on the original Cursor adoption replication package. The broader research question is whether adoption of AI coding tools, especially Cursor-style AI coding assistance, is associated with short-term development velocity changes and longer-term changes in code quality, complexity, maintainability, and static-analysis warnings.

Phase 1 reproduction using the original prepared data and R notebooks has already been completed. Phase 2 focuses on rerunning or partially rerunning the original pipeline with live GitHub data, local cloned repositories, Git-history adoption detection, local SonarQube scans, and local metric/warning collection.

The current Phase 2 work has four major goals:

```text
1. Discover repositories with Cursor or other AI coding-tool evidence.
2. Detect AI-tool adoption dates from Git history.
3. Build repo-month event panels around adoption months.
4. Run SonarQube scans and collect aggregate metrics and detailed warnings.
```

---

## 2. Project Repository and Environment

The active project directory is:

```text
~/project-workspace/ai_code_complexity_study
```

The project was copied from the original `cursor_study` project and initialized as a separate GitHub repository.

The Git remote is:

```text
git@github.com:unoselab/AI-Code-Complexity-Study.git
```

The active Python/Conda environment used for the current work is:

```text
aicomplexity
```

Important working directories:

```text
Project root:
  ~/project-workspace/ai_code_complexity_study

Cloned treatment repositories:
  ~/project-workspace/CursorRepos

Temporary SonarQube batch data:
  tmp_sonar_batch/data

Temporary adoption-detection test data:
  tmp_adoption_test/data

Temporary GitHub search partition outputs:
  temp/

Run logs:
  logs/
```

---

## 3. GitHub Token and GitHub API Status

A `.env` file exists in the project root.

It stores the GitHub token and SonarQube configuration. The GitHub token is stored as:

```text
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

The token is required for GitHub API operations, especially code search and repository metadata retrieval.

A previous test confirmed authenticated GitHub API access:

```text
Core API limit: 5000 / 5000
Search API limit: 30 / 30
Query: filename:.cursorrules
Total count: 1000
```

Important GitHub search limitation:

```text
GitHub code search results are capped at about 1000 results per query.
```

Because of this cap, repository discovery uses partitioned or adaptive search strategies, often splitting queries by repository size ranges.

---

## 4. Ongoing GitHub AI-Tool Repository Discovery

The first major data-collection process is:

```text
run1-fetch-ai-tool-repo.sh
```

It runs:

```text
proc_scripts/fetch_ai_tool_repos.py
```

The confirmed process tree showed one real Python job running inside tmux:

```text
tmux session: bigclone
└── bash ./run1-fetch-ai-tool-repo.sh
    ├── bash ./run1-fetch-ai-tool-repo.sh
    │   └── python -u proc_scripts/fetch_ai_tool_repos.py
    └── tee logs/run-fetch-ai-tool-repo-0617-1450.log
```

The two Bash processes are normal because the wrapper script uses a logging pipeline with `tee`. There is only one real `fetch_ai_tool_repos.py` process.

The confirmed log file is:

```text
logs/run-fetch-ai-tool-repo-0617-1450.log
```

The fetch process writes intermediate partition files under:

```text
temp/
```

Example output files:

```text
temp/cursor_repos_20260617_size_550_to_555.csv
temp/cursor_repos_20260617_size_560_to_565.csv
temp/cursor_repos_20260617_size_565_to_570.csv
temp/cursor_repos_20260617_size_625_to_630.csv
temp/cursor_repos_20260617_size_630_to_635.csv
temp/cursor_repos_20260617_size_635_to_640.csv
```

These files are newer than the original paper’s discovery data because they are being collected from GitHub now. However, this discovery step gives current candidate repositories and current metadata; it does not automatically reconstruct monthly historical panel data. Historical monthly commits must still be reconstructed from Git history.

Useful monitoring commands:

```bash
pgrep -af fetch_ai_tool_repos.py

ps -p <PID> -o pid,stat,etime,pcpu,pmem,cmd

tail -f logs/run-fetch-ai-tool-repo-0617-1450.log

find temp -name 'cursor_repos_20260617_size_*.csv' | wc -l
```

---

## 5. SonarQube Strategy

We use:

```text
Self-hosted SonarQube Community Build
```

instead of SonarQube Cloud or a paid trial.

The local research workflow is:

```text
local cloned repository
→ checkout target commit
→ run SonarScanner CLI
→ upload analysis to local SonarQube
→ query SonarQube Web API for metrics and warnings
```

This setup avoids cloud-trial limitations and keeps scans local.

---

## 6. SonarQube Server Setup

SonarQube is running in Docker.

The container name is:

```text
sonarqube
```

The image is:

```text
sonarqube:latest
```

The local endpoint on the remote Ubuntu server is:

```text
http://localhost:9000
```

The observed SonarQube version is:

```text
26.6.0.123539
```

For Python scripts running directly on the remote server, use:

```text
SONAR_HOST=http://localhost:9000
```

No SSH tunnel is needed for scripts running on the same machine as Docker.

For browser access from a local laptop, use SSH or VS Code port forwarding:

```bash
ssh -L 9000:localhost:9000 user1-system12@<server-address>
```

If local port `9000` is occupied:

```bash
ssh -L 9001:localhost:9000 user1-system12@<server-address>
```

Then open:

```text
http://localhost:9001
```

---

## 7. SonarQube Token and `.env`

The `.env` file contains:

```text
SONAR_HOST=http://localhost:9000
SONAR_TOKEN=<local_sonarqube_token>
SONAR_SCANNER_PATH=/home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
```

The `.env` file must not be committed to Git. Ensure `.gitignore` contains:

```text
.env
```

The SonarQube token was validated through:

```text
/api/authentication/validate
```

and returned:

```text
{"valid": true}
```

---

## 8. SonarScanner CLI Setup

SonarScanner CLI is installed at:

```text
/home/user1-system12/tools/sonar-scanner
```

Executable path:

```text
/home/user1-system12/tools/sonar-scanner/bin/sonar-scanner
```

The scanner test confirmed:

```text
Exists: True
Is file: True
Executable: True
Return code: 0
SonarScanner CLI 8.0.1.6346
Linux 6.8.0-94-generic amd64
```

---

## 9. SonarQube Authentication Convention

The original scripts often used Bearer authentication:

```python
headers = {"Authorization": f"Bearer {SONAR_TOKEN}"}
requests.get(url, headers=headers, params=params)
```

For our local Docker setup, the tested and reliable API style is token-as-basic-auth:

```python
requests.get(url, auth=(SONAR_TOKEN, ""), params=params)
```

Recommended convention:

```text
SonarScanner upload:
  -Dsonar.token=<token>

SonarQube API reads:
  requests.get(..., auth=(SONAR_TOKEN, ""))
```

This convention is used in the new or patched `proc_scripts` files.

---

## 10. Tiny SonarQube Smoke Test

Before scanning real repositories, a tiny project was created:

```text
tmp_sonar_smoke/tiny_project
```

Its structure:

```text
tmp_sonar_smoke/
└── tiny_project
    ├── sonar-project.properties
    └── src
        └── app.py
```

The tiny scan verified the full infrastructure path:

```text
local source files
→ SonarScanner CLI
→ local SonarQube server
→ analysis report upload
→ SonarQube dashboard
```

The scan produced:

```text
ANALYSIS SUCCESSFUL
EXECUTION SUCCESS
```

The tiny project dashboard was:

```text
http://localhost:9000/dashboard?id=cursorstudy-tiny-test
```

This confirmed that the scanner can analyze a local source tree and upload results to the local SonarQube server.

Warnings observed during the tiny scan were acceptable:

```text
Python version not specified
Missing blame information for src/app.py
```

The missing blame warning was expected because the tiny project was not a normal committed Git repository.

---

## 11. Real Repository SonarQube Smoke Test: `run2c`

After the tiny scan, we tested real repositories with a temporary input file.

The helper script:

```text
proc_scripts/create_tmp_repo_timeseries_input.py
```

creates a temporary CSV from cloned repository `HEAD` commits:

```text
repo_name,month,latest_commit
```

It is used by:

```text
proc_scripts/run_sonarqube_v2.py
```

The first successful real-repo smoke test used:

```text
TheSethRose/Agent-Chat
utensils/mcp-nixos
nextml-code/pytorch-datastream
```

The test validated:

```text
1. Repository cloning works.
2. Temporary time-series input generation works.
3. SonarScanner execution works.
4. SonarQube metric retrieval works.
5. Metrics are written back to the temporary CSV.
```

Aggregate metrics collected include:

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

The `static_analysis_warnings` metric is computed as:

```text
bugs + vulnerabilities + code_smells
```

---

## 12. Dynamic Date-Range Patch in `run_sonarqube_v2.py`

A key bug was found during the `run2c` test.

The temporary CSV used:

```text
month = 2026-06
```

but the runner originally processed only the original study window:

```text
2024-01 to 2025-08
```

Therefore, the `2026-06` rows were skipped.

We updated `run_sonarqube_v2.py` so that it infers the processing date range from the input CSV:

```text
START_DATE = min(input month)
END_DATE   = max(input month)
```

The successful log showed:

```text
Using input-derived date range: 2026-06 to 2026-06
```

We also patched related issues:

```text
1. Removed a duplicated dynamic-date block that caused a SyntaxError.
2. Added missing import re.
3. Added support for --data-dir.
4. Added wait/retry logic after SonarScanner upload so SonarQube Compute Engine can index the analysis.
```

The wait/retry logic was necessary because `ANALYSIS SUCCESSFUL` means the scanner uploaded the report, but the SonarQube Compute Engine may need additional time before the version appears through the API.

---

## 13. `run3a`: Multi-Month SonarQube Smoke Test With Actual Git History

The next test moved closer to the original paper pipeline.

The script:

```text
proc_scripts/create_tmp_repo_timeseries_history.py
```

creates a temporary multi-month input using actual Git history.

For each repo and month, it finds the latest commit at or before the end of the month:

```bash
git rev-list -n 1 --before "<month-end> 23:59:59" HEAD
```

The `run3a` test used:

```text
2026-03
2026-04
2026-05
```

and the three sample repositories.

The input produced 9 repo-month rows:

```text
3 repos × 3 months = 9 rows
```

Results:

```text
TheSethRose/Agent-Chat:
  same commit across 2026-03, 2026-04, 2026-05

nextml-code/pytorch-datastream:
  same commit across 2026-03, 2026-04, 2026-05

utensils/mcp-nixos:
  different commits for 2026-03, 2026-04, 2026-05
```

This is valid. If a repository has no new commits between month-end dates, the latest historical commit remains the same.

The strongest validation came from `utensils/mcp-nixos`, where different historical commits produced different SonarQube metrics:

```text
2026-03:
  static_analysis_warnings = 50

2026-04:
  static_analysis_warnings = 39

2026-05:
  static_analysis_warnings = 39
```

This confirms that:

```text
run_sonarqube_v2.py handles multiple periods per repository.
```

---

## 14. Detailed SonarQube Warning Collection

Aggregate metrics from `run_sonarqube_v2.py` are used for the main quantitative analysis.

Detailed warning records are collected for interpretation and diagnostics.

The original warning collector is:

```text
scripts/collect_sonarqube_warnings.py
```

It is paper-oriented. It reads:

```text
data/panel_event_monthly.csv
```

and collects warnings around the Cursor adoption event using:

```text
event_time
relative_period
```

It should not be deleted or replaced.

We created an extended wrapper:

```text
proc_scripts/collect_sonarqube_warnings_v2.py
```

Design:

```text
1. Import the original script.
2. Reuse original pure helper functions where possible.
3. Preserve original event-mode logic.
4. Add timeseries mode for run3a smoke tests.
5. Use token-as-basic-auth for local SonarQube API reads.
```

Supported modes:

```text
--mode event
  Original paper-style behavior.
  Reads panel_event_monthly.csv.
  Uses event_time and relative_period.

--mode timeseries
  Smoke-test behavior.
  Reads ts_repos_monthly.csv.
  Uses repo_name, month, latest_commit.
```

The `run3a` detailed warning step used `--mode timeseries`.

The warning collector found:

```text
9 repo-month rows
47 detailed issue records
9 unique SonarQube warning rules
```

All collected detailed issues were:

```text
CODE_SMELL
```

Counts:

```text
utensils/mcp-nixos at 2026-03:
  39 detailed issues

utensils/mcp-nixos at 2026-04:
  8 detailed issues

utensils/mcp-nixos at 2026-05:
  0 detailed issues
```

Other sample repos had zero detailed issues collected in the created-date windows, even though their aggregate SonarQube metrics contained code smells or vulnerabilities. This is an important limitation of interpreting SonarQube issue creation dates across repeated version scans.

Generated files:

```text
tmp_sonar_batch/data/sonarqube_warnings.csv
tmp_sonar_batch/data/sonarqube_warning_definitions.csv
```

Important interpretation:

```text
Detailed warning files are diagnostic and descriptive.
They should not replace aggregate repo-month metrics in the main causal model.
```

---

## 15. When Detailed Warnings Are Used

The main paper-style causal analysis should use repo-month aggregate metrics:

```text
bugs
vulnerabilities
code_smells
static_analysis_warnings
cognitive_complexity
technical_debt
ncloc
duplicated_lines_density
comment_lines_density
```

Detailed warning records are used after the main model for interpretation:

```text
1. Which SonarQube rules are most common?
2. Are warnings mostly CODE_SMELL, BUG, or VULNERABILITY?
3. Which severities dominate?
4. Which files/components contain repeated warnings?
5. Can we show examples of warning types behind aggregate changes?
6. Are warning changes mainly maintainability-related or security-related?
```

Because SonarQube does not provide a perfect historical issue snapshot for every scanned version, detailed warnings should be described as coarse diagnostic evidence.

---

## 16. Git-History AI Adoption Detection: `run4a`

The next milestone was AI code generator adoption-date detection.

The original adoption-relevant analyzer is:

```text
scripts/analyze_repos.py
```

It contains the original logic for:

```text
find_cursor_commits()
count_cursor_commits_by_time()
time-series generation
```

We created a wrapper/extension:

```text
proc_scripts/analyze_repos_v2.py
```

Design:

```text
1. Import scripts/analyze_repos.py.
2. Reuse original functions.
3. Add CLI arguments.
4. Add sample testing with --max-repos or --repos.
5. Add ai_adoption_dates.csv output.
```

Important CLI arguments:

```text
--repos-file
--clone-dir
--output-dir
--aggregation
--max-repos
--repos
--num-processes
```

The test script:

```text
run4a-detect-ai-adoption.sh
```

created a small repo list:

```text
TheSethRose/Agent-Chat
utensils/mcp-nixos
nextml-code/pytorch-datastream
```

and ran:

```bash
python proc_scripts/analyze_repos_v2.py \
  --repos-file tmp_adoption_test/data/repos.csv \
  --clone-dir ../CursorRepos \
  --output-dir tmp_adoption_test/data \
  --aggregation month \
  --num-processes 1
```

Generated outputs:

```text
tmp_adoption_test/data/ts_repos_monthly.csv
tmp_adoption_test/data/ts_contributors_monthly.csv
tmp_adoption_test/data/cursor_commits.csv
tmp_adoption_test/data/ai_adoption_dates.csv
```

The run completed successfully:

```text
Repos with Cursor adoption evidence: 3
```

---

## 17. Verified Adoption Evidence

The detected adoption evidence was manually checked with:

```bash
git show --name-status --oneline --no-renames <adoption_commit>
```

Results:

### 17.1 `TheSethRose/Agent-Chat`

```text
adoption_month: 2024-10
adoption_commit: c30a90b5d6bad4af242c9dd99ff40cd4497261c0
evidence_paths: .cursorrules
```

The adoption commit was the initial commit:

```text
A .cursorrules
A .env.example
A .gitignore
A README.md
A app.py
A enhancements.md
A requirements.txt
```

Interpretation:

```text
Cursor evidence exists from project birth.
This repo has no clean pre-adoption period inside its own observed Git history.
```

It should be marked later as:

```text
adoption_at_initial_commit = true
```

### 17.2 `nextml-code/pytorch-datastream`

```text
adoption_month: 2025-01
adoption_commit: 5bcbc9467c2b8a19336539482b88f70f871d2825
evidence_paths: .cursorrules
```

The adoption commit added:

```text
A .cursorrules
```

Interpretation:

```text
Cursor adoption evidence detected in 2025-01.
```

### 17.3 `utensils/mcp-nixos`

```text
adoption_month: 2025-03
adoption_commit: 679572cc171210deeb72bb9f7acf11eb2c0867c4
evidence_paths: .cursorrules
```

The same commit also added other AI-agent/tool files:

```text
A .cursorrules
A .goosehints
A .windsurfrules
A CLAUDE.md
```

Interpretation:

```text
This is strong AI coding-tool adoption evidence.
It also suggests simultaneous adoption of multiple AI agents, not Cursor only.
```

This should be handled carefully in later causal interpretation.

---

## 18. Event Panel Concept

An event panel is:

```text
repo-month time-series data
+ AI/Cursor adoption month
= event-study / DiD-ready panel dataset
```

Each row is one repository-month observation.

Example:

```text
repo_name           month     event     treated   relative_month
utensils/mcp-nixos  2025-02   2025-03   1         -1
utensils/mcp-nixos  2025-03   2025-03   1          0
utensils/mcp-nixos  2025-04   2025-03   1          1
```

Interpretation:

```text
relative_month = -1 → one month before adoption
relative_month = 0  → adoption month
relative_month = 1  → one month after adoption
```

The key idea is that calendar time differs across repositories, but event time aligns repositories around adoption.

The next output should be:

```text
tmp_adoption_test/data/panel_event_monthly.csv
```

or, for larger runs:

```text
data/panel_event_monthly.csv
```

---

## 19. Candidate Selection From Baseline Data

We inspected baseline data under:

```text
data_baseline_backup/
```

Important files:

```text
panel_event_monthly.csv
ts_repos_monthly.csv
cursor_commits.csv
cursor_files.csv
repo_metrics.csv
repos.csv
sonarqube_warnings.csv
```

The most important file for candidate selection is:

```text
data_baseline_backup/panel_event_monthly.csv
```

It contains:

```text
repo_name
time
event
post_event
time_to_event
cursor
dataset_source
other_agents
high_confidence
quality and velocity metrics
```

A candidate-selection script was compared in two versions:

```text
proc_scripts/find_repo_pre_post_ai_adoption.py
proc_scripts/find_repo_pre_post_ai_adoption_v2.py
```

Version 1 counted raw rows, which could overstate pre/post coverage if duplicated `(repo_name, time)` rows existed.

Version 2 is better because it:

```text
1. Counts distinct repo-months instead of raw rows.
2. Drops duplicated (repo_name, time) rows before calculating windows.
3. Adds rank.
4. Adds repository metadata such as stars, language, and size.
5. Adds --require-cursor-evidence.
6. Adds window_touches_data_edge diagnostics.
7. Cleans invalid month values.
```

Version 2 reported:

```text
Duplicated (repo, month) rows collapsed: 51
```

Version 2 should be treated as canonical.

Recommended command:

```bash
cp proc_scripts/find_repo_pre_post_ai_adoption_v2.py \
   proc_scripts/find_repo_pre_post_ai_adoption.py

python proc_scripts/find_repo_pre_post_ai_adoption.py \
  --data-dir data_baseline_backup \
  --top-n 100 \
  --min-pre-months 1 \
  --min-post-months 1 \
  --require-cursor-evidence \
  --output tmp_adoption_test/data/top_100_clone_candidates.csv
```

Expected output line count:

```text
101
```

because it should contain 1 header plus 100 selected repositories.

---

## 20. Current Pipeline Status

Completed:

```text
1. New project repository prepared.
2. GitHub token configured and tested.
3. GitHub API search tested.
4. Ongoing GitHub AI-tool repo discovery started.
5. Local SonarQube Docker server running.
6. SonarQube token generated and validated.
7. SonarScanner CLI installed and tested.
8. Tiny SonarQube scan completed.
9. Real-repo single-month SonarQube smoke test completed.
10. Dynamic input-derived date range added to run_sonarqube_v2.py.
11. Post-scan SonarQube Compute Engine wait/retry added.
12. Multi-month historical SonarQube smoke test completed.
13. Detailed SonarQube warning collection implemented and tested.
14. AI/Cursor adoption-date detection wrapper implemented and tested.
15. Adoption commits manually validated for three sample repositories.
```

Current limitations:

```text
1. The current three sample repos are useful for testing, but not all are clean causal candidates.
2. Some repos have adoption at initial commit and therefore no internal pre-adoption period.
3. Some commits introduce multiple AI-tool files at once, requiring careful interpretation.
4. Detailed warning collection is diagnostic, not a perfect historical warning snapshot.
5. The ongoing GitHub discovery job is still collecting current candidate repos.
```

---

## 21. Immediate Next Steps

The next step is:

```text
run4b:
  Build a small event panel from ai_adoption_dates.csv and ts_repos_monthly.csv.
```

Expected inputs:

```text
tmp_adoption_test/data/ai_adoption_dates.csv
tmp_adoption_test/data/ts_repos_monthly.csv
```

Expected output:

```text
tmp_adoption_test/data/panel_event_monthly.csv
```

The panel should include:

```text
repo_name
month
latest_commit
event
treated
relative_month
adoption_at_initial_commit
```

After that, the next steps are:

```text
run4c:
  Select cleaner sample repos with both pre- and post-adoption months.

run5a:
  Clone top 100 candidate repositories selected from baseline data.

run5b:
  Run Git-history adoption validation on the cloned candidate set.

run5c:
  Build an event panel for selected validated candidates.

run6a:
  Run SonarQube metrics on the validated multi-repo event panel.

run6b:
  Collect detailed warning diagnostics for the same panel.
```

---

## 22. Recommended Next Commands

Build the top 100 candidate list:

```bash
cp proc_scripts/find_repo_pre_post_ai_adoption_v2.py \
   proc_scripts/find_repo_pre_post_ai_adoption.py

python proc_scripts/find_repo_pre_post_ai_adoption.py \
  --data-dir data_baseline_backup \
  --top-n 100 \
  --min-pre-months 1 \
  --min-post-months 1 \
  --require-cursor-evidence \
  --output tmp_adoption_test/data/top_100_clone_candidates.csv

wc -l tmp_adoption_test/data/top_100_clone_candidates.csv
head -20 tmp_adoption_test/data/top_100_clone_candidates.csv
```

Build the small event panel next:

```text
Create:
  proc_scripts/build_event_panel_v2.py

Inputs:
  tmp_adoption_test/data/ts_repos_monthly.csv
  tmp_adoption_test/data/ai_adoption_dates.csv

Output:
  tmp_adoption_test/data/panel_event_monthly.csv
```

---

## 23. Summary

The infrastructure is now stable:

```text
GitHub API works.
GitHub discovery is running.
SonarQube server works.
SonarQube token works.
SonarScanner works.
Tiny and real-repo scans work.
Aggregate metric retrieval works.
Detailed warning collection works.
Git-history adoption detection works.
```

The next methodological step is event-panel construction:

```text
adoption dates
+ monthly repository time series
→ event-study panel
```

Once this works on the three sample repositories, the project can scale to selected candidate repositories from the baseline data and eventually to a larger updated dataset.
