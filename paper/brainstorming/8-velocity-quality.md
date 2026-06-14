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
