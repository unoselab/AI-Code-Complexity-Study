# JS/TS Paper vs Our main/strict Dataset Comparison

## Main conclusion

The main_unbalanced panel is closer to the paper Appendix JS/TS dataset in sample size, while the strict_1to3_unbalanced panel is closer to the paper's stated 1:3 matching organization.

## Dataset size comparison

| dataset                                                   |   treatment_repos |   control_repos |   total_observations |   post_treatment_observations | min_time   | max_time   |
|:----------------------------------------------------------|------------------:|----------------:|---------------------:|------------------------------:|:-----------|:-----------|
| paper_appendix_jsts_table7                                |               411 |             422 |                 8870 |                          2279 | nan        | nan        |
| paper_baseline_panel_recomputed_jsts_treatment_repos_only |               441 |               1 |                 4833 |                          2262 | 2024-01    | 2025-08    |
| our_main_unbalanced_panel                                 |               380 |             393 |                 6281 |                          1821 | 2024-01    | 2025-08    |
| our_strict_1to3_unbalanced_panel                          |               337 |             354 |                 5518 |                          1601 | 2024-01    | 2025-08    |

## Pair-stage comparison

| dataset                            |   pair_rows |   treatment_repos |   unique_control_repos |   treatments_with_1_control |   treatments_with_2_controls |   treatments_with_3_controls |   treatments_with_other_control_count |   max_controls_per_treatment |   mean_controls_per_treatment |   max_treatments_per_control |   mean_treatments_per_control |
|:-----------------------------------|------------:|------------------:|-----------------------:|----------------------------:|-----------------------------:|-----------------------------:|--------------------------------------:|-----------------------------:|------------------------------:|-----------------------------:|------------------------------:|
| paper_matching_jsts_from_repos     |        1299 |               433 |                    543 |                           0 |                            0 |                          433 |                                     0 |                            3 |                        3      |                           49 |                       2.39227 |
| paper_matching_for_our_jsts_sample |        1152 |               384 |                    480 |                           0 |                            0 |                          384 |                                     0 |                            3 |                        3      |                           44 |                       2.4     |
| our_main_final_clean_pairs         |        1103 |               384 |                    450 |                           4 |                           41 |                          339 |                                     0 |                            3 |                        2.8724 |                           44 |                       2.45111 |
| our_strict_1to3_pairs              |        1017 |               339 |                    407 |                           0 |                            0 |                          339 |                                     0 |                            3 |                        3      |                           44 |                       2.49877 |

## Strict 1:3 attrition

Number of treatment repos kept in main pairs but dropped from strict pairs: 45

|   main_final_control_count |   dropped_treatment_repos |
|---------------------------:|--------------------------:|
|                          1 |                         4 |
|                          2 |                        41 |

## Interpretation

The strict_1to3_unbalanced panel becomes smaller because it keeps only treated repositories that still have exactly three final controls after clone usability and control contamination filtering. Treatments that lose one or more controls remain in main_unbalanced but are removed from strict_1to3_unbalanced.

## Key numbers

- Paper Appendix JS/TS: treatment=411, control=422, observations=8870, post=2279
- Our main_unbalanced: treatment=380, control=393, observations=6281, post=1821
- Our strict_1to3_unbalanced: treatment=337, control=354, observations=5518, post=1601
