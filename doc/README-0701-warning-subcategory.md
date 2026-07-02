Daily Research Report

Date:
July 1, 2026

Objective:
Continue the JS/TS Cursor adoption study by decomposing the aggregate SonarQube static analysis warning outcome into its three official subcategories: bugs, vulnerabilities, and code smells.

What We Did:
1. Reviewed the motivation for warning-subcategory analysis.
   The aggregate quality DiD result for static_analysis_warnings showed only weak evidence of post-adoption increase in the strict_1to3_unbalanced panel. Since static_analysis_warnings is composed of bugs, vulnerabilities, and code_smells, we decided to analyze these subcategories separately.

2. Confirmed that the required subcategory columns exist in the strict_1to3_unbalanced quality DiD input.
   The following columns were present:
   - bugs
   - bugs_raw
   - vulnerabilities
   - vulnerabilities_raw
   - code_smells
   - code_smells_raw
   - static_analysis_warnings
   - ncloc
   - ncloc_raw
   - contributors
   - log_ncloc

   The only missing column was contributors_log, but this is not an issue because it can be created inside the Rmd using log1p(contributors).

3. Checked the distribution and zero share of each warning subcategory.
   Results showed:
   - bugs_raw: 21.59% zero rows
   - vulnerabilities_raw: 53.18% zero rows
   - code_smells_raw: 0.92% zero rows

   This indicates that vulnerabilities are sparse, bugs are moderately zero-heavy and skewed, while code smells are almost always present.

4. Checked the composition of aggregate static_analysis_warnings.
   The warning composition was:
   - bugs_raw: 244,658 warnings, 4.15%
   - vulnerabilities_raw: 21,363 warnings, 0.36%
   - code_smells_raw: 5,635,991 warnings, 95.49%

   By dataset source:
   - Control: code_smells_raw = 96.37% of warnings
   - Treatment: code_smells_raw = 95.07% of warnings

Key Results:
The aggregate static_analysis_warnings outcome is overwhelmingly dominated by code_smells. More than 95% of all warnings are code smells. Bugs account for only about 4%, and vulnerabilities account for less than 1%.

This means that the weak aggregate warning DiD result is most likely driven by the behavior of code_smells, not by bugs or vulnerabilities.

Interpretation:
The next subcategory DiD analysis will help determine whether the weak aggregate warning effect comes from:
1. code_smells also being weak after adjustment,
2. code_smells increasing but with large standard errors,
3. bugs and vulnerabilities being too sparse or noisy, or
4. the strict 1:3 matched panel having less statistical power than the main panel.

Because code_smells dominate the warning count, the log_code_smells result will be the most important subcategory result. If log_code_smells is not significant, then the strict_1to3_unbalanced panel provides weak evidence for warning accumulation. If log_code_smells is significant, then the warning increase should be interpreted as primarily maintainability-related rather than reliability- or security-related.

Files Prepared:
1. run10a-did-warning-subcategories-borusyak.sh
   Purpose:
   Wrapper script for running Borusyak DiD on SonarQube warning subcategories.

   Default behavior:
   Runs strict_1to3_unbalanced only.

   Optional behavior:
   RUN_ALL=1 runs all four panels:
   - main_unbalanced
   - main_balanced
   - strict_1to3_unbalanced
   - strict_1to3_balanced

2. proc_r/DiffInDiffBorusyak_warning_subcategories_v2.Rmd
   Purpose:
   RMarkdown analysis file for static and dynamic Borusyak DiD effects on:
   - log_bugs
   - log_vulnerabilities
   - log_code_smells

   The Rmd reuses:
   - proc_r/diff_in_diff_borusyak_helpers.R

   Shared helper functions reused:
   - run_borusyak_static()
   - run_borusyak_dynamic()
   - extract_static_result()
   - extract_dynamic_result()

Planned Output Directory:
tmp_jsts_test/data/jsts_did_final/quality_did_borusyak_warning_subcategories/

Expected Outputs for strict_1to3_unbalanced:
- borusyak_warning_subcategories_static_effects.csv
- borusyak_warning_subcategories_dynamic_effects.csv
- borusyak_warning_subcategories_input_summary.csv
- borusyak_warning_subcategories_panel_checks.csv
- borusyak_warning_subcategories_composition.csv
- borusyak_warning_subcategories_metadata.csv
- borusyak_warning_subcategories_strict_1to3_unbalanced.html
- dynamic_effects_borusyak_warning_subcategories.pdf

Commands Used:
1. Checked required columns in the strict_1to3_unbalanced quality DiD input.

2. Checked zero share and distribution of:
   - bugs_raw
   - vulnerabilities_raw
   - code_smells_raw

3. Checked warning composition:
   - overall
   - by dataset_source

4. Drafted the next analysis scripts:
   - run10a-did-warning-subcategories-borusyak.sh
   - proc_r/DiffInDiffBorusyak_warning_subcategories_v2.Rmd

Next Steps:
1. Create the two files on the server.
2. Verify helper reuse with grep.
3. Run R syntax check using knitr::purl().
4. Execute the strict-only run:
   ./run10a-did-warning-subcategories-borusyak.sh
5. Inspect:
   - static effects
   - dynamic effects
   - panel checks
   - HTML report
6. If the strict_1to3_unbalanced result is reasonable, rerun with:
   RUN_ALL=1 ./run10a-did-warning-subcategories-borusyak.sh

Current Status:
Ready to stop for today. The next analysis step is clearly defined, and the warning-subcategory decomposition plan is methodologically justified.
