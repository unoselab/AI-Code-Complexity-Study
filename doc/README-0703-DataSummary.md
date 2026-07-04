네. 첨부된 page 17, 특히 **Table 7**을 기준으로 다시 정리하면, 이전 설명을 조금 더 정확하게 바꿔야 합니다.

핵심은 이것입니다.

```text
4744 = repos.csv에서 language만 JS/TS인 전체 repo 수
441  = baseline panel에서 treatment로 등장하고 language가 JS/TS인 raw treatment repo 수
411  = paper Table 7의 official JS/TS analysis setting treatment repo 수
398  = 우리 replication에서 clone-usable + event_month valid인 JS/TS treatment sample
```

첨부된 page 17의 Table 7은 paper의 공식 JS/TS setting을 이렇게 보고합니다.

```text
JavaScript/TypeScript:
  Treatment Repos = 411
  Control Repos   = 422
  Total Observations = 8,870
  Post-Treatment Observations = 2,279
```

즉, paper와 비교할 때 공식 기준은 **441이 아니라 411**입니다. 441은 우리가 `panel_event_monthly.csv`와 `repos.csv`를 단순 join해서 441은 우리가 `panel_event_monthly.csv`와 `repos.csv`를 단순 join해서 얻은 **raw JS/TS treatment candidates**에 가S analysis setting과 완전히 같은 것은 아닙니다. fileciteturn225file0

## 다시 정리한 흐름

```text
data_baseline_backup/repos.csv
  └─ language만 JS/TS로 세면 4744

data_baseline_backup/panel_event_monthly.csv
+ data_baseline_backup/repos.csv
  └─ treatment repos 중 JS/TS만 세면 441

paper Table 7 official JS/TS setting
  └─ treatment repos = 411
  └─ control repos = 422
  └─ observations = 8870
  └─ post-treatment observations = 2279

our current replication pipeline
  └─ 441 raw JS/TS treatment repos
  └─ 421 clone-usable repos
  └─ 398 clone-usable + event_month valid repos
  └─ 384 matched treatments found in matching.csv
  └─ 339 strict 1:3 treatment repos in pair file
  └─ 337 strict 1:3 treatment repos in final unbalanced panel
```

## 그러면 441과 411의 차이는 무엇인가?

`441`은 우리가 raw baseline files에서 계산한 값입니다.

```text
panel에 treatment로 등장함
+
repos.csv에서 primary language가 JavaScript 또는 TypeScript임
```

하지만 paper Table 7의 `411`은 paper가 실제 robustness analysis에서 사용한 **Programming Language Setting: JavaScript/TypeScript**의 final dataset count입니다.

따라서 이렇게 보는 것이 안전합니다.

```text
441 = raw JS/TS treatment repos identified from baseline panel + metadata
411 = official paper JS/TS analysis treatment repos in Table 7
```

즉, `441`은 Table 7의 `411`을 대체하는 값이 아니라, **왜 우리 replication input이 paper official count와 다른지 추적하기 위한 diagnostic count**입니다.

## 398은 무엇인가?

`398`은 paper 숫자가 아닙니다.
이것은 **우리 replication pipeline에서 만든 treatment sample**입니다.

```text
441 raw JS/TS treatment repos
- 20 clone failed
= 421 clone-usable repos

421 clone-usable repos
- 23 missing event_month
= 398 valid treatment sample repos
```

그래서 `jsts_treatment_sample_main_398.csv`는 이렇게 정의하는 것이 맞습니다.

```text
Our clone-usable, event-valid JS/TS treatment sample derived from raw paper JS/TS treatment candidates.
```

## 가장 중요한 수정점

이전에는 우리가 종종 `441`을 “paper JS/TS treatment repos”처럼 불렀는데, 이제는 더 정확히 이렇게 불러야 합니다.

```text
441 = raw baseline JS/TS treatment repos from panel metadata
411 = official paper Table 7 JS/TS treatment repos
398 = our valid JS/TS treatment sample after current clone/event filtering
```

## CSV / metadata 이름도 이렇게 바꾸는 것이 좋음

`jsts_dataset_size_comparison.csv`에서는 row 이름을 이렇게 두는 것이 가장 명확합니다.

```text
paper_table7_jsts
baseline_raw_jsts_treatment_repos
our_clone_usable_jsts_treatments
our_event_valid_jsts_treatments
our_main_unbalanced
our_strict_1to3_unbalanced
```

그리고 `paper_jsts_treatment_only_panel` 같은 이름은 혼동을 줄 수 있으니, 가능하면 이렇게 바꾸는 것이 좋습니다.

```text
paper_jsts_treatment_only_panel
→ baseline_raw_jsts_treatment_panel
```

또는 더 명확하게:

```text
baseline_raw_jsts_treatment_repos
```

## 최종 해석

첨부 Table 7까지 고려하면, 최종 설명은 이렇게 정리하는 것이 가장 안전합니다.

```text
The official paper JS/TS benchmark is Table 7:
411 treatment repos, 422 control repos, 8,870 observations, and 2,279 post-treatment observations.

Our raw reconstruction from baseline panel metadata identifies 441 JS/TS treatment repositories, but this is a diagnostic raw count rather than the final Table 7 analysis count.

Our replication then applies current clone usability and valid event_month filters, reducing the raw 441 JS/TS treatment repositories to 398 valid treatment repositories.

Therefore, our strict_1to3_unbalanced dataset is smaller than the paper not only because of strict 1:3 filtering, but also because our pipeline starts from the currently reproducible subset of the raw JS/TS treatment candidates.
```

한국어로 아주 짧게 말하면:

```text
paper 공식 JS/TS 기준은 411이다.
441은 우리가 raw panel에서 다시 뽑은 JS/TS treatment 후보 수이다.
398은 현재 clone 가능하고 event_month까지 있는 우리 replication sample이다.
따라서 398은 paper의 411과 직접 같은 단계의 숫자가 아니다.
```


---
---
---


## Daily Research Report

**Date:** 2026-07-04
**Project:** 2026 MSR Speed at the Cost of Quality Replication / JS-TS Analysis

## Objective

Today’s goal was to clarify how the JS/TS treatment sample was created, verify the role of `run7d3-save-treatment-options.sh`, and check whether the `run8d` control-repository analysis cache and metadata were valid before moving to `run8d2`.

## What We Did

We reviewed the JS/TS treatment-count pipeline and clarified why a simple language filter on `data_baseline_backup/repos.csv` returns `4744`, while our treatment sample has only `398` repositories.

We confirmed the distinction among these counts:

```text
4744 = all JS/TS repositories in repos.csv by language only
441  = raw JS/TS treatment repositories reconstructed from baseline panel metadata
411  = official paper Table 7 JS/TS treatment repositories
421  = clone-usable JS/TS treatment repositories
398  = clone-usable + valid event_month JS/TS treatment repositories
```

We reviewed `run7c3-split-valid-event-repos.sh` output and confirmed:

```text
Input rows: 421
Valid rows with event_month: 398
Missing event_month rows: 23
```

We then reviewed `run7d3-save-treatment-options.sh`. This script reads:

```text
tmp_jsts_test/data/jsts_did_test/adoption_month_check.csv
```

and saves four treatment-sample options:

```text
jsts_treatment_sample_main_398.csv
jsts_treatment_sample_exact_match_381.csv
jsts_treatment_sample_within1_month_388.csv
jsts_treatment_sample_diagnostic_10.csv
```

The main sample keeps all 398 valid event-month repositories. The exact sample keeps only repositories where baseline `event_month` and locally detected `adoption_month` exactly match. The within-one-month sample allows small month-level disagreement. The diagnostic sample keeps missing or large-mismatch cases.

We also reviewed these two control-analysis files:

```text
check_cache_control_repos.py
run8d-analyze-control-repos.sh
```

We identified and discussed several updates:

```text
1. The cache-check script name needed to match the actual file name.
2. MAX_REPOS=5 default is risky for production because it can pollute the manifest after a smoke test.
3. The incremental merge here-doc position needed to be safe.
4. Incremental merge keys should use month/week rather than time.
5. repo_name normalization in cache checking should handle empty/nan-like values.
```

Then we checked the actual `run8d` result using:

```bash
MAX_REPOS=0 bash run8d-analyze-control-repos.sh
```

The cache check reported:

```text
REQUESTED_REPOS=453
ANALYZED_REPOS_IN_CACHE=453
MISSING_REPOS=0
CACHE_STATUS=complete
```

So `run8d` correctly skipped expensive git-history analysis because all 453 usable control repositories were already analyzed.

After that, we discovered a stale metadata issue in:

```text
tmp_jsts_test/data/jsts_control_clone_usable_repos_main_398.csv
```

The `target_dir` column still pointed to an old absolute path:

```text
/home/user1-system12/Documents/repro-test01/ai_code_complexity_study_jsts_control_repo_dataset/...
```

but the actual current clone directory is:

```text
../ai_code_complexity_study_jsts_control_repo_dataset
```

Before the fix:

```text
Rows: 453
Unique repos: 453
target_dir exists: 0
target_dir missing: 453
```

We updated the `target_dir` column by rebuilding it from the current clone directory and `repo_name`.

After the fix:

```text
Rows: 453
Unique repos: 453
target_dir exists: 453
target_dir missing: 0

All target_dir values are valid.
```

## Key Findings

The most important finding is that `398` is not a simple JS/TS language count. It is the currently reproducible JS/TS treatment sample after clone usability and event-month validity checks.

The paper’s official JS/TS benchmark remains:

```text
Treatment Repos: 411
Control Repos: 422
Total Observations: 8,870
Post-Treatment Observations: 2,279
```

Our current pipeline starts from a raw reconstructed JS/TS treatment set of 441, then narrows to 398 valid treatment repositories. Therefore, `398` should be described as our replication treatment sample, not as the paper’s official JS/TS treatment count.

We also found that `run8d` outputs are complete and do not need to be regenerated. The control time-series data already covers all 453 usable control repositories.

The stale `target_dir` paths were only a metadata/path-cleanup issue. They did not invalidate the existing `run8d` cache result because `run8d` uses the current `--clone-dir` argument. However, fixing the paths was necessary to prevent confusion and avoid downstream errors if any script later reads `target_dir` directly.

## Files Checked or Updated

```text
run7d3-save-treatment-options.sh
check_cache_control_repos.py
run8d-analyze-control-repos.sh
tmp_jsts_test/data/jsts_control_clone_usable_repos_main_398.csv
```

## Files Confirmed

```text
tmp_jsts_test/data/jsts_treatment_sample_main_398.csv
tmp_jsts_test/data/jsts_treatment_sample_exact_match_381.csv
tmp_jsts_test/data/jsts_treatment_sample_within1_month_388.csv
tmp_jsts_test/data/jsts_treatment_sample_diagnostic_10.csv

tmp_jsts_test/data/jsts_did_control/ts_repos_monthly.csv
tmp_jsts_test/data/jsts_did_control/ts_contributors_monthly.csv
tmp_jsts_test/data/jsts_did_control/cursor_commits.csv
tmp_jsts_test/data/jsts_did_control/ai_adoption_dates.csv
```

## Current Status

The treatment sample logic is now clearer.

The control repo cache is complete.

The stale `target_dir` metadata has been fixed.

The project is ready to continue with:

```bash
bash run8d2-filter-local-cursor-controls.sh
```

## Next Step

Run `run8d2` to filter control repositories with local Cursor evidence and regenerate the final clean control/pair files before rebuilding the matched JS/TS panel.


