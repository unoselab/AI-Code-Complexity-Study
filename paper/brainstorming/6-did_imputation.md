## 💡 `cursor_study` 데이터와 Borusyak DiD 수식의 실제 작동 구조

이 연구의 핵심은 복잡한 머신러닝 아키텍처를 새로 설계한 것이 아니라, 저장소-월(Repository-Month) 단위의 패널 데이터를 정밀하게 빌드한 뒤, **Borusyak et al.의 대체 기반 이중차분법(Imputation-based Difference-in-Differences)** 방법론을 통해 Cursor Adoption의 인과적 효과를 추정한 것입니다.

데이터셋의 한 행(Row)은 단일 **Repository-Month Observation**입니다. 즉, 특정 저장소가 특정 월에 보인 개발 활동과 코드 품질 상태를 하나의 독립된 관측치로 기록합니다.

---

## 1. 마스터 데이터셋의 핵심 구조 (`panel_event_monthly.csv`)

월 단위 DiD 분석을 위한 메인 패널 데이터셋의 핵심 컬럼과 수학 기호의 1:1 매핑 가이드는 다음과 같습니다.

| 컬럼명 (Column) | 쉬운 의미 | 수식 및 이론적 개념과의 연결 |
| --- | --- | --- |
| **`repo_name`** | 저장소 고유 식별자 | 저장소 고정 효과 (Repository Fixed Effect, $\mu_i$) |
| **`time`** | 관찰 대상 년월 | 시간 고정 효과 (Month Fixed Effect, $\lambda_t$) |
| **`event`** | Cursor 채택 월 | 처치 시점 (Treatment Timing, $E_i$) <br>

<br>※ `event == 0`은 끝까지 도입 안 한 대조군 |
| **`post_event`** | Cursor 도입 이후인지 여부 | 처치 기간 인디케이터 (Treated Period Indicator) |
| **`time_to_event`** | 도입 월 기준 상대적 시간 | 타임라인 상의 상대적 위치 ($h$) |
| `ncloc`, `age`, <br>

<br>`contributors`, `stars`, `issues` | 시간에 따라 변하는 <br>

<br>저장소의 실시간 상태 변수 | 시간 가변 공변량 세트 (Covariates, $Z_{it}$) |
| **Outcome Variables** | `lines_added`, `commits`, <br>

<br>`warnings`, `complexity` 등 | 실제 수집된 결과 지표 ($Y_{it}$) |

> ⚠️ **CRITICAL POINT:** 결과 지표인 $Y_{it}$는 수식에 의해 새로 연산되는 값이 아닙니다. 깃허브 및 소나큐브 로그에 이미 찍혀 있는 **'고정된 실제 관찰값'**입니다. (예: Repo A가 2025년 1월에 실제로 기록한 코드 추가량)

---

## 2. 전체 분석의 핵심 아이디어

Borusyak Imputation Estimator의 파이프라인은 다음과 같은 머신러닝 기반 인과추론 메커니즘을 따릅니다.

> 💡 **Core Concept:** Cursor의 오염이 전혀 없는 데이터만 사용하여 **"AI가 없는 청정 세계의 정상 개발 패턴"**을 먼저 학습(Fit)시킵니다. 그 후, Cursor를 도입한 데이터에 대입하여 **"만약 얘네가 Cursor를 안 썼더라면 어땠을까?"**의 반사실(Counterfactual) 결과를 예측(Predict)한 뒤 실제 값과 칼같이 비교합니다.

$$Y_{it} - \hat{Y}_{it}(0)$$

* **$Y_{it}$ :** 현실 세계에서 관찰된 실제 Outcome 데이터
* **$\hat{Y}_{it}(0)$ :** 모델이 수학적으로 추론해 낸 "Cursor를 안 썼을 때"의 가상 예측 Outcome

---

## 3. Step 1: Cursor 영향이 없는 관측치 ($\Omega_0$) 식별

전체 데이터를 AI의 약발이 묻지 않은 청정 구역($\Omega_0$, Untreated)과 실제 사용 구역($\Omega_1$, Treated)으로 분할합니다.

$$\Omega_0 \longrightarrow \text{[ Treatment가 발생하지 않은 청정 구역 ]}$$

보내주신 정확한 로직에 따라, 데이터셋 전반에서 AI의 오염이 없는 깨끗한 관측치들을 골라내는 단계입니다.

* **Control Repository의 모든 기간:** 끝까지 Cursor를 쓰지 않은 순수 대조군 데이터 (`row.event == 0`)
* **Treated Repository의 Adoption 이전 기간:** Cursor를 도입하기 전의 깨끗한 과거 데이터 (`row.time < row.event`)

```python
# Step 1. Identify untreated observations Ω0
for row in dataset:
    if row.event == 0:
        # Never-treated repository
        row.is_untreated = True
    elif row.time < row.event:
        # Treated repository, but before Cursor adoption
        row.is_untreated = True
    else:
        # Treated repository after Cursor adoption
        row.is_untreated = False

```

| 저장소 유형 (Repo Type) | 관찰 기간 (Month) | 수식상 영역 | `row.is_untreated` 라벨링 | Equation 4 학습(Fit) 투입 여부 |
| --- | --- | --- | --- | --- |
| **대조군 (Control Repo)** | 모든 개월 | $\Omega_0$ | **`True`** | **정상 패턴 학습에 사용 (O)** |
| **치료군 (Treated Repo)** | Cursor 도입 전 과거 | $\Omega_0$ | **`True`** | **정상 패턴 학습에 사용 (O)** |
| **치료군 (Treated Repo)** | Cursor 도입 후 미래 | $\Omega_1$ | **`False`** | 학습에서 배제 / **최종 예측 타깃 (X)** |

---

## 4. Step 2: Equation 4로 no-Cursor 패턴 적합 (Fit)

오직 청정 구역($\Omega_0$, `row.is_untreated == True`) 데이터만 사용하여, 저장소 고유 성격, 거시적 월별 흐름, 통제 변수들이 결과($Y$)에 미치는 자연스러운 가중치 패턴을 학습합니다.

$$\text{[Conceptually]} \quad Y_{it} = \mu_i + \lambda_t + \Gamma'Z_{it} + \epsilon_{it}$$

이 식은 프로그래밍의 대입 연산이 아니라, 이미 데이터에 존재하는 정답지 $Y_{it}$를 가장 잘 설명하도록 우변의 파라미터 계수들을 역추적하여 추정(Estimate)하는 회귀 모델 프로세스입니다.

실제 R 소스코드에서는 이 메커니즘이 고정 효과 파이프(`|`) 라인을 갖춘 **`did_imputation()`** 함수의 한 줄로 깔끔하게 가동됩니다.

```R
# In the actual R code this is handled by did_imputation():
first_stage = ~ age + ncloc + contributors + stars + issues | repo_name + time

```

* **`age + ncloc + contributors + stars + issues` $\rightarrow Z_{it}$ (공변량)**
* **`| repo_name + time` $\rightarrow \mu_i + \lambda_t$ (저장소 및 월 고정 효과)**

---

## 5. Step 3: Cursor Adoption 이후 행에 대한 반사실 예측 (Predict)

학습 단계에서 철저히 격리되었던 **실제 Cursor 사용 구역($\Omega_1$, `row.is_untreated == False`)** 데이터를 가져옵니다. 그리고 Step 2에서 훈련된 청정 가중치($\hat{\mu}, \hat{\lambda}, \hat{\Gamma}$)를 대입하여 "AI가 없었을 때의 예상 평상시 점수"를 머신러닝처럼 추론해 냅니다.

$$\hat{Y}_{it}(0) = \hat{\mu}_i + \hat{\lambda}_t + \hat{\Gamma}'Z_{it}$$

* **`Y_hat_it_without_cursor` $\big(\hat{Y}_{it}(0)\big)$** : "이 저장소가 이 달에 기여자가 몇 명이고 스타가 몇 개인지 상태를 보니, **AI가 없었으면 이 정도 결과가 나왔어야 정상**이다"라고 컴퓨터가 예측한 값입니다.

---

## 6. Step 4: 실제 결과와 반사실 예측값의 격차 비교

각 치료군 관측치에서 실제 찍힌 정답($Y_{it}$)과 모델이 예측한 가상 no-Cursor 예측치($\hat{Y}_{it}(0)$)를 빼기 연산하여 오직 AI로 인해 발생한 순수한 인과적 격차를 발라냅니다.

$$\text{effect}_{it} = Y_{it} - \hat{Y}_{it}(0)$$

### 📊 Lines Added(코드 추가량) 분석 시뮬레이션 예시

| 저장소 | 관찰 시점 | 실제 결과 ($Y_{it}$) | no-Cursor 예측치 ($\hat{Y}_{it}(0)$) | **추정된 순수 효과 ($\text{effect}_{it}$)** |
| --- | --- | --- | --- | --- |
| **Repo A** | 도입 당월 ($h=0$) | 500 줄 | 200 줄 | **+300 줄 (초기 속도 폭발)** |
| **Repo A** | 도입 1개월 후 ($h=1$) | 350 줄 | 230 줄 | **+120 줄 (효과 완화)** |
| **Repo B** | 도입 당월 ($h=0$) | 600 줄 | 400 줄 | **+200 줄 (생산성 향상)** |

---

## 7. Step 5: 효과들을 평균 내어 ATT 및 $ATT_h$ 도출

구해진 개별 인과적 격차(`effect_it`)들을 모아서 최종 평균 성적표를 계산합니다. 저자들은 코드에서 `horizon = -6:6` 파라미터를 주어 도입 전후의 흐름을 추적했습니다.

### 🎯 전체 평균 효과 (Overall ATT)

도입 이후 발생한 모든 치료군 저장소의 모든 달(`all treated post-adoption observations`)을 통째로 평균 낸 값입니다.


$$\text{ATT} = \text{average}(\text{effect}_{it})$$

### 📈 시간별 동적 효과 ($ATT_h$, Dynamic/Event-Study Effect)

도입월 기준으로 정확히 **$h$개월째**에 접어든 관측치들만 따로 그룹핑하여 평균을 낸 시계열 데이터입니다.


$$\text{ATT}_h = \text{average}(\text{effect}_{it} \text{ for observations } h \text{ months from adoption})$$

| 상대 시간 ($h$) | 실제 분석 타임라인 의미 | 연구진의 핵심 발견 연계 |
| --- | --- | --- |
| **$h = 0$** | Cursor Adoption Month (도입 당월) | 복사-붙여넣기 및 AI 생성 코드로 생산성 최대 증가 |
| **$h = 1$** | Adoption 1개월 후 | 효과가 유지되거나 서서히 감소하는 구간 |
| **$h = 2$** | Adoption 2개월 후 | 코드 복잡도 증가 및 디버깅 비용 누적 발생 |
| **$h = 3$** | Adoption 3개월 후 | 초기 가속 효과가 거의 0으로 수렴하며 사라지는 현상 검증 |

---

## 8. Equation 5의 역할: Pre-Trend Placebo Test (방어용 검증 모델)

Equation 5는 효과를 구하는 식이 아닙니다. 분석 결과가 통계적 꼬투리를 잡히지 않도록 대전제인 **평행 추세 가정을 검증하는 방패**입니다.

$$Y_{it} = \hat{\mu}_i + \hat{\lambda}_t + \hat{\Gamma}'Z_{it} + \mathbf{\sum_{h=-k}^{-2}\hat{\tau}_h 1[t=E_i+h]} + \epsilon_{it}$$

현미경 검문 대상은 바로 과거 구역에 심어놓은 가짜 마네킹 효과인 **$\hat{\tau}_h$** 입니다. 코드의 `pretrends = -6:-2` 파라미터가 이를 담당합니다.

| 상대 시간 ($h$) | 타임라인 의미 | 청정 구역 이상적인 기대치 |
| --- | --- | --- |
| **$h = -6$** | Cursor 도입 6개월 전 과거 격차 | $\hat{\tau}_{-6} \approx 0$ |
| **$h = -5$** | Cursor 도입 5개월 전 과거 격차 | $\hat{\tau}_{-5} \approx 0$ |
| **$h = -2$** | Cursor 도입 2개월 전 과거 격차 | $\hat{\tau}_{-2} \approx 0$ |

> ⚠️ **해석적 규칙:** AI를 쓰지도 않았던 먼 과거 구역($h < 0$)이므로, 가짜 효과인 $\hat{\tau}_h$ 값들은 **반드시 통계적으로 0에 수렴해야** 합격입니다. 만약 도입 전부터 이 값이 날뛰고 있다면 두 그룹은 애초에 비교 불가능한 성격의 저장소들이었음을 의미하므로 이후의 모든 인과적 주장이 파기됩니다. 저자들은 이 검증을 **`compute_wald()`** 함수를 통한 왈드 테스트로 돌파해 냈습니다.

---

## 📌 전체 구조 및 CS 핵심 직관 총정리

수학 기호에 감춰진 전체 파이프라인의 백엔드 흐름은 제출해주신 명확한 소스코드 구조와 정확히 1:1로 결합됩니다.

> 💡 **Summary:** **Equation 4 회귀 모델**은 Cursor 영향을 받지 않은 청정 데이터(대조군의 전 기간 + 치료군의 도입 전 과거 기간, $\Omega_0$)만 사용하여 'AI가 없는 세계의 정상 개발 패턴'을 **`did_imputation()`** 함수의 `first_stage`로 핏(Fit)하고, Cursor 도입 이후 데이터($\Omega_1$)를 들이받아 반사실적 가상 결과 $\hat{Y}_{it}(0)$를 예측(Predict)합니다. 이후 실제 관찰값 $Y_{it}$와 예측값의 차이인 `effect_it`를 평균 내어 최종 타깃 지표인 전체 ATT와 시간별 처치 효과($ATT_h$)를 정밀하게 추정해 냅니다.