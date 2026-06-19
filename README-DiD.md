# Progress Report: Small-Scale Python DiD Pipeline for AI/Cursor Adoption Study

## 1. Project Goal

The current goal is to reproduce and understand the full pipeline behind the MSR 2026 study, “Speed at the Cost of Quality,” using a small-scale dataset before scaling to the full paper-level Difference-in-Differences analysis.

The immediate objective is not yet to produce the final paper-scale DiD results. Instead, we are building and validating an end-to-end small-scale workflow using Python repositories only. This allows us to verify each pipeline component: treatment selection, cloning, Git-history validation, adoption timing verification, and eventually control selection, SonarQube measurement, and DiD estimation.

## 2. Current Working Dataset

We selected Python repositories from the top 100 AI/Cursor adoption candidates and filtered them to keep only usable cloned repositories.

The current treatment input file is:

```text
tmp_adoption_test/data/ai_adopt_repo_python.csv
```

This file contains 13 usable Python AI-adopting treatment repositories. Failed or inaccessible Python repositories were excluded from this file.

The file includes key columns such as:

```text
rank
repo_name
event_month
panel_first_month
panel_latest_month
pre_panel_months
post_panel_months
cursor_commit_rows
cursor_authors
repo_stars
repo_primary_language
repo_commits
repo_contributors
cursor_commit_share
status
target_dir
note
```

This file is now the clean treatment-repository input for the small-scale Python DiD pipeline.

## 3. Candidate Selection Completed

We created and used `proc_scripts/find_repo_pre_post_ai_adoption.py` to select candidate repositories from the baseline event-panel data.

The script reads from:

```text
data_baseline_backup/panel_event_monthly.csv
```

It selects treatment repositories with sufficient pre-adoption and post-adoption months, ranks them by a high-contributor Cursor adoption proxy, and writes two files:

```text
tmp_adoption_test/data/top_100_clone_candidates.csv
tmp_adoption_test/data/top_100_clone_candidates_all_eligible.csv
```

The `top_100_clone_candidates.csv` file contains the first 100 ranked repositories. The `top_100_clone_candidates_all_eligible.csv` file contains all eligible repositories in sorted rank order, so ranks 101, 102, and later can be used as replacements if some top-100 repositories fail to clone.

## 4. Repository Cloning Completed

We created `proc_scripts/clone_repos_v2.py` as a wrapper-style cloning script instead of modifying the original `scripts/clone_repos.py`.

This script supports:

```text
custom candidate CSV
custom clone root
timestamped clone logs
skip existing repositories
non-interactive Git cloning
```

The clone root is:

```text
../ai_code_complexity_study_repo_dataset
```

The full top-100 clone run processed 100 repositories:

```text
processed: 100
cloned: 71
skipped_existing: 23
failed: 6
```

Therefore, 94 repositories were locally usable from the top-100 list.

The non-interactive Git setting worked correctly. When GitHub required credentials for inaccessible repositories, the script logged the failure and continued instead of stopping at a username/password prompt.

## 5. Python Treatment Repository Filtering Completed

We created `proc_scripts/check_python_repo_clone.py` to identify usable Python repositories from the top-100 candidate list and clone log.

The script now writes only usable Python repositories to:

```text
tmp_adoption_test/data/ai_adopt_repo_python.csv
```

It no longer creates a separate `_usable.csv` file. This keeps the workflow simpler.

The current result is:

```text
Python candidate repos: 15
Python usable repos written: 13
Python failed repos excluded: 2
```

The two failed Python repositories were excluded from the final Python treatment input file.

## 6. Git-History Repository Analysis Completed

We created and ran `run4c-analyze-repo.sh`.

This script runs:

```text
proc_scripts/analyze_repos_v2.py
```

using the 13 usable Python treatment repositories.

The run produced the following files:

```text
tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv
tmp_adoption_test/data/python_did_test/ts_contributors_monthly.csv
tmp_adoption_test/data/python_did_test/cursor_commits.csv
tmp_adoption_test/data/python_did_test/ai_adoption_dates.csv
```

The most important file for later DiD construction is:

```text
ts_repos_monthly.csv
```

This is the repo-month panel containing monthly activity data such as commits, lines added, lines removed, contributors, latest monthly commit, and Cursor status.

The second most important file is:

```text
ai_adoption_dates.csv
```

This file gives the Git-history detected Cursor adoption date and adoption month for each treatment repository.

## 7. Repo Name Consistency Fix Completed

We identified a correctness risk in the original analyzer: some original logic reconstructs `repo_name` from folder names by replacing underscores with slashes.

This can break repositories whose owner or repository name contains underscores.

To avoid downstream join errors, we updated `proc_scripts/analyze_repos_v2.py` so that after calling the original `process_repository()`, it overwrites the `repo_name` field in all returned rows using the authoritative value from the input CSV:

```python
correct_repo_name = str(repo_dict["repo_name"]).strip()

for rows in (repo_ts, contrib_ts, cursor_commits):
    for row in rows:
        row["repo_name"] = correct_repo_name
```

This keeps `ts_repos_monthly.csv`, `ts_contributors_monthly.csv`, `cursor_commits.csv`, and `ai_adoption_dates.csv` join-compatible.

## 8. Adoption Timing Validation Completed

We created `proc_scripts/check_time_of_event_and_adoption.py` and integrated it into `run4c-analyze-repo.sh`.

This script compares:

```text
ai_adopt_repo_python.csv:event_month
```

against:

```text
python_did_test/ai_adoption_dates.csv:adoption_month
```

The output file is:

```text
tmp_adoption_test/data/python_did_test/adoption_month_check.csv
```

The latest run showed:

```text
Treatment repos: 13
Matched event/adoption month: 13
Mismatched event/adoption month: 0
Missing adoption month: 0
```

This is a strong validation result. It means all 13 Python treatment repositories have Git-history Cursor evidence, and their detected adoption month exactly matches the baseline event month.

## 9. Current Status

The treatment side of the small-scale Python DiD pipeline is now ready.

We have:

```text
13 usable Python AI-adopting treatment repositories
verified Git-history Cursor adoption evidence
100% event_month/adoption_month agreement
repo-month activity panel
contributor-month activity panel
Cursor commit evidence
timestamped run logs
```

However, this is not yet a complete DiD dataset because we still need control repositories.

At this point:

```text
Treatment repos: ready
Control repos: not ready
SonarQube quality metrics: not yet collected for this small DiD panel
Final DiD regression: not yet run
```

## 10. Next Step: Control Repository Selection

The next major task is to find comparable Python control repositories.

Control repositories should satisfy:

```text
primary language = Python
no Cursor adoption evidence during the analysis window
similar stars
similar commit count
similar contributor count
similar repository size
similar pre-period activity if available
```

Each treatment repository should be matched with one or more control repositories.

For DiD, each matched control repository should receive the same pseudo-event month as its matched treatment repository. For example:

```text
Treatment repo: airweave-ai/airweave
event_month: 2025-03

Matched control repo: some-python/control-repo
pseudo_event_month: 2025-03
```

This allows treatment and control repositories to be aligned on the same relative event-time scale.

## 11. Planned Small-Scale DiD Pipeline

The next full small-scale pipeline should be:

```text
1. Finalize 13 validated Python treatment repositories
2. Select comparable Python control repositories
3. Clone control repositories
4. Verify controls have no Cursor adoption evidence
5. Build treated + control repo-month panel
6. Assign treatment indicator and event month
7. Run SonarQube on monthly historical snapshots
8. Merge SonarQube outcomes into the repo-month panel
9. Run small-scale DiD and event-study models
10. Inspect whether the pipeline produces sensible results before scaling up
```

## 12. Important Reminder

The current work is a small-scale validation pipeline. It is valuable because it checks the mechanics of the full study pipeline, but it should not yet be interpreted as the final empirical result of the paper.

The final paper-scale DiD analysis will require:

```text
larger treatment sample
matched control sample
full SonarQube metric collection
robust event-study design
pre-trend checks
sensitivity analyses
```

For now, the most important achievement is that the treatment-side pipeline works cleanly and the adoption timing validation is perfect for the 13 Python repositories.


---
---
---


# Plan of Work

**방법 A: paper-style PSM**으로 가려면 다음 단계는 **GHArchive 분석**입니다.

쉽게 말하면:

```text
지금까지는 Git history로 treatment repo를 검증했다.
이제는 GHArchive로 treatment와 control repo의 GitHub 활동량을 비교해서 control repo를 찾아야 한다.
```

## 전체 그림

현재 우리는 여기까지 했습니다.

```text
13 Python treatment repos
Cursor adoption month 검증 완료
event_month == adoption_month 13/13
```

하지만 DiD에는 control repo가 필요합니다.

Paper-style PSM에서는 control repo를 그냥 아무 Python repo로 고르지 않습니다. 대신 adoption 전 GitHub 활동 패턴이 비슷한 repo를 찾습니다.

그때 쓰는 데이터가 **GHArchive**입니다.

## GHArchive가 필요한 이유

Git history는 이런 정보를 줍니다.

```text
commits
lines_added
lines_removed
contributors
Cursor adoption commit
```

반면 GHArchive는 GitHub 플랫폼 활동을 줍니다.

```text
WatchEvent
ForkEvent
IssuesEvent
PullRequestEvent
IssueCommentEvent
ReleaseEvent
PushEvent
```

즉, GHArchive는 repo가 adoption 전에 얼마나 활발했는지를 보여줍니다.

Paper-style PSM은 대략 이런 생각입니다.

```text
AI adoption repo와 비슷한 GitHub 활동 패턴을 가진 non-adoption repo를 control로 고르자.
```

## GHArchive 분석 단계

### Step 0. BigQuery / GCP 확인

GHArchive 분석은 보통 BigQuery를 씁니다.

먼저 환경 확인이 필요합니다.

```bash
python -c "import google.cloud.bigquery, pandas"
```

그리고 GCP 인증 확인:

```bash
gcloud auth list
gcloud config get-value project
```

만약 BigQuery 인증이 안 되어 있으면 GHArchive 수집 단계에서 막힙니다.

## Step 1. Treatment repo input 준비

현재 treatment repo 파일은 이것입니다.

```text
tmp_adoption_test/data/ai_adopt_repo_python.csv
```

여기에는 13개 usable Python treatment repo가 있습니다.

GHArchive 분석을 위해 필요한 핵심 컬럼은:

```text
repo_name
event_month
repo_primary_language
repo_stars
repo_commits
repo_contributors
repo_size
```

여기서 `event_month`는 adoption 기준 월입니다.

예:

```text
airweave-ai/airweave, event_month = 2025-03
Kiln-AI/Kiln, event_month = 2025-01
VRSEN/agency-swarm, event_month = 2024-10
```

## Step 2. Treatment repo의 GHArchive event 수집

각 treatment repo에 대해 adoption 전 몇 개월의 GitHub activity를 수집합니다.

예를 들어 event_month가 `2025-03`이면:

```text
2024-09
2024-10
2024-11
2024-12
2025-01
2025-02
```

같은 pre-period를 봅니다.

GHArchive에서 수집할 raw event schema는 보통 이런 형태입니다.

```text
repo
created_at
type
actor
```

예:

```text
airweave-ai/airweave, 2025-01-12, PushEvent, some_user
airweave-ai/airweave, 2025-01-15, IssuesEvent, some_user
```

이 단계의 목적은:

```text
treatment repo들이 adoption 전에 어떤 GitHub 활동 패턴을 가졌는지 계산하기
```

출력 예시:

```text
tmp_adoption_test/data/python_did_test/gharchive_treatment_events.csv
```

## Step 3. Control candidate pool 만들기

이제 control 후보 repo가 필요합니다.

조건은 대략 이렇습니다.

```text
Python repo
Cursor evidence 없음
treatment repo 아님
충분한 GitHub 활동 있음
충분한 pre-period 데이터 있음
```

Paper-style에서는 많은 control candidate를 모읍니다.

예:

```text
수백 개 ~ 수천 개 Python candidate control repos
```

small-scale에서는 처음부터 너무 크게 하지 말고 이렇게 시작하는 것이 좋습니다.

```text
13 treatment repos
각 adoption month별 control candidates 100~500개
```

출력 예시:

```text
tmp_adoption_test/data/python_did_test/gharchive_control_candidates.csv
```

## Step 4. Control candidate의 GHArchive event 수집

control repo에도 pseudo-event month를 줘야 합니다.

예를 들어 treatment repo가 `2025-03` adoption이면, 그 treatment와 비교할 control repo도 `2025-03`을 기준 월로 둡니다.

```text
treatment repo:
  airweave-ai/airweave
  event_month = 2025-03

control repo:
  some-python/control-repo
  pseudo_event_month = 2025-03
```

그리고 control repo도 같은 pre-period의 GHArchive activity를 계산합니다.

```text
2024-09 ~ 2025-02
```

## Step 5. GHArchive raw events를 matching feature로 변환

Raw event를 그대로 matching에 쓰지는 않습니다.

이벤트를 월별/기간별 feature로 바꿉니다.

예:

```text
watch_count_lag_1
watch_count_lag_2
fork_count_lag_1
issue_count_lag_1
pr_count_lag_1
comment_count_lag_1
release_count_lag_1
push_count_lag_1
total_events_lag_1
```

또는 누적 feature:

```text
watch_count_pre_6mo
fork_count_pre_6mo
issues_pre_6mo
prs_pre_6mo
comments_pre_6mo
total_events_pre_6mo
```

쉽게 말하면:

```text
adoption 전 GitHub 활동량을 숫자로 요약한다.
```

## Step 6. Propensity score 계산

이제 treatment repo와 control candidate repo를 한 테이블에 넣고 logistic regression을 합니다.

목적은:

```text
이 repo가 treatment repo처럼 보일 확률을 계산한다.
```

이 확률이 propensity score입니다.

예:

```text
repo_name                         treatment   propensity_score
airweave-ai/airweave              1           0.72
some-python/control-repo          0           0.70
another-python/control-repo       0           0.31
```

`0.72` treatment repo와 `0.70` control repo는 비슷하다고 볼 수 있습니다.

## Step 7. Nearest-neighbor matching

각 treatment repo마다 propensity score가 가까운 control repo를 고릅니다.

Paper-style은 보통 1:N matching을 씁니다.

예:

```text
1 treatment repo
→ 3 matched control repos
```

출력 예시:

```text
tmp_adoption_test/data/python_did_test/python_psm_matches.csv
```

예상 컬럼:

```text
treatment_repo
control_repo
event_month
propensity_score_treated
propensity_score_control
distance
matched_group
```

## Step 8. Control repo clone

matching 결과로 control repo가 정해지면, 이제 control repo를 clone합니다.

출력:

```text
../ai_code_complexity_study_control_repo_dataset
```

또는 기존 clone root 안에 control도 같이 넣을 수 있지만, 처음에는 분리하는 것이 더 안전합니다.

```text
../ai_code_complexity_study_control_repo_dataset
```

## Step 9. Control repo 검증

control repo는 Cursor adoption이 없어야 합니다.

따라서 control repo도 Git history로 검사해야 합니다.

목적:

```text
control repo에 .cursorrules, .cursor/rules/* 같은 evidence가 없어야 한다.
```

만약 control repo에서 Cursor evidence가 나오면 control에서 제외합니다.

## Step 10. DiD repo list 만들기

최종적으로 treated + control repo를 합친 파일을 만듭니다.

예:

```text
tmp_adoption_test/data/python_did_test/python_did_repos.csv
```

형태:

```text
repo_name,treatment,event_month,matched_group,target_dir
airweave-ai/airweave,1,2025-03,group_001,/path/to/treatment
some-python/control-repo,0,2025-03,group_001,/path/to/control
```

이 파일이 이후 SonarQube + DiD panel construction의 기준이 됩니다.

## 정리하면 GHArchive 단계는 이것입니다

```text
1. BigQuery/GHArchive 환경 확인
2. treatment repo의 GHArchive events 수집
3. Python control candidate pool 만들기
4. control candidate의 GHArchive events 수집
5. raw events를 PSM feature로 변환
6. propensity score 계산
7. nearest-neighbor matching
8. matched control repo clone
9. control repo에 Cursor evidence 없는지 검증
10. treated + control combined repo list 생성
```

## 지금 바로 해야 할 첫 작업

가장 먼저 확인할 것은 BigQuery 사용 가능 여부입니다.

```bash
python -c "from google.cloud import bigquery; print('BigQuery OK')"
```

그리고:

```bash
gcloud auth list
gcloud config get-value project
```

이게 정상이어야 GHArchive 분석을 시작할 수 있습니다.

## 추천하는 다음 스크립트 흐름

앞으로는 이렇게 가면 좋습니다.

```text
run5a-fetch-gharchive-treatment.sh
run5b-fetch-gharchive-control-candidates.sh
run5c-match-controls-psm.sh
run5d-clone-control-repos.sh
run5e-validate-control-repos.sh
```

하지만 처음에는 너무 크게 가지 말고, small-scale smoke test로 시작하는 게 좋습니다.

```text
13 treatment repos
각 event_month별 control 후보 100~500개
1 treatment : 1 or 3 controls
```

그 다음 pipeline이 잘 되면 paper-scale로 늘리면 됩니다.
