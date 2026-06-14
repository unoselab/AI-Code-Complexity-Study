Equation 1은 **control group을 고르기 위한 propensity score matching model**입니다.

핵심부터 말하면:

> Equation 1은 “이 repository가 Cursor를 도입할 가능성이 얼마나 되는가?”를 추정하는 모델입니다.

즉, 이 식은 Cursor가 outcome에 미친 효과를 직접 추정하는 식이 아닙니다.
이 식의 목적은:

> Cursor를 실제로 도입한 repository와, Cursor를 도입할 가능성은 비슷했지만 실제로는 도입하지 않은 repository를 매칭하기 위한 사전 단계

입니다.

---

## 1. Equation 1 전체

논문에서 제시한 Equation 1은 다음과 같습니다.

$$
\log \frac{P(\text{treat} \mid \cdots)}
{1-P(\text{treat} \mid \cdots)}
=

\alpha
+
\beta T_{i,t-1}
+
\sum_{j=1}^{6}\Gamma_j X_{i,t-j}
+
\Theta \sum_{j=7}^{\infty} X_{i,t-j}
+
\epsilon_i
$$

이 식은 assignment statement가 아닙니다.

즉, 프로그래밍에서의:

```python
probability = ...
```

처럼 단순히 오른쪽 값을 계산해서 왼쪽 변수에 저장한다는 뜻이 아닙니다.

더 정확히는:

> repository의 과거 활동 데이터와 age를 사용해서 Cursor adoption probability를 추정하는 propensity score model을 fit한다.

입니다.

---

## 2. Equation 1이 예측하는 것

Equation 1이 최종적으로 예측하는 값은 다음입니다.

$$
P(\text{treat} \mid t, T_i, X_i)
$$

뜻은:

> repository $i$가 특정 adoption month $t$에 Cursor를 도입할 확률

입니다.

이 확률을 **propensity score**라고 부릅니다.

예를 들어:

| Repo   | 실제 Cursor 도입? | Propensity score |
| ------ | ------------: | ---------------: |
| Repo A |           Yes |            0.084 |
| Repo B |            No |            0.081 |
| Repo C |            No |            0.079 |
| Repo D |            No |            0.003 |

Repo A가 실제 Cursor adopter라면, control 후보 중에서는 Repo B나 Repo C가 좋은 match입니다.

왜냐하면:

> Repo B와 Repo C는 Cursor를 도입하지 않았지만, 과거 활동 패턴상 Cursor를 도입할 가능성은 Repo A와 비슷했기 때문입니다.

반대로 Repo D는 propensity score가 너무 낮기 때문에 Repo A와 비교하기에 덜 적절합니다.

---

## 3. 왜 이런 모델이 필요한가?

그냥 random control repo를 고르면 문제가 생깁니다.

Cursor를 도입한 repo들은 보통 random repo보다:

* 더 active할 수 있음
* 더 빠르게 성장 중일 수 있음
* stars, forks, issues, PRs가 많을 수 있음
* contributors가 많을 수 있음
* 새로운 개발 도구를 더 적극적으로 받아들이는 팀일 수 있음

예를 들어:

| Repo   | Cursor adoption | Activity pattern |
| ------ | --------------- | ---------------- |
| Repo A | Yes             | 빠르게 성장 중         |
| Repo B | No              | 거의 비활성           |

이 둘을 비교하면, Cursor 효과가 아니라 **원래 성장 차이**를 Cursor 효과로 착각할 수 있습니다.

그래서 Equation 1은 먼저 이런 질문에 답합니다.

> Cursor adopter와 비슷한 과거 활동 패턴을 가진 non-Cursor repo는 누구인가?

---

## 4. 왼쪽: log odds

왼쪽은 다음과 같습니다.

$$
\log \frac{P(\text{treat} \mid \cdots)}
{1-P(\text{treat} \mid \cdots)}
$$

여기서 $P(\text{treat})$는 Cursor를 도입할 확률입니다.

예를 들어:

$$
P(\text{treat}) = 0.8
$$

이면 Cursor를 도입할 가능성이 80%라는 뜻입니다.

반대로:

$$
1 - P(\text{treat}) = 0.2
$$

는 Cursor를 도입하지 않을 가능성이 20%라는 뜻입니다.

odds는 다음입니다.

$$
\frac{P(\text{treat})}{1-P(\text{treat})}
$$

예를 들어:

$$
\frac{0.8}{0.2} = 4
$$

이면:

> 도입할 가능성이 도입하지 않을 가능성보다 4배 높다

는 뜻입니다.

log odds는 odds에 log를 씌운 것입니다.

$$
\log \frac{P(\text{treat})}{1-P(\text{treat})}
$$

logistic regression은 확률을 직접 linear model로 다루지 않고, 이 log odds를 linear model로 설명합니다.

쉽게 말하면:

> 왼쪽은 “Cursor adoption 가능성”을 regression이 다루기 쉬운 형태로 변환한 값입니다.

---

## 5. 오른쪽: repository의 과거 상태와 활동 패턴

오른쪽은 다음과 같습니다.

$$
\alpha
+
\beta T_{i,t-1}
+
\sum_{j=1}^{6}\Gamma_j X_{i,t-j}
+
\Theta \sum_{j=7}^{\infty} X_{i,t-j}
+
\epsilon_i
$$

쉽게 말하면 Equation 1은 이렇게 말합니다.

> Cursor adoption 가능성은 repository age, 최근 6개월 활동 trajectory, 그리고 더 오래된 누적 활동 baseline으로 설명될 수 있다.

---

## 6. $T_{i,t-1}$: repository maturity

$$
T_{i,t-1}
$$

는 repository $i$의 adoption 직전 시점 $t-1$에서의 나이입니다.

실제 코드에서는 이 값이 `age_days`로 구현됩니다.

제공된 코드에서는 각 repository에 대해 가장 최근 `within` period를 찾고, 그 시점의 `age_days`를 feature로 가져옵니다.

```python
latest_period_df = (
    combined_df[combined_df["period_type"] == "within"]
    .groupby("repo_name")["period"]
    .max()
    .reset_index()
)

latest_age_df = combined_df.merge(
    latest_period_df, on=["repo_name", "period"]
)[["repo_name", "age_days"]].drop_duplicates()
```

즉, 코드에서:

```python
age_days
```

는 논문의 $T_{i,t-1}$, 즉 repository maturity에 해당합니다.

왜 중요할까요?

오래된 repo와 신생 repo는 Cursor adoption pattern이 다를 수 있기 때문입니다.

| Repo type  | Possible behavior                       |
| ---------- | --------------------------------------- |
| 오래된 repo   | 기존 workflow가 안정되어 있어 새 도구 도입이 느릴 수 있음   |
| 신생 repo    | 새 도구를 더 쉽게 받아들일 수 있음                    |
| 성장 중인 repo | productivity tool adoption 가능성이 높을 수 있음 |

---

## 7. $X_{i,t-j}$: repository activity covariates

$$
X_{i,t-j}
$$

는 repository $i$의 $t-j$개월 전 활동 변수들입니다.

실제 코드에서 사용되는 activity features는 다음입니다.

```python
feature_list = [
    "users_involved",
    "n_stars",
    "n_forks",
    "n_releases",
    "n_pulls",
    "n_issues",
    "n_comments",
    "total_events",
]
```

논문 수식의 $X$는 이 변수들의 묶음이라고 보면 됩니다.

즉:

| Code feature     | Meaning                   |
| ---------------- | ------------------------- |
| `users_involved` | 활동에 참여한 사용자 수             |
| `n_stars`        | stars 수                   |
| `n_forks`        | forks 수                   |
| `n_releases`     | releases 수                |
| `n_pulls`        | pull requests 수           |
| `n_issues`       | issues 수                  |
| `n_comments`     | comments 수                |
| `total_events`   | 전체 GitHub activity events |

---

## 8. 최근 6개월 dynamics

Equation 1의 이 부분은 최근 6개월의 활동 trajectory를 반영합니다.

$$
\sum_{j=1}^{6}\Gamma_j X_{i,t-j}
$$

즉:

|      $j$ | Meaning              |
| -------: | -------------------- |
|    $j=1$ | adoption 기준 1개월 전 활동 |
|    $j=2$ | adoption 기준 2개월 전 활동 |
|    $j=3$ | adoption 기준 3개월 전 활동 |
| $\cdots$ | $\cdots$             |
|    $j=6$ | adoption 기준 6개월 전 활동 |

실제 코드에서는 `period_type == "within"`인 rows를 pivot해서, 각 metric의 월별 column을 만듭니다.

```python
monthly_pivot = combined_df[
    combined_df["period_type"] == "within"
].pivot(
    index="repo_name",
    columns="period",
    values=metric
)

monthly_pivot.columns = [
    f"{metric}_{col}" for col in monthly_pivot.columns
]
```

예를 들어 `n_pulls`에 대해 다음과 같은 feature들이 만들어질 수 있습니다.

```text
n_pulls_1
n_pulls_2
n_pulls_3
n_pulls_4
n_pulls_5
n_pulls_6
```

이것이 논문 수식의 최근 6개월 lag features에 대응합니다.

왜 최근 6개월을 따로 보느냐가 중요합니다.

현재 활동량이 같은 두 repo라도 trajectory는 다를 수 있습니다.

| Month   | Repo A PRs | Repo B PRs |
| ------- | ---------: | ---------: |
| 2024-02 |         20 |        180 |
| 2024-03 |         40 |        160 |
| 2024-04 |         60 |        140 |
| 2024-05 |         80 |        120 |
| 2024-06 |         90 |        110 |
| 2024-07 |        100 |        100 |

현재 PR 수는 둘 다 100입니다.

하지만:

| Repo   | Pattern |
| ------ | ------- |
| Repo A | 성장 중    |
| Repo B | 감소 중    |

Cursor adoption 가능성은 단순한 현재 활동량뿐 아니라 이런 성장/감소 trajectory와도 관련 있을 수 있습니다.

그래서 최근 6개월 lag를 feature로 넣습니다.

---

## 9. Historical baseline: 오래된 누적 이력

Equation 1의 이 부분은 최근 6개월보다 더 오래된 누적 활동 이력을 의미합니다.

$$
\Theta \sum_{j=7}^{\infty} X_{i,t-j}
$$

실제 코드에서는 `period_type == "sum"`인 row를 사용해 각 metric의 누적값을 feature로 추가합니다.

```python
sum_metrics = combined_df[
    combined_df["period_type"] == "sum"
].set_index("repo_name")[metric]

sum_metrics.name = f"{metric}_sum"
```

예를 들어 다음과 같은 column이 만들어질 수 있습니다.

```text
n_pulls_sum
n_issues_sum
n_stars_sum
total_events_sum
```

이것이 논문의 historical baseline에 해당합니다.

쉽게 말하면:

> 최근 6개월의 trend뿐 아니라, 그 이전까지 이 repo가 전체적으로 얼마나 큰 프로젝트였는지도 반영한다.

예를 들어:

| Repo   | 최근 6개월    | 과거 전체 history |
| ------ | --------- | ------------- |
| Repo A | 최근 빠르게 성장 | 오래된 대형 프로젝트   |
| Repo B | 최근 빠르게 성장 | 신생 소형 프로젝트    |

둘 다 최근 성장세는 비슷해도 project scale은 다릅니다.

그래서 오래된 누적 activity baseline이 필요합니다.

---

## 10. 실제 코드 흐름 요약

제공된 `compute_propensity_scores()` 함수는 Equation 1의 아이디어를 다음 순서로 구현합니다.

### Step 1. Treatment/control label 만들기

```python
treatment_df["treatment"] = 1
control_df["treatment"] = 0
combined_df = pd.concat([treatment_df, control_df], ignore_index=True)
```

여기서 label은 다음입니다.

| Repository type        | `treatment` |
| ---------------------- | ----------: |
| Cursor adopter         |           1 |
| Candidate control repo |           0 |

즉, 모델은:

> 이 repo가 treatment group에 속하는가?

를 예측하도록 학습됩니다.

---

### Step 2. Repository age feature 만들기

각 repo에 대해 가장 최근 `within` period의 `age_days`를 가져옵니다.

이 값은 논문의 $T_{i,t-1}$에 대응합니다.

---

### Step 3. Activity features 만들기

코드는 8개 activity metrics를 사용합니다.

```python
users_involved
n_stars
n_forks
n_releases
n_pulls
n_issues
n_comments
total_events
```

각 metric에 대해 두 종류의 feature를 만듭니다.

| Feature type            | Code source               | Equation 1 mapping                    |
| ----------------------- | ------------------------- | ------------------------------------- |
| 최근 monthly features     | `period_type == "within"` | $\sum_{j=1}^{6}\Gamma_j X_{i,t-j}$    |
| historical sum features | `period_type == "sum"`    | $\Theta \sum_{j=7}^{\infty}X_{i,t-j}$ |

---

### Step 4. Missing values를 0으로 채움

```python
features_df = features_df.fillna(0)
```

어떤 repo는 특정 기간에 events가 없을 수 있습니다.

그 경우 해당 metric을 0으로 처리합니다.

---

### Step 5. Feature scaling

```python
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)
```

여기서 모든 numeric feature를 normalize합니다.

왜냐하면 `age_days`, `total_events`, `n_stars`처럼 scale이 크게 다른 변수들이 같이 들어가기 때문입니다.

예를 들어:

| Feature          | Scale example |
| ---------------- | ------------: |
| `age_days`       |          1000 |
| `n_stars`        |         50000 |
| `n_releases`     |             3 |
| `users_involved` |            20 |

scale을 맞추지 않으면 큰 숫자를 가진 feature가 모델 학습에서 과도하게 영향을 줄 수 있습니다.

---

### Step 6. Propensity model fit

코드는 설정에 따라 두 모델 중 하나를 사용합니다.

```python
if USE_RANDOM_FOREST:
    model = RandomForestClassifier(random_state=42)
else:
    model = LogisticRegression(random_state=42)
```

논문의 Equation 1은 logistic regression 형태입니다.

따라서 Equation 1과 직접 대응되는 것은:

```python
model = LogisticRegression(random_state=42)
```

입니다.

다만 실제 구현은 `USE_RANDOM_FOREST` 설정이 켜져 있으면 Random Forest로도 propensity score를 계산할 수 있게 되어 있습니다.

그 후 모델을 fit합니다.

```python
model.fit(X_scaled, y)
```

여기서:

* `X_scaled`: repository age, 최근 monthly activity features, historical sum features
* `y`: Cursor adopter이면 1, control이면 0

입니다.

---

### Step 7. Model quality 확인

코드는 AUC를 계산합니다.

```python
auc_score = roc_auc_score(y, model.predict_proba(X_scaled)[:, 1])
```

AUC는 모델이 treatment repo와 control repo를 얼마나 잘 구분하는지 보여줍니다.

또한 logistic regression을 사용할 때는 McFadden’s pseudo $R^2$도 계산합니다.

```python
mcfadden_r2 = 1 - (ll_full / ll_null)
```

이 값은 logistic regression에서 모델 적합도를 보는 보조 지표입니다.

---

### Step 8. Propensity score 계산

마지막으로 각 repository에 대해 treatment probability를 계산합니다.

```python
propensity_scores = model.predict_proba(X_scaled)[:, 1]
features_df["propensity_score"] = propensity_scores
```

여기서:

```python
model.predict_proba(X_scaled)[:, 1]
```

은 각 repo가 treatment group, 즉 Cursor adopter일 확률을 의미합니다.

이 값이 바로 propensity score입니다.

$$
P(\text{treat} \mid t, T_i, X_i)
$$

---

### Step 9. 원래 데이터에 propensity score 붙이기

마지막으로 계산된 propensity score를 원래 combined dataframe에 merge합니다.

```python
result_df = combined_df.merge(
    features_df[["repo_name", "propensity_score"]],
    on="repo_name",
    how="left"
)
```

즉 최종 output은 각 repo-month row에 propensity score가 붙은 dataframe입니다.

---

## 11. 실제 구현을 반영한 CS-friendly pseudo-code

제공된 실제 코드를 더 간단히 요약하면 다음과 같습니다.

```python
def compute_propensity_scores(treatment_df, control_df):

    # 1. Label data
    treatment_df["treatment"] = 1
    control_df["treatment"] = 0
    combined_df = concat(treatment_df, control_df)

    # 2. Get repository age
    age_feature = latest_age_days_for_each_repo(combined_df)

    # 3. Build activity features
    for metric in [
        "users_involved",
        "n_stars",
        "n_forks",
        "n_releases",
        "n_pulls",
        "n_issues",
        "n_comments",
        "total_events",
    ]:
        monthly_features = pivot_monthly_values(
            combined_df,
            metric,
            period_type="within"
        )

        historical_sum_feature = get_sum_value(
            combined_df,
            metric,
            period_type="sum"
        )

        add_to_feature_table(monthly_features)
        add_to_feature_table(historical_sum_feature)

    # 4. Fill missing values
    features = fill_missing_values_with_zero(features)

    # 5. Split X and y
    X = features.drop(["repo_name", "treatment"])
    y = features["treatment"]

    # 6. Normalize features
    X_scaled = StandardScaler().fit_transform(X)

    # 7. Fit propensity model
    if USE_RANDOM_FOREST:
        model = RandomForestClassifier()
    else:
        model = LogisticRegression()

    model.fit(X_scaled, y)

    # 8. Predict treatment probability
    propensity_score = model.predict_proba(X_scaled)[:, 1]

    # 9. Attach score back to the original data
    return combined_df_with_propensity_score
```

---

## 12. Equation 1과 실제 코드의 매핑

| Equation 1 term                   | Meaning                          | Real code mapping                                              |
| --------------------------------- | -------------------------------- | -------------------------------------------------------------- |
| $P(\text{treat} \mid \cdots)$     | Cursor adoption probability      | `model.predict_proba(X_scaled)[:, 1]`                          |
| treatment label                   | whether repo adopted Cursor      | `treatment_df["treatment"] = 1`, `control_df["treatment"] = 0` |
| $T_{i,t-1}$                       | repository maturity              | `age_days`                                                     |
| $X_{i,t-j}$                       | monthly repo activity covariates | pivoted `period_type == "within"` metrics                      |
| $\sum_{j=1}^{6}\Gamma_jX_{i,t-j}$ | recent 6-month dynamics          | monthly pivot columns for each metric                          |
| $\sum_{j=7}^{\infty}X_{i,t-j}$    | historical baseline              | `period_type == "sum"` metrics                                 |
| logistic regression               | Equation 1 model                 | `LogisticRegression(random_state=42)`                          |
| optional alternative model        | implementation extension         | `RandomForestClassifier(random_state=42)`                      |
| propensity score                  | matching score                   | `features_df["propensity_score"]`                              |

---

## 13. Matching과의 연결

Equation 1 자체는 matching을 수행하지 않습니다.

Equation 1은 matching에 사용할 점수, 즉 propensity score를 만듭니다.

그 다음 단계에서 연구자는:

1. Cursor adopter repo의 propensity score를 본다.
2. never-treated control repo들의 propensity score를 본다.
3. score가 가까운 control repo를 고른다.
4. matched treatment/control sample로 DiD를 수행한다.

쉽게 말하면:

> Equation 1은 “비슷한 control을 찾기 위한 점수표”를 만드는 단계입니다.

---

## 14. Equation 1과 다른 수식들의 차이

| Equation   | Purpose                         | Predicts / estimates         |
| ---------- | ------------------------------- | ---------------------------- |
| Equation 1 | matching용 control group 만들기     | Cursor adoption probability  |
| Equation 3 | dynamic treatment effect 정의     | $ATT_h$                      |
| Equation 4 | DiD counterfactual outcome 예측   | $\hat{Y}_{it}(0)$            |
| Equation 5 | pre-trend placebo test          | pre-treatment $\hat{\tau}_h$ |
| Equation 6 | velocity-quality interaction 분석 | $\hat{\gamma}$               |

즉 Equation 1은 outcome을 예측하지 않습니다.

Equation 1은:

> 이 repository가 treatment group에 들어갈 가능성이 얼마나 되는가?

를 예측합니다.

---

## 15. 아주 쉬운 비유

학생들이 어떤 새 공부 앱을 사용할지 예측한다고 합시다.

새 공부 앱을 쓰는 학생들은 원래부터:

* 공부량이 많고
* 최근 성적이 오르고 있고
* 동아리 활동도 활발하고
* 새로운 도구에 관심이 많을 수 있습니다.

그럼 앱을 쓴 학생과 아무 학생이나 비교하면 불공정합니다.

그래서 먼저 이런 모델을 만듭니다.

> 이 학생이 새 공부 앱을 사용할 가능성은 얼마인가?

그다음 비교는 이렇게 합니다.

* 실제 앱을 쓴 학생
* 앱을 쓸 가능성은 비슷했지만 실제로는 안 쓴 학생

Equation 1이 바로 이 “앱을 쓸 가능성 점수”를 만드는 모델입니다.

---

## 16. 한 문장으로 최종 정리

Equation 1은:

> repository의 age, 최근 6개월 activity trajectory, 오래된 누적 activity baseline을 사용해 “이 repo가 Cursor를 도입할 가능성”, 즉 propensity score를 추정하는 model입니다.

실제 구현에서는 `age_days`, 월별 pivot activity features, historical sum features를 만들고, 이를 `StandardScaler`로 정규화한 뒤 `LogisticRegression` 또는 설정에 따라 `RandomForestClassifier`에 넣어 `predict_proba(... )[:, 1]`로 propensity score를 계산합니다.

그 목적은:

> Cursor adopter와 과거 활동 패턴이 비슷한 non-adopter control repositories를 골라서, 이후 DiD 분석이 더 공정해지도록 만드는 것입니다.
