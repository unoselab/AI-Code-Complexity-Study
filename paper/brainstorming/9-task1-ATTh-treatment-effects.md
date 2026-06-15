오늘 한 일을 **처음부터 끝까지 아주 쉽게, lab notebook처럼** 정리해보겠습니다. 목표는 “무엇을 했고, 왜 했고, 지금 어디까지 왔는지”를 완전히 이해하는 것입니다.

# 0. 오늘의 큰 목표

오늘 우리는 **데이터를 새로 수집하지 않았습니다.**

대신 이미 받은 Zenodo `data/`와 replication package 안의 `notebooks/*.Rmd`를 사용해서, 논문의 결과를 재현하는 **Phase 1**을 시작했습니다.

논문의 README도 이 방향을 권장합니다. `data/` 폴더는 논문에서 실제 사용한 dataset이고, `scripts/`는 GitHub API, BigQuery, SonarQube 등을 다시 실행하는 data collection용입니다. README는 scripts를 다시 돌리면 GitHub repo 변화, API 변화, SonarQube 변화 때문에 논문과 완전히 같은 dataset이 나오지 않을 수 있다고 설명합니다. 

그래서 오늘의 전략은 이것이었습니다.

```text
Phase 1, now:
이미 만들어진 data/ 사용
R notebooks 실행
논문 Table/Figure 결과 이해

Phase 2, later:
GitHub에서 repo 다시 찾기
repo clone
GHArchive 수집
SonarQube 다시 실행
matching부터 다시 만들기
```

# 1. System info 확인

먼저 machine 상태를 봤습니다.

## OS

```text
Ubuntu 22.04.5 LTS
Linux kernel 6.8
x86_64
```

이 환경은 좋습니다. 논문 replication, R 분석, 나중에 SonarQube/BigQuery/GitHub API pipeline을 돌리기에 적절합니다.

## CPU / RAM / Disk

```text
CPU: AMD Ryzen Threadripper PRO 7985WX, 64 cores / 128 threads
RAM: 251 GiB
Disk: 1.8 TB, 1.4 TB free
```

이건 매우 강한 환경입니다. 특히 나중에 repo clone, SonarQube scan, monthly commit history 분석을 할 때 큰 장점이 있습니다.

하지만 오늘 한 **R notebook 재현** 자체에는 이렇게 강한 machine까지는 필요하지 않습니다. 그래도 안정적입니다.

## GPU

```text
2 x NVIDIA RTX 6000 Ada, each 49 GB
```

이번 논문 재현에는 GPU가 필요 없습니다.

이 연구는 LLM을 직접 학습하거나 inference하는 작업이 아니라, GitHub repository data와 SonarQube metric을 사용한 통계 분석입니다.

즉:

```text
GPU = 지금은 거의 irrelevant
CPU/RAM/Disk = 중요
R/Python environment = 중요
```

## Python / Conda

이미 conda env가 있었습니다.

```text
conda env: cursorstudy
Python: 3.11.4
```

그리고 Python packages도 README와 잘 맞게 설치되어 있었습니다.

```text
pandas 2.2.0
numpy 1.26.4
requests 2.31.0
python-dotenv 1.0.1
GitPython 3.1.43
PyGithub 2.3.0
google-cloud-bigquery 3.25.0
scikit-learn 1.5.0
semver 3.0.2
node-semver 0.9.0
gql 3.5.0
aiohttp 3.9.5
```

README에 따르면 Python 3.11.4는 **data collection scripts**용입니다. 즉, Python은 나중에 Phase 2에서 더 중요합니다. 

## R 상태

처음 system info에서는 R 부분이 비어 있었습니다.

그래서 오늘의 중요한 작업은:

```text
R 4.3.3 설치
R packages 설치
Rmd notebooks 실행 가능하게 만들기
```

였습니다.

README에 따르면 논문 결과의 통계 분석과 visualization은 **R 4.3.3**으로 수행되었습니다. 

# 2. Directory structure 확인

현재 project directory는 매우 잘 준비되어 있었습니다.

중요한 폴더는 네 개입니다.

```text
data/
notebooks/
plots/
paper/
```

## data/

여기에 논문 결과 재현용 핵심 dataset이 있었습니다.

특히 중요한 파일:

```text
data/panel_event_monthly.csv
data/matching.csv
data/ts_repos_monthly.csv
data/ts_repos_control_monthly.csv
data/repo_metrics.csv
data/repos.csv
data/cursor_files.csv
data/cursor_commits.csv
data/sonarqube_warnings.csv
```

README에서도 `panel_event_monthly.csv`는 main panel dataset이고, `matching.csv`는 propensity score matching 결과이며, `ts_repos_monthly.csv`와 `ts_repos_control_monthly.csv`는 treatment/control monthly time series라고 설명합니다. 

## notebooks/

여기에 R Markdown notebooks가 있었습니다.

핵심 파일:

```text
DataCollection.Rmd
PropensityScoreMatching.Rmd
DiffInDiffBorusyak.Rmd
DynamicPanel.Rmd
```

README의 reproduction order도 이 흐름입니다. 

## plots/

여기에는 논문 figure PDF들이 있습니다.

오늘 새로 생성한 핵심 PDF:

```text
plots/dynamic_effects_borusyak.pdf
```

이게 paper Figure 3에 해당하는 main dynamic DiD plot입니다.

## scripts/

여기는 오늘은 거의 건드리지 않았습니다.

왜냐하면 여기는 Phase 2용입니다.

```text
clone_repos.py
analyze_repos.py
fetch_gharchive.py
run_sonarqube.py
matching_complex.py
prepare_panel_event.py
```

이 scripts는 GitHub에서 다시 data를 수집하고 dataset을 다시 만드는 용도입니다.

# 3. VS Code Remote SSH 사용 가능 여부 확인

우리는 local MacBook에서 VS Code를 쓰고, Ubuntu server에 Remote SSH로 접속하는 방식이었습니다.

이 방식은 좋습니다.

역할을 나누면:

```text
MacBook:
VS Code UI, editor, browser-like workflow

Ubuntu remote server:
R 실행
Python 실행
data files 저장
notebook rendering
later SonarQube/data collection
```

그래서 RStudio 없이도 충분히 진행할 수 있습니다.

VS Code에서 R을 편하게 쓰기 위해 remote side에 R extension과 `languageserver`를 설치하면 됩니다. 오늘 `languageserver`도 설치 확인했습니다.

# 4. R 설치

우리는 conda env 안에 R을 설치했습니다.

확인 결과:

```text
/home/user1-system12/miniconda3/envs/cursorstudy/bin/R
R version 4.3.3

/home/user1-system12/miniconda3/envs/cursorstudy/bin/Rscript
Rscript version 4.3.3
```

이건 아주 중요합니다.

왜냐하면 README의 R version과 맞기 때문입니다.

```text
Paper environment:
R 4.3.3

Our environment:
R 4.3.3
```

즉, statistical analysis 재현 조건이 좋아졌습니다.

# 5. CRAN mirror 선택

R에서 package 설치를 시작했을 때 CRAN mirror를 물어봤습니다.

우리는:

```text
1: 0-Cloud [https]
```

를 선택했습니다.

이건 안전한 선택입니다. `https://cloud.r-project.org`를 쓰는 방식이고, 일반적으로 가장 무난합니다.

나중에는 R 안에서 이렇게 고정할 수 있습니다.

```r
options(repos = c(CRAN = "https://cloud.r-project.org"))
```

# 6. R package 설치 과정

처음에는 R에서 직접 `install.packages()`를 실행했습니다.

설치하려던 패키지들은 대략 이런 그룹입니다.

## R Markdown / VS Code support

```text
languageserver
rmarkdown
knitr
```

## Data manipulation

```text
tidyverse
data.table
dplyr
tidyr
tibble
lubridate
```

## DiD / causal inference / panel model

```text
fixest
did
didimputation
plm
bacondecomp
DRDID
fastglm
```

## Tables / plots

```text
modelsummary
kableExtra
gridExtra
cowplot
corrplot
RColorBrewer
Cairo
showtext
ggfx
```

README의 R package list도 이런 분석/시각화 중심 패키지들로 구성되어 있습니다. 

# 7. 첫 번째 package 설치 문제

처음 `install.packages()`에서 일부 dependency가 실패했습니다.

에러는 이런 형태였습니다.

```text
fastglm 없음 → DRDID 실패 → did 실패
ragg, rvest, xml2 없음 → tidyverse 실패
Matrix 없음 → did 실패
```

쉽게 말하면:

```text
R package A를 설치하려고 했는데,
A가 필요한 package B가 없어서 실패.
B도 C/C++ library를 필요로 해서 실패.
```

이 문제는 Ubuntu가 나빠서가 아니라, **conda R + CRAN source package** 조합에서 자주 생기는 문제입니다.

그래서 해결 전략을 바꿨습니다.

# 8. 해결 전략: conda-forge에서 R packages 설치

우리는 dependency가 복잡한 R packages를 CRAN source build로 설치하지 않고, conda-forge binary package로 설치했습니다.

예를 들어:

```bash
conda install -c conda-forge \
  r-matrix \
  r-fastglm \
  r-ragg \
  r-rvest \
  r-xml2 \
  r-drdid \
  r-did \
  r-tidyverse \
  -y
```

그 후 핵심 package check를 했습니다.

```r
pkgs <- c(
  "tidyverse", "did", "DRDID", "didimputation", "fixest",
  "plm", "modelsummary", "rmarkdown", "languageserver"
)

sapply(pkgs, requireNamespace, quietly = TRUE)
```

결과는 모두 TRUE였습니다.

```text
tidyverse       TRUE
did             TRUE
DRDID           TRUE
didimputation   TRUE
fixest          TRUE
plm             TRUE
modelsummary    TRUE
rmarkdown       TRUE
languageserver  TRUE
```

이 순간부터 **main statistical notebooks를 실행할 준비가 된 상태**가 되었습니다.

# 9. 두 번째 package 문제: plot/table rendering packages

이후 또 일부 package가 실패했습니다.

```text
systemfonts
magick
Cairo
svglite
ggfx
kableExtra
```

이들은 주로 plot, font, image, HTML table rendering과 관련된 package입니다.

즉:

```text
DiD 계산 자체 = 가능
HTML/PDF plot/table rendering = 일부 문제 가능
```

그래서 이것들도 conda-forge로 설치했습니다.

```bash
conda install -c conda-forge \
  r-systemfonts \
  r-magick \
  r-cairo \
  r-svglite \
  r-ggfx \
  r-kableextra \
  -y
```

그 다음 확인:

```bash
Rscript -e "pkgs <- c('systemfonts','magick','Cairo','svglite','ggfx','kableExtra'); print(setNames(sapply(pkgs, requireNamespace, quietly=TRUE), pkgs))"
```

결과:

```text
systemfonts TRUE
magick      TRUE
Cairo       TRUE
svglite     TRUE
ggfx        TRUE
kableExtra  TRUE
```

이제 plot/table rendering package까지 준비되었습니다.

# 10. 첫 번째 notebook 실행: DataCollection.Rmd

우리가 처음 실행한 notebook은:

```bash
Rscript -e "rmarkdown::render('notebooks/DataCollection.Rmd')"
```

결과:

```text
Output created: DataCollection.html
```

그리고 실제 파일 확인:

```text
notebooks/DataCollection.html
```

timestamp도 새로 바뀌었습니다.

이 notebook의 의미는:

```text
dataset overview
treatment repositories 확인
Cursor adoption time distribution 확인
Table 1 / Figure 2 관련 결과 확인
```

즉, 논문의 Section 3.1과 가장 가까운 notebook입니다.

성공했다는 것은:

```text
R works
rmarkdown works
data files are readable
basic plots/tables work
```

라는 뜻입니다.

# 11. 두 번째 notebook 실행: PropensityScoreMatching.Rmd

다음 실행:

```bash
Rscript -e "rmarkdown::render('notebooks/PropensityScoreMatching.Rmd')"
```

결과:

```text
Output created: PropensityScoreMatching.html
```

파일 확인:

```text
notebooks/PropensityScoreMatching.html
```

이 notebook의 의미는:

```text
Cursor adopter repo와 control repo가 잘 matched 되었는지 확인
propensity score distribution 확인
pre-adoption covariate balance 확인
```

쉽게 말하면:

```text
Cursor 쓴 repo와 안 쓴 repo를 비교해도 되는가?
둘이 원래 비슷했는가?
```

를 보는 단계입니다.

논문의 causal inference에서 매우 중요합니다. 왜냐하면 control group이 이상하면 DiD 결과도 믿기 어렵기 때문입니다.

# 12. 세 번째 notebook 실행: DiffInDiffBorusyak.Rmd

그 다음 핵심 notebook을 실행했습니다.

```bash
Rscript -e "rmarkdown::render('notebooks/DiffInDiffBorusyak.Rmd')"
```

이 notebook이 제일 중요합니다.

왜냐하면 논문의 main DiD result, 특히 **Figure 3**을 만드는 notebook이기 때문입니다.

README도 `DiffInDiffBorusyak.Rmd`를 main DiD results notebook으로 소개합니다. 

# 13. DiffInDiffBorusyak 첫 번째 에러

처음에는 71%에서 실패했습니다.

에러:

```text
object 'significant' not found
```

위치:

```text
compare_activity_all
```

이 문제는 통계 계산 문제가 아니었습니다.

문제는 `ggplot2` plot drawing에서 발생했습니다.

특히:

```r
after_scale(ifelse(significant, colour, NA))
```

같은 plot aesthetic 처리에서 현재 `ggplot2` 버전이 `significant` variable을 못 찾았습니다.

쉽게 말하면:

```text
estimate 계산은 되었는데,
점 모양을 예쁘게 그리는 코드에서 멈춤.
```

그래서 우리는 plotting code만 patch했습니다.

수정의 의미:

```text
기존:
significant 여부에 따라 fill/color를 after_scale에서 처리

수정:
significant 여부에 따라 shape만 단순하게 처리
TRUE  → filled point
FALSE → hollow point
```

중요한 점:

```text
통계 결과 변경 없음
estimate 변경 없음
confidence interval 변경 없음
plot 표시 방식만 안정화
```

# 14. DiffInDiffBorusyak 두 번째 에러

다시 실행했더니 93%까지 갔고, 이번에는 다른 plot에서 실패했습니다.

에러:

```text
invalid hex digit in 'color' or 'lty'
```

위치:

```text
compare_agent_cohort_all
```

이것도 통계 계산 에러가 아니고 plot rendering 에러였습니다.

문제는 `linetype` mapping 쪽이었습니다.

기존에는 `linetype_sig` 변수를 사용해서 significant이면 solid, 아니면 dotted로 그리려고 했습니다.

하지만 현재 R/ggplot/grid 조합에서 color 또는 line type을 처리하다가 실패했습니다.

그래서 우리는 다시 plotting code만 수정했습니다.

수정의 의미:

```text
기존:
geom_errorbar(aes(linetype = linetype_sig))

수정:
significant data와 non-significant data를 나누어
두 개의 geom_errorbar layer로 그림

significant     → linetype = "solid"
non-significant → linetype = "dotted"
```

다시 말하지만:

```text
estimate 변경 없음
model 변경 없음
data 변경 없음
plot 그리는 방식만 더 안정적으로 변경
```

# 15. DiffInDiffBorusyak 최종 성공

patch 후 다시 실행했더니 성공했습니다.

생성된 파일:

```text
notebooks/DiffInDiffBorusyak.html
plots/dynamic_effects_borusyak.pdf
plots/dynamic_effects_activity_all.pdf
plots/dynamic_effects_agent_cohort_all.pdf
```

확인 결과:

```text
notebooks/DiffInDiffBorusyak.html       Jun 15 14:59
plots/dynamic_effects_borusyak.pdf      Jun 15 14:58
plots/dynamic_effects_activity_all.pdf  Jun 15 14:58
plots/dynamic_effects_agent_cohort_all.pdf Jun 15 14:59
```

timestamp가 오늘 날짜로 갱신되었습니다.

즉:

```text
DiffInDiffBorusyak.Rmd successfully reproduced the main DiD outputs.
```

# 16. Figure 3 PDF 확인

우리가 만든 첫 번째 중요 PDF는:

```text
plots/dynamic_effects_borusyak.pdf
```

업로드해서 paper page 8의 Figure 3과 비교했습니다.

결론:

```text
잘 aligned 되어 있음.
```

## Figure 3의 구조

Figure 3은 5개의 outcome panel을 보여줍니다.

```text
1. Commits
2. Lines Added
3. Static Analysis Warnings
4. Duplicated Lines Density
5. Code Complexity
```

paper Figure 3도 동일한 순서입니다. 
우리가 생성한 PDF도 동일한 구조입니다. 

## x축 의미

```text
Months Relative to Cursor Adoption
```

즉, Cursor adoption month를 기준으로 한 상대 시간입니다.

```text
-6, -5, -4, -3, -2 = Cursor 도입 전
0                  = Cursor 도입한 달
1, 2, ..., 6        = Cursor 도입 후
```

## y축 의미

```text
Treatment Effect
```

쉽게 말하면:

```text
실제 Cursor 사용 후 outcome
-
Cursor를 안 썼다면 나왔을 것으로 추정되는 outcome
```

입니다.

이 값이 0보다 크면 Cursor adoption 이후 해당 metric이 증가했다는 뜻입니다.

## 점의 의미

```text
filled dot = statistically significant, p < 0.05
hollow dot = not significant, p >= 0.05
```

paper caption도 filled/hollow dot을 이렇게 설명합니다. 

# 17. Figure 3의 연구 방법상 의미

paper caption은 Figure 3을 이렇게 설명합니다.

```text
0 to +6 months:
horizon-average treatment effects, ATT_h

-6 to -2 months:
placebo pre-adoption treatment effect estimates
for testing parallel trend assumption
```

즉 Figure 3은 두 가지를 동시에 보여줍니다. 

## 도입 전: pre-trend / placebo check

Cursor를 쓰기 전인 -6 to -2개월에 effect가 0 근처여야 합니다.

왜냐하면 아직 Cursor를 쓰기 전이므로, treatment group과 control group이 이미 크게 다르게 움직이고 있으면 안 됩니다.

쉽게 말하면:

```text
Cursor 도입 전부터 treatment repo가 이미 훨씬 빨라지고 있었다면?
→ 도입 후 증가를 Cursor 효과라고 말하기 어려움.
```

Figure 3에서 pre-period dots가 대체로 0 근처에 있습니다.

논문도 모든 outcome이 robust Wald test 기준으로 pre-trend test를 통과했다고 설명합니다. 

## 도입 후: treatment effect

0개월부터 +6개월까지는 Cursor adoption 이후 효과입니다.

여기서 중요한 질문은:

```text
Cursor adoption 후 velocity와 quality가 어떻게 바뀌었는가?
```

입니다.

# 18. Figure 3 해석: Commits

첫 번째 panel은 **Commits**입니다.

우리 PDF와 paper Figure 3 모두 Cursor 도입 직후 commits가 증가하는 패턴을 보입니다.  

논문 본문은 이렇게 설명합니다.

```text
first month: commits +55.4%
second month: commits +14.5%
```

하지만 이 효과는 오래 가지 않습니다. 2개월 이후에는 대부분 0 근처로 돌아갑니다. 

쉽게 말하면:

```text
Cursor 도입 직후에는 commit 활동이 잠깐 늘어난다.
하지만 장기적으로 계속 commit 수가 높아지는 것은 아니다.
```

# 19. Figure 3 해석: Lines Added

두 번째 panel은 **Lines Added**입니다.

이게 velocity 측면에서 가장 강한 결과입니다.

논문은:

```text
first month: lines added +281.3%
second month: lines added +48.4%
```

라고 설명합니다. 

쉽게 말하면:

```text
Cursor를 도입하면 처음에는 코드가 엄청 많이 추가된다.
하지만 그 증가가 오래 지속되지는 않는다.
```

그래서 논문의 표현은:

```text
large but transient velocity increase
```

입니다.

한국어로는:

```text
크지만 일시적인 개발 속도 증가
```

입니다.

# 20. Figure 3 해석: Static Analysis Warnings

세 번째 panel은 **Static Analysis Warnings**입니다.

여기서 중요한 점은 velocity와 다릅니다.

Velocity는 처음 1~2개월만 증가했지만, warnings는 adoption 이후 여러 달 동안 계속 증가합니다.

논문은 평균적으로 static analysis warnings가:

```text
+30.3%
```

증가했다고 설명합니다. 

쉽게 말하면:

```text
Cursor 도입 후 코드 생산량만 늘어난 것이 아니라,
SonarQube가 잡는 potential issue/warning도 늘어났다.
```

이것이 논문의 “quality cost” 중 하나입니다.

# 21. Figure 3 해석: Duplicated Lines Density

네 번째 panel은 **Duplicated Lines Density**입니다.

이 panel은 다른 quality metrics와 다릅니다.

대부분 effect가 불안정하고, significant하지 않습니다.

논문도 duplicate line density effect는 insignificant하다고 설명합니다. 

쉽게 말하면:

```text
Cursor가 코드 중복률을 확실히 늘렸다는 강한 증거는 없다.
```

즉, 논문의 quality degradation은 모든 metric에서 나타난 것이 아닙니다.

주로:

```text
Static Analysis Warnings
Code Complexity
```

에서 나타났습니다.

# 22. Figure 3 해석: Code Complexity

다섯 번째 panel은 **Code Complexity**입니다.

Cursor adoption 이후 code complexity effect가 지속적으로 양수입니다.

논문은 평균적으로 code complexity가:

```text
+41.6%
```

증가했다고 설명합니다. 

쉽게 말하면:

```text
Cursor 도입 후 코드가 더 복잡해지는 경향이 지속된다.
```

이건 논문의 핵심 quality result입니다.

# 23. Figure 3 전체 메시지

Figure 3을 한 문장으로 요약하면:

```text
Cursor adoption은 처음 1~2개월 동안 개발 속도를 크게 올리지만,
static analysis warnings와 code complexity는 더 오래 지속적으로 증가한다.
```

즉:

```text
short-term velocity gain
long-term quality/complexity cost
```

입니다.

한국어로는:

```text
단기적으로는 빨라지지만,
장기적으로는 코드 품질 부담과 복잡도가 증가한다.
```

이게 논문 제목인:

```text
Speed at the Cost of Quality
```

와 직접 연결됩니다.

# 24. Paper Figure 3과 우리가 만든 PDF의 alignment

비교 결과는 좋습니다.

| 항목                              | 우리가 만든 PDF | Paper Figure 3 | 판단 |
| ------------------------------- | ---------- | -------------- | -- |
| Outcome 5개                      | 동일         | 동일             | OK |
| x축 -6 to +6                     | 동일         | 동일             | OK |
| y축 Treatment Effect             | 동일         | 동일             | OK |
| vertical dashed line            | 있음         | 있음             | OK |
| filled/hollow dot 설명            | 있음         | 있음             | OK |
| velocity 초기 증가                  | 보임         | 보임             | OK |
| warnings 지속 증가                  | 보임         | 보임             | OK |
| complexity 지속 증가                | 보임         | 보임             | OK |
| duplicate density insignificant | 보임         | 보임             | OK |

우리가 patch한 부분 때문에 점/선의 시각적 스타일은 아주 미세하게 다를 수 있습니다. 하지만 핵심 estimate, confidence interval, significant/non-significant pattern, figure message는 paper와 잘 맞습니다.

# 25. 오늘 현재까지의 최종 상태

현재 완료된 것:

```text
[완료] system info 확인
[완료] conda cursorstudy env 확인
[완료] Python packages 확인
[완료] R 4.3.3 설치
[완료] CRAN mirror 선택
[완료] 핵심 R packages 설치
[완료] plot/table R packages 설치
[완료] DataCollection.Rmd render 성공
[완료] PropensityScoreMatching.Rmd render 성공
[완료] DiffInDiffBorusyak.Rmd render 성공
[완료] Figure 3 PDF 생성
[완료] Figure 3 paper alignment 확인
```

아직 남은 것:

```text
[다음] DynamicPanel.Rmd 실행
[다음] Table 3 이해
[다음] GMM 결과 해석
[나중] DiffInDiffAll.Rmd robustness
[나중] AnalyzeSonarQubeWarnings.Rmd appendix
[훨씬 나중] data collection pipeline 재실행
```

# 26. 오늘 한 일을 아주 짧게 다시 말하면

오늘 우리는 Ubuntu remote server에서 `cursorstudy` conda environment 안에 R 4.3.3을 세팅하고, 필요한 R packages를 설치했습니다. 중간에 CRAN source build dependency 문제가 있었지만, conda-forge R packages로 해결했습니다. 그 다음 `DataCollection.Rmd`, `PropensityScoreMatching.Rmd`, `DiffInDiffBorusyak.Rmd`를 순서대로 실행했습니다. `DiffInDiffBorusyak.Rmd`에서는 최신 ggplot 환경 때문에 plot rendering 문제가 두 번 발생했지만, 통계 계산이 아니라 그림 스타일 문제였기 때문에 plotting code만 안전하게 수정했습니다. 최종적으로 `dynamic_effects_borusyak.pdf`를 생성했고, 이것이 paper page 8의 Figure 3과 잘 일치함을 확인했습니다.

지금 우리는 논문의 가장 중요한 main result 중 하나, 즉:

```text
Cursor adoption → short-term velocity increase
Cursor adoption → persistent warnings and complexity increase
```

를 직접 재현한 상태입니다.
