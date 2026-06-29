#!/usr/bin/env python3
"""Run Borusyak DiD for the SonarQube Code Hygiene warning category.

This script:
  1. Reads a run9e quality DiD panel.
  2. Reads SonarQube warning issue/count data.
  3. Filters/categorizes warnings to Code Hygiene.
  4. Builds a repo-month Code Hygiene warning-count outcome.
  5. Writes a DiD input CSV.
  6. Calls R helper functions for Borusyak static and dynamic DiD.

Important:
  The warning input must contain both treatment and control repositories.
  If it only contains treatment repos, this script stops by default to avoid
  producing a misleading DiD estimate.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd


DEFAULT_CATEGORY = "Code Hygiene"

DEFAULT_PANEL = (
    "tmp_jsts_test/data/jsts_did_final/"
    "panel_event_monthly_matched_final_clean_balanced_with_sonarqube_quality_did_input.csv"
)

DEFAULT_OUT_DIR = (
    "tmp_jsts_test/data/jsts_did_final/"
    "warning_category_did/code_hygiene"
)

CANDIDATE_WARNING_INPUTS = [
    "tmp_jsts_test/data/jsts_sonarqube_main/sonarqube_warnings_categorized.csv",
    "tmp_jsts_test/data/jsts_sonarqube_main/sonarqube_warnings.csv",
    "tmp_jsts_test/data/jsts_sonarqube_main/treatment/data/sonarqube_warnings_categorized.csv",
    "tmp_jsts_test/data/jsts_sonarqube_main/treatment/data/sonarqube_warnings.csv",
    "tmp_jsts_test/data/jsts_sonarqube_main/control/data/sonarqube_warnings_categorized.csv",
    "tmp_jsts_test/data/jsts_sonarqube_main/control/data/sonarqube_warnings.csv",
    "data/sonarqube_warnings_categorized.csv",
    "data/sonarqube_warnings.csv",
]

KEY_COLS = ["repo_name", "time", "dataset_source"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Borusyak DiD for Code Hygiene warnings."
    )
    parser.add_argument(
        "--panel",
        default=DEFAULT_PANEL,
        help="run9e full quality DiD input panel.",
    )
    parser.add_argument(
        "--warnings",
        default=None,
        help=(
            "SonarQube warning issue/count CSV. If omitted, the script searches "
            "common project paths."
        ),
    )
    parser.add_argument(
        "--category",
        default=DEFAULT_CATEGORY,
        help="Warning category to analyze. Default: Code Hygiene.",
    )
    parser.add_argument(
        "--out-dir",
        default=DEFAULT_OUT_DIR,
        help="Output directory.",
    )
    parser.add_argument(
        "--helper",
        default="proc_r/diff_in_diff_borusyak_helpers.R",
        help="R helper file containing Borusyak functions.",
    )
    parser.add_argument(
        "--allow-treatment-only-warning-input",
        action="store_true",
        help=(
            "Allow running even when the warning input has no control repositories. "
            "Not recommended for causal DiD."
        ),
    )
    parser.add_argument(
        "--horizon-min",
        type=int,
        default=-6,
        help="Minimum event-study horizon.",
    )
    parser.add_argument(
        "--horizon-max",
        type=int,
        default=6,
        help="Maximum event-study horizon.",
    )
    return parser.parse_args()


def find_warning_input(user_path: str | None) -> Path:
    if user_path:
        path = Path(user_path)
        if not path.exists():
            raise FileNotFoundError(f"Warning input not found: {path}")
        return path

    for candidate in CANDIDATE_WARNING_INPUTS:
        path = Path(candidate)
        if path.exists():
            return path

    searched = "\n".join(f"  - {p}" for p in CANDIDATE_WARNING_INPUTS)
    raise FileNotFoundError(
        "No warning input found. Set WARNING_INPUT or pass --warnings.\n"
        f"Searched:\n{searched}"
    )


def normalize_time(value: object) -> str | None:
    if pd.isna(value):
        return None

    text = str(value).strip()
    if not text or text.lower() in {"na", "nan", "none", "null"}:
        return None

    # YYYY-MM
    m = re.match(r"^(\d{4})-(\d{2})$", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    # YYYYMM
    m = re.match(r"^(\d{4})(\d{2})$", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    # ISO date
    m = re.match(r"^(\d{4})-(\d{2})-\d{2}", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    return None


def yyyymm_to_month_id(value: object) -> int | None:
    time_text = normalize_time(value)
    if time_text is None:
        return None

    year = int(time_text[:4])
    month = int(time_text[5:7])

    if month < 1 or month > 12:
        return None

    return year * 12 + month


def import_rule_category_mapping() -> dict[str, str]:
    """Load SonarQube rule-to-category mapping.

    Preferred source:
      data/sonarqube_warning_definitions.csv

    Legacy fallback:
      proc_scripts/classify_sonarqube_warnings.py with RULE_TO_CATEGORY
    """
    candidates: list[Path] = []

    env_path = os.environ.get("WARNING_DEFINITIONS")
    if env_path:
        candidates.append(Path(env_path))

    candidates.extend(
        [
            Path("data/sonarqube_warning_definitions.csv"),
            Path("tmp_jsts_test/data/jsts_sonarqube_main/sonarqube_warning_definitions.csv"),
            Path("tmp_jsts_test/data/jsts_sonarqube_main/data/sonarqube_warning_definitions.csv"),
        ]
    )

    for definition_path in candidates:
        if not definition_path.exists():
            continue

        definitions = pd.read_csv(definition_path, low_memory=False)

        required = {"rule", "category"}
        missing = required - set(definitions.columns)
        if missing:
            raise ValueError(
                f"Warning definition file {definition_path} is missing columns: "
                f"{sorted(missing)}"
            )

        mapping = (
            definitions[["rule", "category"]]
            .dropna()
            .drop_duplicates("rule")
            .set_index("rule")["category"]
            .to_dict()
        )

        print(f"Loaded rule-category mapping from: {definition_path}")
        print(f"Mapped rules: {len(mapping)}")

        return mapping

    # Legacy fallback: old script with RULE_TO_CATEGORY dictionary.
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    legacy_candidates = [
        project_root / "proc_scripts" / "classify_sonarqube_warnings.py",
        project_root / "classify_sonarqube_warnings.py",
    ]

    for legacy_path in legacy_candidates:
        if legacy_path.exists():
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "classify_sonarqube_warnings", legacy_path
            )
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if hasattr(module, "RULE_TO_CATEGORY"):
                mapping = dict(module.RULE_TO_CATEGORY)
                print(f"Loaded legacy RULE_TO_CATEGORY from: {legacy_path}")
                print(f"Mapped rules: {len(mapping)}")
                return mapping

    searched = "\n".join(str(p) for p in candidates + legacy_candidates)
    raise FileNotFoundError(
        "Could not find rule-category mapping. "
        "Expected data/sonarqube_warning_definitions.csv or legacy "
        "classify_sonarqube_warnings.py with RULE_TO_CATEGORY.\n"
        f"Searched:\n{searched}"
    )


def load_panel(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    missing = set(KEY_COLS) - set(df.columns)
    if missing:
        raise ValueError(f"Panel missing required columns: {sorted(missing)}")

    if "event" not in df.columns:
        raise ValueError("Panel must contain event column.")

    df = df.copy()
    df["time"] = df["time"].map(normalize_time)
    df = df[df["time"].notna()].copy()

    duplicate_count = int(df.duplicated(KEY_COLS).sum())
    if duplicate_count:
        raise ValueError(f"Panel has duplicated repo-time-source rows: {duplicate_count}")

    return df


def load_warning_counts(path: Path, category: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(path, low_memory=False)

    if "repo_name" not in df.columns:
        raise ValueError("Warning input must contain repo_name.")

    # Determine time column.
    if "time" in df.columns:
        df["time"] = df["time"].map(normalize_time)
    elif "month" in df.columns:
        df["time"] = df["month"].map(normalize_time)
    elif "creation_date" in df.columns:
        df["time"] = df["creation_date"].map(normalize_time)
    else:
        raise ValueError(
            "Warning input must contain one of: time, month, creation_date."
        )

    df = df[df["time"].notna()].copy()

    # Determine category.
    if "category" not in df.columns:
        if "rule" not in df.columns:
            raise ValueError(
                "Warning input has no category column and no rule column for mapping."
            )

        mapping = import_rule_category_mapping()
        df["category"] = df["rule"].map(mapping).fillna("Other")

    category_df = df[df["category"] == category].copy()

    if category_df.empty:
        raise ValueError(f"No warnings found for category: {category}")

    # Determine count.
    if "warning_count" in category_df.columns:
        category_df["warning_count"] = pd.to_numeric(
            category_df["warning_count"], errors="coerce"
        ).fillna(0)
        counts = (
            category_df.groupby(["repo_name", "time"], as_index=False)["warning_count"]
            .sum()
            .rename(columns={"warning_count": "category_warning_count"})
        )
    elif "count" in category_df.columns:
        category_df["count"] = pd.to_numeric(category_df["count"], errors="coerce").fillna(0)
        counts = (
            category_df.groupby(["repo_name", "time"], as_index=False)["count"]
            .sum()
            .rename(columns={"count": "category_warning_count"})
        )
    elif "issue_key" in category_df.columns:
        counts = (
            category_df.groupby(["repo_name", "time"], as_index=False)["issue_key"]
            .nunique()
            .rename(columns={"issue_key": "category_warning_count"})
        )
    else:
        counts = (
            category_df.groupby(["repo_name", "time"], as_index=False)
            .size()
            .rename(columns={"size": "category_warning_count"})
        )

    all_warning_repo_months = df[["repo_name", "time"]].drop_duplicates().copy()
    all_warning_repo_months["warning_input_has_repo_month"] = 1

    return counts, all_warning_repo_months


def prepare_did_input(
    panel: pd.DataFrame,
    counts: pd.DataFrame,
    warning_coverage: pd.DataFrame,
    category: str,
    allow_treatment_only: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = panel.merge(counts, on=["repo_name", "time"], how="left")
    df = df.merge(warning_coverage, on=["repo_name", "time"], how="left")

    df["warning_input_has_repo_month"] = df["warning_input_has_repo_month"].fillna(0).astype(int)
    df["category_warning_count"] = df["category_warning_count"].fillna(0).astype(float)

    safe_name = category.lower().replace("/", "_").replace(" ", "_")
    outcome_col = f"{safe_name}_warnings"
    log_col = f"log_{safe_name}_warnings"

    df[outcome_col] = df["category_warning_count"]
    df[log_col] = df[outcome_col].map(lambda x: math.log1p(x) if pd.notna(x) and x >= 0 else None)

    treatment_repo_count = df.loc[
        (df["dataset_source"] == "treatment") & (df["warning_input_has_repo_month"] == 1),
        "repo_name",
    ].nunique()
    control_repo_count = df.loc[
        (df["dataset_source"] == "control") & (df["warning_input_has_repo_month"] == 1),
        "repo_name",
    ].nunique()

    if control_repo_count == 0 and not allow_treatment_only:
        raise ValueError(
            "Warning input has no observed control repositories. "
            "This is not valid for DiD. Collect or provide warning category data "
            "for both treatment and control repos, or rerun with "
            "--allow-treatment-only-warning-input for a diagnostic-only run."
        )

    if treatment_repo_count == 0:
        raise ValueError("Warning input has no observed treatment repositories.")

    df["time_id"] = df["time"].map(yyyymm_to_month_id)

    event_norm = df["event"].map(normalize_time)
    df["event_yyyymm"] = event_norm
    df["event_id"] = event_norm.map(yyyymm_to_month_id).fillna(0).astype(int)

    # Same adoption cohort window used in the run9 quality DiD.
    event_numeric = df["event_yyyymm"].str.replace("-", "", regex=False)
    event_numeric = pd.to_numeric(event_numeric, errors="coerce").fillna(0).astype(int)

    cohort_ok = (event_numeric == 0) | ((event_numeric > 202407) & (event_numeric <= 202503))
    df = df[cohort_ok].copy()

    df = df[df["time_id"].notna()].copy()
    df["time_id"] = df["time_id"].astype(int)

    df["repo_id"] = pd.factorize(df["repo_name"])[0] + 1

    if "contributors" in df.columns:
        df["contributors"] = pd.to_numeric(df["contributors"], errors="coerce")
        df["contributors_log"] = df["contributors"].map(
            lambda x: math.log1p(x) if pd.notna(x) and x >= 0 else None
        )

    if "ncloc" in df.columns:
        df["ncloc"] = pd.to_numeric(df["ncloc"], errors="coerce")
        df["log_ncloc"] = df["ncloc"].map(
            lambda x: math.log1p(x) if pd.notna(x) and x >= 0 else None
        )

    base_ready = (
        df["repo_name"].notna()
        & df["time_id"].notna()
        & df["dataset_source"].isin(["treatment", "control"])
    )

    df["analysis_ready_code_hygiene_did"] = base_ready.astype(int)

    qc_rows = [
        {"check": "category", "value": category},
        {"check": "outcome_col", "value": outcome_col},
        {"check": "log_outcome_col", "value": log_col},
        {"check": "rows", "value": len(df)},
        {"check": "repos", "value": df["repo_name"].nunique()},
        {"check": "treatment_rows", "value": int((df["dataset_source"] == "treatment").sum())},
        {"check": "control_rows", "value": int((df["dataset_source"] == "control").sum())},
        {"check": "warning_input_repo_month_rows", "value": int(df["warning_input_has_repo_month"].sum())},
        {"check": "warning_input_treatment_repos", "value": int(treatment_repo_count)},
        {"check": "warning_input_control_repos", "value": int(control_repo_count)},
        {"check": "category_warning_total", "value": float(df[outcome_col].sum())},
        {"check": "category_warning_nonzero_rows", "value": int((df[outcome_col] > 0).sum())},
        {"check": "analysis_ready_code_hygiene_did_rows", "value": int(df["analysis_ready_code_hygiene_did"].sum())},
    ]

    qc = pd.DataFrame(qc_rows)

    return df, qc


def write_r_runner(
    out_dir: Path,
    did_input: Path,
    helper: Path,
    category: str,
    horizon_min: int,
    horizon_max: int,
) -> Path:
    r_path = out_dir / "run_code_hygiene_borusyak.R"

    r_code = f'''
library(data.table)
library(dplyr)
library(ggplot2)
library(didimputation)

input_path <- "{did_input.as_posix()}"
helper_path <- "{helper.as_posix()}"
out_dir <- "{out_dir.as_posix()}"
category_label <- "{category}"
horizon_min <- {horizon_min}
horizon_max <- {horizon_max}

source(helper_path)

df <- fread(input_path)
df <- df[analysis_ready_code_hygiene_did == 1]

outcome_var <- "log_code_hygiene_warnings"
outcome_label <- "Code Hygiene Warnings"

if (!(outcome_var %in% names(df))) {{
  stop("Missing outcome column: ", outcome_var)
}}

covariates <- c()

if ("contributors_log" %in% names(df)) {{
  if (sum(!is.na(df$contributors_log)) > 0) {{
    covariates <- c(covariates, "contributors_log")
  }}
}}

if ("log_ncloc" %in% names(df)) {{
  if (sum(!is.na(df$log_ncloc)) > 0) {{
    covariates <- c(covariates, "log_ncloc")
  }}
}}

if (length(covariates) == 0) {{
  first_stage_rhs <- "1"
}} else {{
  first_stage_rhs <- paste(covariates, collapse = " + ")
}}

first_stage_formula <- as.formula(
  paste0("~ ", first_stage_rhs, " | repo_id + time_id")
)

qc <- data.frame(
  check = c(
    "rows",
    "repos",
    "treated_repos",
    "control_repos",
    "outcome_nonmissing",
    "outcome_zero_rows",
    "outcome_total",
    "first_stage_formula"
  ),
  value = c(
    nrow(df),
    uniqueN(df$repo_id),
    uniqueN(df[event_id > 0, repo_id]),
    uniqueN(df[event_id == 0, repo_id]),
    sum(!is.na(df[[outcome_var]])),
    sum(df[[outcome_var]] == 0, na.rm = TRUE),
    sum(df[[outcome_var]], na.rm = TRUE),
    deparse(first_stage_formula)
  )
)

fwrite(qc, file.path(out_dir, "code_hygiene_r_qc.csv"))

static_error <- NULL
dynamic_error <- NULL

static_result <- tryCatch(
  run_borusyak_static(
    data = df,
    outcome_var = outcome_var,
    first_stage_formula = first_stage_formula,
    idname = "repo_id",
    tname = "time_id",
    gname = "event_id"
  ),
  error = function(e) {{
    static_error <<- conditionMessage(e)
    NULL
  }}
)

if (is.null(static_result)) {{
  static_df <- data.frame(
    outcome = outcome_var,
    term = "treat",
    estimate = NA_real_,
    std_error = NA_real_,
    conf_low = NA_real_,
    conf_high = NA_real_,
    p_value = NA_real_,
    note = "model failed"
  )
}} else {{
  static_df <- extract_static_result(static_result, outcome_var)
}}

static_df$outcome_label <- outcome_label
static_df$category <- category_label
fwrite(static_df, file.path(out_dir, "code_hygiene_static_effects.csv"))

dynamic_result <- tryCatch(
  run_borusyak_dynamic(
    data = df,
    outcome_var = outcome_var,
    first_stage_formula = first_stage_formula,
    horizon = horizon_min:horizon_max,
    pretrends = horizon_min:-2,
    idname = "repo_id",
    tname = "time_id",
    gname = "event_id"
  ),
  error = function(e) {{
    dynamic_error <<- conditionMessage(e)
    NULL
  }}
)

if (is.null(dynamic_result)) {{
  dynamic_df <- data.frame()
}} else {{
  dynamic_df <- extract_dynamic_result(
    dynamic_result,
    outcome = outcome_var,
    outcome_label = outcome_label,
    min_horizon = horizon_min,
    max_horizon = horizon_max
  )
}}

if (nrow(dynamic_df) > 0) {{
  dynamic_df$category <- category_label
}}

fwrite(dynamic_df, file.path(out_dir, "code_hygiene_dynamic_effects.csv"))

errors <- data.frame(
  model = c("static", "dynamic"),
  error = c(
    ifelse(is.null(static_error), "", static_error),
    ifelse(is.null(dynamic_error), "", dynamic_error)
  )
)

errors <- errors[errors$error != "", , drop = FALSE]
fwrite(errors, file.path(out_dir, "code_hygiene_errors.csv"))

if (nrow(dynamic_df) > 0) {{
  p <- ggplot(dynamic_df, aes(x = time, y = estimate)) +
    geom_errorbar(
      aes(ymin = conf_low, ymax = conf_high),
      width = 0.35,
      linetype = "dotted"
    ) +
    geom_point(aes(shape = significant), size = 2) +
    geom_hline(yintercept = 0, linetype = "dashed") +
    geom_vline(xintercept = -0.5, linetype = "dashed") +
    scale_x_continuous(breaks = horizon_min:horizon_max) +
    labs(
      title = paste("Borusyak DiD:", category_label),
      subtitle = "Outcome: log1p(Code Hygiene warning count)",
      x = "Months Relative to Cursor Adoption",
      y = "Treatment Effect"
    ) +
    theme_minimal()

  ggsave(
    filename = file.path(out_dir, "code_hygiene_dynamic_effects.pdf"),
    plot = p,
    width = 7,
    height = 4
  )
}}

cat("Saved Code Hygiene Borusyak outputs to:", out_dir, "\\n")
'''

    r_path.write_text(r_code)
    return r_path


def run_r_script(r_script: Path) -> None:
    cmd = ["Rscript", str(r_script)]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    args = parse_args()

    panel_path = Path(args.panel)
    warning_path = find_warning_input(args.warnings)
    out_dir = Path(args.out_dir)
    helper_path = Path(args.helper)

    if not panel_path.exists():
        raise FileNotFoundError(f"Panel file not found: {panel_path}")

    if not helper_path.exists():
        raise FileNotFoundError(f"R helper file not found: {helper_path}")

    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("run10a: Code Hygiene Borusyak DiD")
    print("=" * 72)
    print("Panel:", panel_path)
    print("Warnings:", warning_path)
    print("Category:", args.category)
    print("Output dir:", out_dir)
    print("Helper:", helper_path)
    print("=" * 72)

    panel = load_panel(panel_path)
    counts, coverage = load_warning_counts(warning_path, args.category)

    did_df, qc = prepare_did_input(
        panel=panel,
        counts=counts,
        warning_coverage=coverage,
        category=args.category,
        allow_treatment_only=args.allow_treatment_only_warning_input,
    )

    did_input = out_dir / "code_hygiene_did_input.csv"
    qc_output = out_dir / "code_hygiene_input_qc.csv"

    did_df.to_csv(did_input, index=False)
    qc.to_csv(qc_output, index=False)

    print()
    print("Input QC:")
    print(qc.to_string(index=False))

    r_script = write_r_runner(
        out_dir=out_dir,
        did_input=did_input.resolve(),
        helper=helper_path.resolve(),
        category=args.category,
        horizon_min=args.horizon_min,
        horizon_max=args.horizon_max,
    )

    run_r_script(r_script)

    print()
    print("Saved outputs:")
    for path in [
        did_input,
        qc_output,
        out_dir / "code_hygiene_r_qc.csv",
        out_dir / "code_hygiene_static_effects.csv",
        out_dir / "code_hygiene_dynamic_effects.csv",
        out_dir / "code_hygiene_dynamic_effects.pdf",
        out_dir / "code_hygiene_errors.csv",
    ]:
        print(" -", path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
