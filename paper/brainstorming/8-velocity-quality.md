**Table 3(a). Main temporal paths between development velocity and software quality.**

| Tested Path                    | Main Effect $\hat{\gamma}$ | Evidence? |
| ------------------------------ | -------------------------- | --------- |
| $L_{it} \rightarrow W_{it}$    | not significant            | No        |
| $L_{it} \rightarrow C_{it}$    | not significant            | No        |
| $C_{it} \rightarrow L_{i,t+1}$ | negative, significant      | Yes       |
| $W_{it} \rightarrow L_{i,t+1}$ | negative, significant      | Yes       |

*Note.* This table summarizes the main temporal paths tested using Equation 6 and Equation 7. $L$, $W$, and $C$ denote Lines Added, Static Analysis Warnings, and Code Complexity, respectively.

---

**Table 3(b). Selected controls from the dynamic panel GMM models.**

| Model                          | Cursor Adoption $D_{it}$ | Total Lines of Code   |
| ------------------------------ | ------------------------ | --------------------- |
| $L_{it} \rightarrow W_{it}$    | not significant          | positive, significant |
| $L_{it} \rightarrow C_{it}$    | positive, significant    | positive, significant |
| $C_{it} \rightarrow L_{i,t+1}$ | positive, significant    | positive, significant |
| $W_{it} \rightarrow L_{i,t+1}$ | positive, significant    | positive, significant |

*Note.* “Total Lines of Code” is a codebase-size control variable included in $Z_{it}$ in Equation 6. It is not the same as $L_{it}$, which denotes Lines Added during month $t$.


---
---
---

I agree with your concern. **Table 3에 있는 숫자와 본문 문장은 일관되지 않아 보입니다.**

Table 3의 마지막 두 모델에서 main effect는 다음입니다.

| 관계                                               | Table 3 coefficient |
| ------------------------------------------------- | ------------------: |
| Code Complexity → next-month Lines Added          |            (-0.718) |
| Static Analysis Warnings → next-month Lines Added |            (-0.588) |

논문은 Table 3에서 이 값을 바탕으로 “complexity와 warnings가 100% 증가하면 lines added가 각각 64.5%, 50.3% 감소한다”고 설명합니다. 

그런데 Table 3의 coefficient를 일반적인 log-scale percentage 변환으로 바꾸면:

[
100 \times (e^{-0.718} - 1) \approx -51.2%
]

[
100 \times (e^{-0.588} - 1) \approx -44.5%
]

즉, **Table 3와 일관되게 계산하면 약 51.2% 감소와 약 44.5% 감소**가 됩니다.

그래서 네 말처럼:

> “to be consistent with Table 3, the correct result for complexity should be about 51.2% decrease”

는 맞습니다.

다만 하나 더 엄밀하게 말하면, “100% increase”라는 표현도 조심해야 합니다. 만약 모든 변수가 log-transform 되어 있고, 정말로 “complexity가 100% 증가”, 즉 **두 배가 됨**을 의미한다면 계산은 보통 이렇게 해야 합니다.

[
100 \times (e^{\beta \log 2} - 1)
]

그러면:

[
100 \times (e^{-0.718 \log 2} - 1) \approx -39.2%
]

[
100 \times (e^{-0.588 \log 2} - 1) \approx -33.5%
]

즉 해석 방식에 따라 두 가지가 있습니다.

| 해석                                | Complexity effect | Warnings effect |
| --------------------------------- | ----------------: | --------------: |
| 1 log-unit increase로 해석           |    약 **51.2% 감소** |  약 **44.5% 감소** |
| 실제 100% increase, 즉 doubling으로 해석 |    약 **39.2% 감소** |  약 **33.5% 감소** |
| 논문 본문 값                           |      **64.5% 감소** |    **50.3% 감소** |

따라서 **본문의 64.5%와 50.3%는 Table 3의 (-0.718), (-0.588)에서 직접 나오지 않습니다.**
가장 안전한 표현은:

> There appears to be an inconsistency between the reported coefficients in Table 3 and the percentage interpretation in the text. Using the coefficients in Table 3, the corresponding percentage changes are approximately 51.2% and 44.5% decreases under the usual (100(e^\beta-1)) conversion. If “100% increase” is interpreted literally as doubling, the effects would be approximately 39.2% and 33.5% decreases.


---
---
---

좋습니다. 이 설명의 핵심은:

> Table 3에 보이는 (-0.718)을 그대로 percentage로 바꾸면 **64.5%가 안 나온다**.
> 그래서 아마 저자들은 Table 3의 raw coefficient가 아니라, **dynamic model의 long-run effect**를 사용한 것이다.

하나씩 아주 쉽게 보겠습니다.

---

# 1. Table 3에 보이는 값

Table 3의 마지막 두 모델은 다음입니다.

| Path                           | Table 3 Main Effect |
| ------------------------------ | ------------------: |
| $C_{it} \rightarrow L_{i,t+1}$ |            $-0.718$ |
| $W_{it} \rightarrow L_{i,t+1}$ |            $-0.588$ |

여기서:

* $C$ = Code Complexity
* $W$ = Static Analysis Warnings
* $L$ = Lines Added

즉 Table 3은:

> complexity와 warnings가 다음 달 lines added를 줄인다

는 방향을 보여줍니다. 

---

# 2. 그런데 (-0.718)을 바로 변환하면 64.5%가 안 나옴

보통 log-transformed outcome의 coefficient는 이렇게 percentage로 바꿉니다.

$$
100(e^b - 1)%
$$

감소율로 보면:

$$
1 - e^b
$$

입니다.

그래서 (-0.718)을 넣으면:

$$
1 - e^{-0.718}
$$

$$
= 1 - 0.488
$$

$$
= 0.512
$$

즉:

$$
51.2%
$$

입니다.

그런데 논문 본문은 **64.5% decrease**라고 말합니다. 

그래서 질문이 생깁니다.

> 왜 Table 3의 (-0.718)에서 64.5%가 바로 안 나오지?

맞습니다. 바로 안 나옵니다.

---

# 3. 핵심 이유: Equation 6에는 지난달 $Y$가 들어감

Equation 6에는 이 항이 있습니다.

$$
\hat{\rho}Y_{i,t-1}
$$

이게 매우 중요합니다.

뜻은:

> 이번 달 outcome은 지난달 outcome의 영향을 받는다.

예를 들어 lines added를 설명한다면:

> 이번 달 lines added는 지난달 lines added의 영향을 받는다.

즉, effect가 한 번만 생기고 끝나는 게 아니라, 다음 달, 그 다음 달로 일부 이어질 수 있습니다.

---

# 4. Short-run effect vs Long-run effect

Table 3에 보이는 (-0.718)은 보통 **short-run coefficient**처럼 볼 수 있습니다.

즉:

> complexity가 lines added에 미치는 직접적인 한 번의 효과

입니다.

하지만 dynamic model에서는 효과가 이렇게 이어집니다.

```text
Complexity increases
        ↓
Next-month Lines Added decreases
        ↓
Because Lines Added has persistence, that decrease carries forward
        ↓
Later Lines Added also affected
```

그래서 전체 효과는 short-run coefficient보다 커질 수 있습니다.

이를 **long-run effect** 또는 **steady-state effect**라고 생각하면 됩니다.

---

# 5. Long-run effect 계산 아이디어

dynamic model에서 long-run effect는 보통 이렇게 계산합니다.

$$
\text{Long-run effect}
======================

\frac{\gamma}{1-\rho}
$$

여기서:

* $\gamma$ = Table 3의 main effect
* $\rho$ = lagged dependent variable, 즉 $Y_{i,t-1}$의 coefficient

문제는 Table 3에 $\rho$가 안 나와 있습니다.

Table 3 caption도 일부 covariate estimates는 생략했다고 말합니다. 

그래서 우리는 정확한 $\rho$를 표에서 직접 볼 수 없습니다.

---

# 6. 64.5%가 나오려면 어떤 coefficient가 필요할까?

64.5% decrease는 남는 비율이:

$$
1 - 0.645 = 0.355
$$

입니다.

이걸 log coefficient로 바꾸면:

$$
\log(0.355) \approx -1.036
$$

즉, 64.5% 감소가 나오려면 coefficient가 대략:

$$
-1.036
$$

이어야 합니다.

그런데 Table 3에는:

$$
-0.718
$$

이 있습니다.

따라서 설명은:

> 저자들이 (-0.718) raw coefficient가 아니라, long-run coefficient 약 (-1.036)을 사용했을 가능성이 높다.

입니다.

---

# 7. 어떻게 (-0.718)에서 (-1.036)으로 가나?

long-run formula를 사용합니다.

$$
\frac{-0.718}{1-\rho} = -1.036
$$

이걸 풀면:

$$
1-\rho = \frac{0.718}{1.036}
$$

$$
1-\rho \approx 0.693
$$

$$
\rho \approx 0.307
$$

즉 lagged lines added coefficient $\rho$가 약 0.31이면:

$$
\frac{-0.718}{1-0.31}
\approx
-1.036
$$

그리고:

$$
1 - e^{-1.036}
==============

64.5%
$$

가 됩니다.

---

# 8. Warnings도 같은 방식

Warnings path는 Table 3 coefficient가:

$$
-0.588
$$

논문 본문은 50.3% decrease라고 말합니다.

50.3% decrease는 남는 비율이:

$$
1 - 0.503 = 0.497
$$

그래서 필요한 log coefficient는:

$$
\log(0.497) \approx -0.70
$$

즉 long-run coefficient가 약:

$$
-0.70
$$

이어야 합니다.

그러면:

$$
1 - e^{-0.70}
\approx
50.3%
$$

입니다.

이걸 long-run formula로 보면:

$$
\frac{-0.588}{1-\rho} = -0.70
$$

$$
1-\rho = \frac{0.588}{0.70}
$$

$$
\rho \approx 0.16
$$

즉 warnings model에서는 $\rho$가 약 0.16이면 논문 숫자와 맞습니다.

---

# 9. 더 쉽게 비유하면

Table 3의 (-0.718)은 이런 느낌입니다.

> complexity가 올라가면 바로 다음 달 lines added가 줄어드는 1차 충격

그런데 Equation 6은 지난달 outcome도 이번 달 outcome에 영향을 준다고 봅니다.

그래서 1차 충격이 끝나지 않고 일부 남습니다.

```text
1차 감소: -0.718
       ↓
다음 기간에 일부 남음
       ↓
그 다음에도 일부 남음
       ↓
총합은 -1.036 정도가 됨
```

그래서 본문 percentage는 raw coefficient가 아니라 누적된 long-run effect를 사용한 것으로 보입니다.

---

# 10. Cross-check: 3x, 5x도 이 설명과 맞음

논문은 또 이렇게 말합니다.

> Cursor velocity gain would be cancelled out by about 5x increase in warnings or 3x increase in complexity. 

Cursor coefficient는 Table 3에서 약:

$$
1.044
$$

입니다.

이 값은:

$$
e^{1.044} - 1 \approx 1.84
$$

즉 baseline보다 184% 증가, 또는 1.84x increase입니다.

이제 이 gain을 complexity long-run effect가 상쇄하려면:

$$
\text{needed increase}
\approx
e^{1.046 / 1.036}
$$

$$
\approx 2.7x
$$

즉 약 3x입니다.

Warnings는:

$$
e^{1.046 / 0.70}
$$

$$
\approx 4.5x
$$

즉 약 5x입니다.

그래서 64.5%, 50.3%, 3x, 5x는 모두 **long-run effect를 썼다고 보면 서로 잘 맞습니다.**

---

# 11. 중요한 caveat

하지만 여기서 중요한 주의점이 있습니다.

논문 본문은 이 계산 과정을 명확히 보여주지 않습니다.

특히 Table 3에는 $\rho$가 없습니다.

그래서 독자가 Table 3만 보고:

$$
-0.718 \rightarrow 64.5%
$$

를 바로 재현할 수 없습니다.

더 정확히 말하면:

> 64.5%와 50.3%는 Table 3의 visible main effect coefficient를 단순 변환한 값이 아니라, 생략된 lagged dependent variable coefficient $\rho$까지 고려한 long-run effect로 보아야 자연스럽게 설명됩니다.

---

# 12. 또 하나의 조심할 점: “100% increase”

여기도 약간 애매합니다.

일반적으로 “100% increase”는 두 배 증가, 즉:

$$
X \rightarrow 2X
$$

를 의미합니다.

하지만 위 계산에서 64.5%와 50.3%는 사실상 **one-log-unit increase**에 가까운 해석입니다.

one-log-unit increase는:

$$
\Delta \log X = 1
$$

이고, 이는 원래 값이:

$$
e^1 \approx 2.718
$$

배가 되는 것입니다.

즉 엄밀하게는 100% increase, 즉 2배 증가와 완전히 같지는 않습니다.

그래서 이 부분도 논문에서 더 명확히 설명했으면 좋았을 부분입니다.

---

# 최종 요약

아주 쉽게 정리하면:

1. Table 3에 보이는 (-0.718)을 바로 변환하면 **51.2%**이지, **64.5%**가 아닙니다.
2. 64.5%가 나오려면 coefficient가 약 (-1.036)이어야 합니다.
3. (-1.036)은 Equation 6의 lagged outcome term, 즉 $\rho Y_{i,t-1}$을 고려한 **long-run effect**로 설명할 수 있습니다.
4. 공식은 대략:

$$
\text{Long-run effect}
======================

\frac{\gamma}{1-\rho}
$$

5. Table 3에는 $\rho$가 생략되어 있어서, 독자가 직접 계산하기는 어렵습니다.
6. 따라서 이 문단은 방향성은 이해 가능하지만, percentage conversion은 더 명시적으로 설명했어야 합니다.



---
---
---
---
---
---
---

좋습니다. 이 설명은 핵심적으로 이렇게 말합니다:

> **처음에는 64.5%와 50.3%가 long-run elasticity에서 나온다고 생각했지만, 실제 코드를 돌려보니 그 설명은 틀렸다.**
> **Table 3의 계수와 논문 본문의 percentage 숫자가 서로 잘 맞지 않는다.**

쉽게 단계별로 보겠습니다.

---

## 1. 먼저 Table 3의 실제 계수는 맞게 재현됨

Table 3의 마지막 두 모델은 이것입니다.

| Path                           | Table 3 coefficient |
| ------------------------------ | ------------------: |
| $C_{it} \rightarrow L_{i,t+1}$ |            $-0.718$ |
| $W_{it} \rightarrow L_{i,t+1}$ |            $-0.588$ |

여기서:

* $C$ = Code Complexity
* $W$ = Static Analysis Warnings
* $L$ = Lines Added

즉 Table 3은:

> complexity와 warnings가 높으면 다음 달 lines added가 감소한다

는 결과를 보여줍니다. 

제공하신 설명에서는 실제 R 모델을 다시 돌려도 이 값들이 거의 그대로 나왔다고 합니다.

* complexity model: $\gamma = -0.7185$
* warnings model: $\gamma = -0.5880$

즉 **Table 3 자체는 데이터와 코드로 재현됨**입니다.

---

## 2. 문제는 논문 본문의 64.5%, 50.3%

논문 본문은 이렇게 말합니다.

> complexity가 100% 증가하면 lines added가 64.5% 감소
> warnings가 100% 증가하면 lines added가 50.3% 감소

하지만 Table 3 계수를 보통 방식으로 바꾸면 이 숫자가 안 나옵니다.

### Complexity

$$
1 - e^{-0.718}
$$

$$
= 1 - 0.488
$$

$$
= 0.512
$$

즉:

$$
51.2%
$$

입니다.

64.5%가 아닙니다.

### Warnings

$$
1 - e^{-0.588}
$$

$$
= 1 - 0.555
$$

$$
= 0.445
$$

즉:

$$
44.5%
$$

입니다.

50.3%가 아닙니다.

그래서 결론:

> Table 3의 visible coefficient를 단순 변환하면 논문 본문의 64.5%, 50.3%가 나오지 않는다.

---

## 3. 이전 가설: long-run effect일 수도 있다

처음에는 이렇게 생각할 수 있었습니다.

Equation 6에는 lagged outcome이 있습니다.

$$
\rho Y_{i,t-1}
$$

그래서 short-run effect가 아니라 long-run effect를 썼을 수도 있습니다.

long-run effect 공식은 보통:

$$
\frac{\gamma}{1-\rho}
$$

입니다.

즉:

> Table 3의 $\gamma$를 그대로 쓰지 않고, 지난달 outcome persistence $\rho$까지 고려했을 수 있다.

이 설명이 맞으려면 $\rho$가 꽤 커야 했습니다.

64.5%가 나오려면 complexity 쪽 long-run coefficient가 약:

$$
-1.036
$$

이어야 합니다.

그래서:

$$
\frac{-0.718}{1-\rho} = -1.036
$$

가 되어야 하고, 이 경우 $\rho \approx 0.31$ 정도가 필요합니다.

---

## 4. 그런데 실제 $\rho$는 약 0.10이었다

제공하신 설명에 따르면 실제 R 모델을 돌려보니:

| Model            |       $\rho$ |
| ---------------- | -----------: |
| complexity model | about 0.0999 |
| warnings model   | about 0.1011 |

즉 $\rho$가 약 0.10입니다.

생각보다 작습니다.

그래서 long-run effect를 계산해도:

### Complexity

$$
\frac{-0.718}{1-0.10}
$$

$$
\approx -0.798
$$

이를 percentage로 바꾸면:

$$
1 - e^{-0.798}
$$

$$
\approx 55.0%
$$

### Warnings

$$
\frac{-0.588}{1-0.10}
$$

$$
\approx -0.654
$$

이를 percentage로 바꾸면:

$$
1 - e^{-0.654}
$$

$$
\approx 48.0%
$$

여전히 논문의 64.5%, 50.3%와 맞지 않습니다.

---

## 5. 그래서 이전 long-run explanation은 틀림

정리하면:

| Method                                 | Complexity decrease | Warnings decrease |
| -------------------------------------- | ------------------: | ----------------: |
| Short-run coefficient                  |               51.2% |             44.5% |
| Long-run with real $\rho \approx 0.10$ |               55.0% |             48.0% |
| Paper prose                            |               64.5% |             50.3% |

즉:

> 실제 모델의 short-run effect도 아니고, 실제 $\rho$를 반영한 long-run effect도 아니다.

그래서 제공하신 설명은 이렇게 말하는 것입니다.

> 내가 처음에 추측했던 “long-run elasticity 때문에 64.5%가 나온다”는 설명은 실제 모델을 돌려보니 틀렸다.

이건 매우 중요한 correction입니다.

---

## 6. 그럼 64.5%, 50.3%는 어디서 온 것 같나?

제공하신 설명의 결론은:

> 아마 논문 본문 숫자가 이전 모델이나 이전 데이터 버전에서 온 것일 수 있다.
> 또는 단순 계산 실수일 수 있다.

왜냐하면 64.5%가 나오려면 coefficient가 대략:

$$
-1.04
$$

이어야 합니다.

50.3%가 나오려면 coefficient가 대략:

$$
-0.70
$$

이어야 합니다.

그런데 실제 Table 3과 재현 모델에서는:

$$
-0.718,\quad -0.588
$$

입니다.

즉 본문 숫자와 표 숫자가 서로 다른 모델을 보고 있는 것처럼 보입니다.

---

## 7. 그래도 qualitative conclusion은 유지됨

중요한 점은 이것입니다.

숫자 64.5%, 50.3%는 의심스럽지만, 방향 자체는 여전히 같습니다.

Table 3의 계수는 둘 다 음수입니다.

| Path                           | Coefficient | Meaning                               |
| ------------------------------ | ----------: | ------------------------------------- |
| $C_{it} \rightarrow L_{i,t+1}$ |    negative | complexity가 높으면 future lines added 감소 |
| $W_{it} \rightarrow L_{i,t+1}$ |    negative | warnings가 많으면 future lines added 감소   |

즉 강한 결론은 여전히:

> technical debt가 미래 개발 속도를 낮춘다

입니다.

하지만 정확한 percentage로는:

> 64.5%, 50.3%라고 단정하기 어렵다

입니다.

---

## 8. cancellation multiplier도 다시 봐야 함

논문은 또 이렇게 말합니다.

> Cursor velocity gain은 complexity 약 3x 증가 또는 warnings 약 5x 증가로 상쇄될 수 있다.

제공하신 설명에 따르면, 3x와 5x는 논문 본문의 64.5%, 50.3% 숫자와는 내부적으로 맞습니다.

하지만 실제 coefficient로 다시 계산하면 조금 달라집니다.

실제 long-run values를 쓰면:

* complexity: 약 $-0.798$
* warnings: 약 $-0.654$

Cursor gain은 약:

$$
1.044
$$

그러면 cancellation point는 대략:

### Complexity

$$
e^{1.044/0.798}
$$

$$
\approx 3.7x
$$

### Warnings

$$
e^{1.044/0.654}
$$

$$
\approx 5.0x
$$

즉 실제 모델 기준으로는:

| Variable                | Paper prose | Based on reproduced model |
| ----------------------- | ----------: | ------------------------: |
| Complexity cancellation |   $\sim 3x$ |     closer to $\sim 3.7x$ |
| Warnings cancellation   |   $\sim 5x$ |     closer to $\sim 5.0x$ |

Warnings 쪽은 거의 맞지만, complexity 쪽은 차이가 있습니다.

---

## 9. 아주 쉽게 한 문장으로

이 설명의 핵심은:

> Table 3의 회귀계수는 재현되지만, 논문 본문에 적힌 64.5%와 50.3%는 그 계수에서 표준적인 방식으로 계산되지 않는다. 따라서 방향성은 맞지만, 본문의 구체적인 percentage 숫자는 이전 버전의 결과가 남았거나 계산 실수일 가능성이 있다.

---

## 10. 우리가 지금 이해해야 할 최종 버전

가장 안전한 해석은 이렇게 하면 됩니다.

> Table 3은 complexity와 warnings가 future lines added를 감소시킨다는 evidence를 제공한다. 하지만 본문에 제시된 “64.5%”와 “50.3%” 감소율은 Table 3의 최종 계수와 replication result로부터 직접 재현되지 않는다. 따라서 이 percentage 값들은 조심해서 해석해야 하며, 저자에게 계산 방식 또는 버전 불일치 여부를 확인할 필요가 있다.

쉽게 말하면:

> **방향은 믿을 수 있다: technical debt가 future velocity를 낮춘다.**
> **하지만 정확한 숫자 64.5%, 50.3%는 paper 안에서 투명하게 설명되지 않고, 최종 Table 3과 잘 안 맞는다.**

