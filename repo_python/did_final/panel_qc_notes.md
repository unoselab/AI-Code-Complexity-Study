# Python Matched Panel QC Notes

## Panel summary

| panel                  | file                                                                 |   rows |   repos |   treated_repos |   control_repos |   treatment_rows |   control_rows |   post_treatment_rows |   avg_rows_per_repo | time_col   | time_min   | time_max   |
|:-----------------------|:---------------------------------------------------------------------|-------:|--------:|----------------:|----------------:|-----------------:|---------------:|----------------------:|--------------------:|:-----------|:-----------|:-----------|
| flexible               | repo_python/did_final/panel_event_matched_flexible.csv               |   1706 |     232 |             110 |             122 |              917 |            789 |                   471 |              7.3534 | time       | 2024-01    | 2025-08    |
| strict                 | repo_python/did_final/panel_event_matched_strict.csv                 |   1633 |     220 |             100 |             120 |              853 |            780 |                   432 |              7.4227 | time       | 2024-01    | 2025-08    |
| flexible_window_driven | repo_python/did_final/panel_event_matched_flexible_window_driven.csv |   3804 |     263 |             110 |             153 |             1384 |           2420 |                   829 |             14.4639 | time       | 2024-01    | 2025-08    |
| strict_window_driven   | repo_python/did_final/panel_event_matched_strict_window_driven.csv   |   3663 |     251 |             100 |             151 |             1264 |           2399 |                   736 |             14.5936 | time       | 2024-01    | 2025-08    |

## Paper comparison

| panel    | comparison_focus   |   paper_treatment_repos |   current_treatment_repos |   treatment_repo_difference |   paper_control_repos |   current_control_repos |   control_repo_difference |   paper_total_observations |   current_total_observations |   total_observation_difference |   paper_post_treatment_observations |   current_post_treatment_observations |   post_treatment_observation_difference |
|:---------|:-------------------|------------------------:|--------------------------:|----------------------------:|----------------------:|------------------------:|--------------------------:|---------------------------:|-----------------------------:|-------------------------------:|------------------------------------:|--------------------------------------:|----------------------------------------:|
| flexible | sample_size        |                     121 |                       110 |                         -11 |                   127 |                     122 |                        -5 |                       2461 |                         1706 |                           -755 |                                 582 |                                   471 |                                    -111 |
| strict   | matching_rule      |                     121 |                       100 |                         -21 |                   127 |                     120 |                        -7 |                       2461 |                         1633 |                           -828 |                                 582 |                                   432 |                                    -150 |

## Attrition summary

| metric                            |   value | note                                                                                |
|:----------------------------------|--------:|:------------------------------------------------------------------------------------|
| current_treatment_sample          |     118 | Current reproducible Python treatment sample.                                       |
| treatments_missing_matching_rows  |       8 | Treatment repos present in the treatment sample but missing selected matching rows. |
| flexible_final_matched_treatments |     110 | Treatments retained by the flexible final-clean matched pair file.                  |
| treatments_with_2_final_controls  |      10 | Final control-count distribution after clone and local Cursor filtering.            |
| treatments_with_3_final_controls  |     100 | Final control-count distribution after clone and local Cursor filtering.            |
| strict_1to3_treatments            |     100 | Treatments retained by the strict 1:3 final-clean matched pair file.                |
| final_clean_controls_before_panel |     153 | Final clean controls before unbalanced observed-row filtering.                      |

## Interpretation

- `flexible` is the sample-size / coverage-oriented unbalanced panel. It keeps all final-clean matched treatments, including treatments with 2 or 3 controls.
- `strict` is the matching-rule-oriented unbalanced panel. It keeps only treatments with exactly 3 final controls.
- `window_driven` panels complete the Jan 2024-Aug 2025 window and should not be directly compared with paper Table 7 unbalanced observation counts.
