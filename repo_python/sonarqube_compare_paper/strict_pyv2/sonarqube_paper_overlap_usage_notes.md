# SonarQube paper-overlap usage check

This diagnostic checks whether Python pyv2 SonarQube scan rows that are not present in the frozen paper panel enter the final complete-case quality DiD input.

## Key counts

- Combined scan rows: 3043
- Combined scan rows overlapping with paper: 2169
- Combined scan rows missing in paper: 874
- Final DiD rows: 1603
- Final DiD rows overlapping with paper: 1588
- Final DiD rows missing in paper: 15
- Final DiD rows missing in scan: 0

Interpretation: final_rows_missing_in_paper should be zero for a paper-overlap replication branch.
