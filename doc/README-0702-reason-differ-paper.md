## Daily Research Report

**Date:** 2026-07-02

**Project:** 2026 MSR Speed at the Cost of Quality Replication / JS-TS Analysis

---

## Objective

Today’s goal was to clarify why our `strict_1to3_unbalanced` results differ from the original paper, especially for the warning-subcategory and quality outcomes.

We focused on three related questions:

1. Whether the paper uses a strict 1:3 matching rule.
2. Whether our `strict_1to3_unbalanced` or `main_unbalanced` panel is closer to the paper.
3. Whether the difference between our result and the paper is caused by currently unavailable repositories during git cloning.

---

## What We Reviewed

We reviewed the paper again, especially:

```text
Section 3.1.3 Building a Control Group via Propensity Score Matching
Section 3.2 Metrics
Appendix C Figure 7
Appendix C Table 7
```

We also reviewed our run8 pipeline files:

```text
proc_scripts/filter_controls_by_local_cursor_evidence.py
run8d2-filter-local-cursor-controls.sh
run8e-build-jsts-matched-panel.sh
proc_scripts/prepare_panel_event_v2.py
```

We focused especially on how these files the paper uses a strict 1:3 matching rule.
2. Whether our `strict_1to3_unbalanced` or `main_unbalanced` panel is closer to the paper.
3. Whether the difference between our result and the paper is caused by currently unavailable repositories during git cloning.

---

## What We Reviewed

We reviewed the paper again, especially:

```text
Section 3.1.3 Building a Control Group via Propensity Score Matching
Section 3.2 Metrics
Appendix C Figure 7
Appendix C Table 7
```

We also reviewed our run8 pipeline files generate:

```text
main_unbalanced:
  panel_event_monthly_matched_final_clean.csv

strict_1to3_unbalanced:
  panel_event_monthly_matched_final_clean_1to3_only.csv
```

---

## Key Findings

### 1. The paper uses 1:3 matching

The paper states that for each Cursor-adopting repository, it performs:

```text
1:3 nearest-neighbor matching
three controls per treated unit
```

So the paper does **not** directly support this interpretation:

```text
A treated repo can have only 1 or 2 controls.
```

The paper’s matching rule is closer to:

```text
Each treated repo should have 3 matched control slots.
```

However, the same control repository may be reused across multiple treated repositories.

Example:

```text
Treatment repo 1:
  A_control, B_control, C_control

Treatment repo 2:
  A_control, D_control, E_control
```

This means controls do **not** need to be globally unique.

---

### 2. `strict_1to3_unbalanced` is closer to the paper’s matching rule

We agreed that:

```text
strict_1to3_unbalanced:
  closer to the paper's data organization / matching rule

main_unbalanced:
  closer to the paper's sample size / sample coverage
```

The reason is:

```text
strict_1to3_unbalanced keeps only treated repos with exactly 3 final controls.
```

This matches the paper’s stated 1:3 matching design more closely.

---

### 3. `main_unbalanced` is larger because it keeps treated repos with 1, 2, or 3 final controls

The `main_unbalanced` panel uses the full final-clean pair file:

```text
jsts_matched_control_pairs_main_398_final_clean.csv
```

This file includes treated repositories even if, after filtering, they have only:

```text
1 final control
2 final controls
3 final controls
```

Therefore, `main_unbalanced` is larger.

In contrast, `strict_1to3_unbalanced` uses:

```text
jsts_matched_control_pairs_main_398_final_clean_1to3_only.csv
```

This keeps only treated repositories with:

```text
num_final_controls == 3
```

So `strict_1to3_unbalanced` is smaller.

---

## Important Code Logic Confirmed

In `filter_controls_by_local_cursor_evidence.py`, the script first removes controls with local Cursor evidence inside the analysis window:

```python
remove_controls = set(in_window["repo_name"].astype(str).str.strip())

final_controls = controls[~controls["repo_name"].isin(remove_controls)].copy()
dropped_pairs = pairs[pairs["control_repo"].isin(remove_controls)].copy()
final_pairs = pairs[~pairs["control_repo"].isin(remove_controls)].copy()
```

Then it computes how many controls remain per treatment:

```python
final_counts = (
    final_pairs.groupby("treatment_repo")["control_repo"]
    .nunique()
    .reset_index(name="num_final_controls")
)
```

Then it creates the strict 1:3 subset:

```python
strict_1to3_treatments = set(
    coverage.loc[coverage["num_final_controls"] == 3, "treatment_repo"]
)

strict_1to3_pairs = final_pairs[
    final_pairs["treatment_repo"].isin(strict_1to3_treatments)
].copy()
```

So the strict 1:3 logic is:

```text
Keep only treated repositories with exactly 3 final controls.
```

---

## Why Our `strict_1to3_unbalanced` Result Differs from the Paper

The final explanation we agreed on is:

```text
Our strict_1to3_unbalanced result differs from the paper not simply because
some repos are unavailable for git-cloning, but because those unavailable repos
trigger sample attrition in a strict 1:3 design.
```

More specifically:

```text
original 1:3 matched pairs
→ some control repos are no longer clone-usable
→ some control repos are removed due to local Cursor evidence
→ some treated repos now have only 1 or 2 final controls
→ strict_1to3 filtering drops those treated repos
→ strict_1to3_unbalanced becomes smaller and more selective
→ estimates can differ from the paper
```

So the short answer is:

```text
Yes, repo unavailability is one important reason.
But the full reason is the combination of repo unavailability, control filtering,
and the strict 1:3 requirement.
```

---

## Final Agreed Interpretation

We agreed on the following three-part conclusion:

```text
Data size / sample coverage:
  main_unbalanced is closer to the paper Appendix JS/TS dataset.

Data organization / matching rule:
  strict_1to3_unbalanced is closer to the paper.

Result pattern:
  strict_1to3_unbalanced is closer to the paper.
```

This is the cleanest way to explain the comparison.

---

## Paper Comparison Summary

Paper Appendix JS/TS reports:

```text
Treatment repos: 411
Control repos: 422
Total observations: 8,870
Post-treatment observations: 2,279
```

Our `main_unbalanced` is closer in size.

Our `strict_1to3_unbalanced` is closer in matching structure because each included treatment still has exactly 3 final controls.

---

## Interpretation for Reporting

Recommended wording:

```text
The strict_1to3_unbalanced panel is closer to the paper's stated 1:3
matching rule, because each included treated repository retains exactly three
matched control repositories, while controls may be reused across treated
repositories. However, our strict panel is smaller than the paper's JS/TS
Appendix sample because some matched controls were no longer clone-usable or
were removed after local Cursor-evidence filtering. These losses caused some
treated repositories to lose one or more controls, and the strict 1:3 filter
then removed those treated repositories from the analysis. Therefore, the
difference from the paper is best explained by sample attrition caused by
repo unavailability and filtering under a strict 1:3 design.
```

---

## Next Steps

When we resume, we should document this clearly in the methodology notes.

Suggested next check:

```bash
cat tmp_jsts_test/data/jsts_control_pair_coverage_main_398_final_clean.csv
```

and summarize:

```text
How many treatments have 1 final control?
How many treatments have 2 final controls?
How many treatments have 3 final controls?
Which treatment repos were dropped by strict_1to3?
```

This will let us explicitly quantify the attrition from `main_unbalanced` to `strict_1to3_unbalanced`.
