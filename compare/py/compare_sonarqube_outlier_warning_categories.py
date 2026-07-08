#!/usr/bin/env python3
"""Compare paper SonarQube warnings with sensitivity-scan issues for outliers.

This diagnostic script is intended for:
  compare/run-py-2b13-compare-sonarqube-outlier-warning-categories.sh

Goal:
  Compare paper warning rules/categories with SonarQube issues collected from
  the run-py-2b12 targeted sensitivity scan. This helps decide whether the
  remaining gap is driven by quality profile, active rules, analyzer/plugin
  version, or source-scope differences.

Inputs:
  - paper SonarQube warnings CSV
  - paper SonarQube warning definitions CSV
  - run-py-2b12 targets, plan, and results CSVs
  - live/local SonarQube API for issue-level data of the 2b12 projects

Outputs:
  - paper and our enriched issue-level rows for the selected outliers
  - warning type/severity comparison
  - warning category comparison
  - warning rule comparison
  - component/path comparison
  - missing paper rules and extra our rules
  - human-readable notes
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

SONAR_TOKEN = os.getenv("SONAR_TOKEN")
SONAR_HOST = os.getenv("SONAR_HOST")

OUTPUT_NAMES = {
    "paper_enriched": "sonarqube_outlier_warning_paper_enriched.csv",
    "our_enriched": "sonarqube_outlier_warning_our_issues_enriched.csv",
    "type_severity": "sonarqube_outlier_warning_type_severity_comparison.csv",
    "category": "sonarqube_outlier_warning_category_comparison.csv",
    "rule": "sonarqube_outlier_warning_rule_comparison.csv",
    "component_path": "sonarqube_outlier_warning_component_path_comparison.csv",
    "missing_rules": "sonarqube_outlier_warning_missing_paper_rules.csv",
    "extra_rules": "sonarqube_outlier_warning_extra_our_rules.csv",
    "notes": "sonarqube_outlier_warning_category_notes.md",
}

DEFAULT_SEVERITY_ORDER = ["INFO", "MINOR", "MAJOR", "CRITICAL", "BLOCKER"]
DEFAULT_TYPE_ORDER = ["CODE_SMELL", "BUG", "VULNERABILITY"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare paper and sensitivity-scan SonarQube warning categories for top outliers."
    )
    parser.add_argument("--paper-warnings-file", required=True)
    parser.add_argument("--paper-definitions-file", required=True)
    parser.add_argument("--targets-file", required=True)
    parser.add_argument("--plan-file", required=True)
    parser.add_argument("--results-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--variant",
        default="paper_like",
        help="Sensitivity-scan variant to compare. Use 'all' for all variants.",
    )
    parser.add_argument(
        "--max-issues-per-project",
        type=int,
        default=0,
        help="Optional cap for API issue rows per project. Use 0 for all rows.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=500,
        help="SonarQube issues API page size. SonarQube typically caps this at 500.",
    )
    parser.add_argument(
        "--api-sleep",
        type=float,
        default=0.0,
        help="Optional sleep between SonarQube issue API pages.",
    )
    parser.add_argument(
        "--top-print",
        type=int,
        default=30,
        help="Number of rows to print in console previews and notes.",
    )
    return parser.parse_args()


def split_variant(value: str) -> list[str] | None:
    if str(value).strip().lower() == "all":
        return None
    variants = [x.strip() for x in str(value).split(",") if x.strip()]
    return variants or ["paper_like"]


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")


def require_columns(df: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise SystemExit(f"ERROR: {label} missing required columns: {missing}")


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def clean_repo(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip()
    return out.mask(out.isna() | out.eq("") | out.str.lower().isin(["nan", "none", "nat"]))


def normalize_month_value(value: object) -> str | pd.NA:
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return pd.NA
    text = text.replace("/", "-")
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 6:
        return f"{digits[:4]}-{digits[4:6]}"
    return pd.NA


def normalize_month(series: pd.Series) -> pd.Series:
    return series.map(normalize_month_value).astype("string")


def normalize_rule(series: pd.Series) -> pd.Series:
    out = series.astype("string").str.strip()
    return out.mask(out.isna() | out.eq("") | out.str.lower().isin(["nan", "none", "nat"]))


def normalize_text(series: pd.Series, default: str = "Unmapped") -> pd.Series:
    out = series.astype("string").str.strip()
    out = out.mask(out.isna() | out.eq("") | out.str.lower().isin(["nan", "none", "nat"]))
    return out.fillna(default)


def component_path_from_component(component: object) -> str:
    if pd.isna(component):
        return "(missing)"
    text = str(component).strip()
    if not text:
        return "(missing)"
    if ":" in text:
        text = text.split(":", 1)[1]
    text = text.lstrip("./")
    return text or "(root)"


def path_bucket(path: object) -> str:
    text = component_path_from_component(path)
    if text in {"(missing)", "(root)"}:
        return text
    return text.split("/", 1)[0] or "(root)"


def load_definitions(path: Path) -> pd.DataFrame:
    require_file(path, "paper warning definitions file")
    df = pd.read_csv(path, dtype=str, low_memory=False)
    require_columns(df, ["rule"], "paper warning definitions")
    df = df.copy()
    df["rule"] = normalize_rule(df["rule"])
    for col in ["type", "severity", "effort", "example_message", "category"]:
        if col not in df.columns:
            df[col] = pd.NA
    df["type"] = normalize_text(df["type"], default="Unmapped")
    df["severity"] = normalize_text(df["severity"], default="Unmapped")
    df["category"] = normalize_text(df["category"], default="Unmapped")
    return df.dropna(subset=["rule"]).drop_duplicates("rule", keep="first")


def load_targets(path: Path) -> pd.DataFrame:
    require_file(path, "2b12 targets file")
    df = pd.read_csv(path, dtype=str, low_memory=False)
    require_columns(df, ["target_id", "source_group", "repo_name", "time", "scan_commit"], "2b12 targets")
    df = df.copy()
    df["target_id"] = pd.to_numeric(df["target_id"], errors="coerce").astype("Int64")
    df["repo_name"] = clean_repo(df["repo_name"])
    df["time"] = normalize_month(df["time"])
    return df.dropna(subset=["target_id", "repo_name", "time"]).copy()


def load_plan(path: Path, variants: list[str] | None) -> pd.DataFrame:
    require_file(path, "2b12 plan file")
    df = pd.read_csv(path, dtype=str, low_memory=False)
    require_columns(
        df,
        ["target_id", "variant", "project_key", "project_version", "repo_name", "time"],
        "2b12 plan",
    )
    df = df.copy()
    df["target_id"] = pd.to_numeric(df["target_id"], errors="coerce").astype("Int64")
    df["repo_name"] = clean_repo(df["repo_name"])
    df["time"] = normalize_month(df["time"])
    if variants is not None:
        df = df[df["variant"].isin(variants)].copy()
    return df.dropna(subset=["target_id", "repo_name", "time", "project_key"]).copy()


def load_results(path: Path, variants: list[str] | None) -> pd.DataFrame:
    require_file(path, "2b12 results file")
    df = pd.read_csv(path, dtype=str, low_memory=False)
    require_columns(
        df,
        ["target_id", "variant", "project_key", "project_version", "repo_name", "time"],
        "2b12 results",
    )
    df = df.copy()
    df["target_id"] = pd.to_numeric(df["target_id"], errors="coerce").astype("Int64")
    df["repo_name"] = clean_repo(df["repo_name"])
    df["time"] = normalize_month(df["time"])
    if variants is not None:
        df = df[df["variant"].isin(variants)].copy()
    return df.dropna(subset=["target_id", "repo_name", "time", "project_key"]).copy()


def load_paper_warnings(path: Path, definitions: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    require_file(path, "paper warnings file")
    needed = {"repo_name", "month", "issue_key", "component", "line", "rule", "creation_date"}
    raw = pd.read_csv(path, dtype=str, low_memory=False)
    require_columns(raw, ["repo_name", "month", "rule"], "paper warnings")
    raw = raw.copy()
    raw["repo_name"] = clean_repo(raw["repo_name"])
    raw["time"] = normalize_month(raw["month"])
    raw["rule"] = normalize_rule(raw["rule"])
    for col in needed:
        if col not in raw.columns:
            raw[col] = pd.NA

    target_keys = targets[["target_id", "source_group", "repo_name", "time", "scan_commit"]].drop_duplicates()
    out = raw.merge(target_keys, on=["repo_name", "time"], how="inner")
    out = out.merge(definitions, on="rule", how="left", suffixes=("", "_definition"))
    out["source_dataset"] = "paper"
    out["type"] = normalize_text(out.get("type", pd.Series(dtype=str)), default="Unmapped")
    out["severity"] = normalize_text(out.get("severity", pd.Series(dtype=str)), default="Unmapped")
    out["category"] = normalize_text(out.get("category", pd.Series(dtype=str)), default="Unmapped")
    out["component_path"] = out["component"].map(component_path_from_component)
    out["path_bucket"] = out["component_path"].map(path_bucket)
    return out.reset_index(drop=True)


def sonar_api_available() -> None:
    if not SONAR_HOST:
        raise SystemExit("ERROR: SONAR_HOST is not set.")
    if not SONAR_TOKEN:
        raise SystemExit("ERROR: SONAR_TOKEN is not set.")


def fetch_project_issues(
    project_key: str,
    page_size: int,
    max_issues: int,
    api_sleep: float,
) -> tuple[list[dict], str]:
    sonar_api_available()
    issues: list[dict] = []
    page = 1
    last_note = "ok"
    auth = (SONAR_TOKEN, "")

    while True:
        params = {
            "componentKeys": project_key,
            "p": page,
            "ps": page_size,
            "additionalFields": "_all",
        }
        url = f"{SONAR_HOST}/api/issues/search"
        try:
            response = requests.get(url, auth=auth, params=params, timeout=90)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            last_note = f"api_error:{exc}"
            break

        data = response.json()
        page_issues = data.get("issues", [])
        if not page_issues:
            break
        issues.extend(page_issues)

        if max_issues > 0 and len(issues) >= max_issues:
            issues = issues[:max_issues]
            last_note = "max_issues_reached"
            break

        total = int(data.get("total", len(issues)))
        if len(issues) >= total:
            break

        page += 1
        if api_sleep > 0:
            time.sleep(api_sleep)

    return issues, last_note


def issue_to_row(issue: dict, base: pd.Series) -> dict:
    impacts = issue.get("impacts") or []
    first_impact = impacts[0] if impacts else {}
    software_quality = first_impact.get("softwareQuality")
    impact_severity = first_impact.get("severity")

    row = {
        "target_id": base.get("target_id"),
        "variant": base.get("variant"),
        "project_key": base.get("project_key"),
        "project_version": base.get("project_version"),
        "source_group": base.get("source_group"),
        "repo_name": base.get("repo_name"),
        "time": base.get("time"),
        "scan_commit": base.get("scan_commit"),
        "issue_key": issue.get("key"),
        "component": issue.get("component"),
        "line": issue.get("line"),
        "rule": issue.get("rule"),
        "type_api": issue.get("type"),
        "severity_api": issue.get("severity"),
        "message": issue.get("message"),
        "creation_date": issue.get("creationDate"),
        "effort_api": issue.get("effort") or issue.get("debt"),
        "status": issue.get("status"),
        "resolution": issue.get("resolution"),
        "clean_code_attribute": issue.get("cleanCodeAttribute"),
        "clean_code_attribute_category": issue.get("cleanCodeAttributeCategory"),
        "software_quality": software_quality,
        "impact_severity": impact_severity,
    }
    row["component_path"] = component_path_from_component(row["component"])
    row["path_bucket"] = path_bucket(row["component_path"])
    return row


def fetch_our_issues(plan: pd.DataFrame, definitions: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    rows: list[dict] = []
    fetch_notes: list[dict] = []

    plan_unique = plan.drop_duplicates(["target_id", "variant", "project_key"]).copy()
    for idx, base in plan_unique.iterrows():
        project_key = str(base["project_key"])
        issues, note = fetch_project_issues(
            project_key=project_key,
            page_size=args.page_size,
            max_issues=args.max_issues_per_project,
            api_sleep=args.api_sleep,
        )
        fetch_notes.append(
            {
                "target_id": base.get("target_id"),
                "variant": base.get("variant"),
                "project_key": project_key,
                "fetched_issues": len(issues),
                "fetch_note": note,
            }
        )
        for issue in issues:
            rows.append(issue_to_row(issue, base))

    out = pd.DataFrame(rows)
    if out.empty:
        out = pd.DataFrame(
            columns=[
                "target_id",
                "variant",
                "project_key",
                "project_version",
                "source_group",
                "repo_name",
                "time",
                "scan_commit",
                "issue_key",
                "component",
                "line",
                "rule",
                "type_api",
                "severity_api",
                "message",
                "creation_date",
                "effort_api",
                "status",
                "resolution",
                "component_path",
                "path_bucket",
            ]
        )
    out["rule"] = normalize_rule(out.get("rule", pd.Series(dtype=str)))
    out = out.merge(definitions, on="rule", how="left", suffixes=("", "_definition"))

    type_from_api = normalize_text(out.get("type_api", pd.Series(dtype=str)), default="")
    severity_from_api = normalize_text(out.get("severity_api", pd.Series(dtype=str)), default="")
    out["type"] = type_from_api.mask(type_from_api.eq(""), normalize_text(out.get("type", pd.Series(dtype=str)), default="Unmapped"))
    out["severity"] = severity_from_api.mask(severity_from_api.eq(""), normalize_text(out.get("severity", pd.Series(dtype=str)), default="Unmapped"))
    out["category"] = normalize_text(out.get("category", pd.Series(dtype=str)), default="Unmapped")
    out["source_dataset"] = "sensitivity_scan"

    fetch_df = pd.DataFrame(fetch_notes)
    if not fetch_df.empty:
        out = out.merge(fetch_df, on=["target_id", "variant", "project_key"], how="left")
    return out.reset_index(drop=True)


def duplicate_paper_for_variants(paper: pd.DataFrame, plan: pd.DataFrame) -> pd.DataFrame:
    if paper.empty:
        return paper.assign(variant=pd.Series(dtype=str), project_key=pd.Series(dtype=str))
    variant_keys = plan[["target_id", "variant", "project_key", "project_version"]].drop_duplicates()
    out = paper.merge(variant_keys, on="target_id", how="inner")
    return out.reset_index(drop=True)


def compare_counts(
    paper: pd.DataFrame,
    ours: pd.DataFrame,
    group_cols: list[str],
    sort_cols: list[str] | None = None,
) -> pd.DataFrame:
    base_cols = ["target_id", "variant", "source_group", "repo_name", "time"]
    cols = base_cols + group_cols

    for col in cols:
        if col not in paper.columns:
            paper[col] = "(missing)"
        if col not in ours.columns:
            ours[col] = "(missing)"

    p = paper.groupby(cols, dropna=False).size().reset_index(name="paper_count")
    o = ours.groupby(cols, dropna=False).size().reset_index(name="our_count")
    out = p.merge(o, on=cols, how="outer")
    out["paper_count"] = pd.to_numeric(out["paper_count"], errors="coerce").fillna(0).astype(int)
    out["our_count"] = pd.to_numeric(out["our_count"], errors="coerce").fillna(0).astype(int)
    out["diff_our_minus_paper"] = out["our_count"] - out["paper_count"]
    out["paper_minus_our"] = out["paper_count"] - out["our_count"]
    out["abs_diff"] = out["diff_our_minus_paper"].abs()
    if sort_cols is None:
        sort_cols = ["abs_diff", "paper_count", "our_count"]
    ascending = [False for _ in sort_cols]
    return out.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)


def build_summaries(paper: pd.DataFrame, ours: pd.DataFrame) -> dict[str, pd.DataFrame]:
    summaries: dict[str, pd.DataFrame] = {}
    summaries["type_severity"] = compare_counts(
        paper,
        ours,
        ["type", "severity"],
    )
    summaries["category"] = compare_counts(
        paper,
        ours,
        ["category", "type"],
    )
    summaries["rule"] = compare_counts(
        paper,
        ours,
        ["rule", "type", "severity", "category"],
    )
    summaries["component_path"] = compare_counts(
        paper,
        ours,
        ["path_bucket", "component_path", "type"],
    )

    rule = summaries["rule"].copy()
    summaries["missing_rules"] = rule[rule["paper_minus_our"] > 0].sort_values(
        ["paper_minus_our", "paper_count"], ascending=[False, False]
    ).reset_index(drop=True)
    summaries["extra_rules"] = rule[rule["diff_our_minus_paper"] > 0].sort_values(
        ["diff_our_minus_paper", "our_count"], ascending=[False, False]
    ).reset_index(drop=True)
    return summaries


def safe_int(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(value)
    except Exception:
        return 0


def top_rows_markdown(df: pd.DataFrame, cols: list[str], n: int) -> list[str]:
    if df.empty:
        return ["- No rows."]
    keep = [col for col in cols if col in df.columns]
    lines = []
    for row in df[keep].head(n).itertuples(index=False):
        parts = []
        for col, value in zip(keep, row):
            parts.append(f"{col}={value}")
        lines.append("- " + "; ".join(parts))
    return lines


def write_notes(
    path: Path,
    args: argparse.Namespace,
    targets: pd.DataFrame,
    plan: pd.DataFrame,
    paper: pd.DataFrame,
    ours: pd.DataFrame,
    summaries: dict[str, pd.DataFrame],
) -> None:
    missing = summaries.get("missing_rules", pd.DataFrame())
    extra = summaries.get("extra_rules", pd.DataFrame())
    type_summary = summaries.get("type_severity", pd.DataFrame())
    category_summary = summaries.get("category", pd.DataFrame())

    lines: list[str] = []
    lines.append("# SonarQube outlier warning category comparison")
    lines.append("")
    lines.append("## Purpose")
    lines.append(
        "Compare paper SonarQube warning rules/categories with issue-level warnings collected from the targeted 2b12 sensitivity scan."
    )
    lines.append("")
    lines.append("## Inputs")
    lines.append(f"- paper_warnings_file: `{args.paper_warnings_file}`")
    lines.append(f"- paper_definitions_file: `{args.paper_definitions_file}`")
    lines.append(f"- targets_file: `{args.targets_file}`")
    lines.append(f"- plan_file: `{args.plan_file}`")
    lines.append(f"- results_file: `{args.results_file}`")
    lines.append(f"- variant: `{args.variant}`")
    lines.append("")
    lines.append("## Data coverage")
    lines.append(f"- selected targets: {len(targets)}")
    lines.append(f"- selected plan rows: {len(plan)}")
    lines.append(f"- paper warning rows for targets: {len(paper)}")
    lines.append(f"- sensitivity-scan issue rows fetched: {len(ours)}")
    lines.append(f"- paper unique rules: {paper['rule'].nunique() if 'rule' in paper else 0}")
    lines.append(f"- sensitivity unique rules: {ours['rule'].nunique() if 'rule' in ours else 0}")
    lines.append("")
    lines.append("## Main interpretation guide")
    lines.append(
        "- Many paper-heavy rules missing from the sensitivity scan suggest quality profile, active rules, or analyzer/plugin version differences."
    )
    lines.append(
        "- Similar rules but different component/path distributions suggest source-scope or inclusion/exclusion differences."
    )
    lines.append(
        "- Differences in both rule distribution and path distribution suggest combined source-scope and rule/profile effects."
    )
    lines.append("")
    lines.append("## Top paper-heavy missing rules")
    lines.extend(
        top_rows_markdown(
            missing,
            ["repo_name", "time", "variant", "rule", "type", "severity", "category", "paper_count", "our_count", "paper_minus_our"],
            args.top_print,
        )
    )
    lines.append("")
    lines.append("## Top sensitivity-heavy extra rules")
    lines.extend(
        top_rows_markdown(
            extra,
            ["repo_name", "time", "variant", "rule", "type", "severity", "category", "paper_count", "our_count", "diff_our_minus_paper"],
            args.top_print,
        )
    )
    lines.append("")
    lines.append("## Top type/severity differences")
    lines.extend(
        top_rows_markdown(
            type_summary,
            ["repo_name", "time", "variant", "type", "severity", "paper_count", "our_count", "diff_our_minus_paper", "abs_diff"],
            args.top_print,
        )
    )
    lines.append("")
    lines.append("## Top category differences")
    lines.extend(
        top_rows_markdown(
            category_summary,
            ["repo_name", "time", "variant", "category", "type", "paper_count", "our_count", "diff_our_minus_paper", "abs_diff"],
            args.top_print,
        )
    )
    lines.append("")
    lines.append("## Recommended next step")
    lines.append(
        "Inspect the missing-paper-rules and extra-our-rules files first. If missing paper rules dominate, compare SonarQube quality profiles, active rules, and analyzer/plugin versions before attempting more source-scope rescans."
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    variants = split_variant(args.variant)

    definitions = load_definitions(Path(args.paper_definitions_file))
    targets = load_targets(Path(args.targets_file))
    plan = load_plan(Path(args.plan_file), variants)
    results = load_results(Path(args.results_file), variants)

    if plan.empty:
        raise SystemExit("ERROR: no 2b12 plan rows remain after applying the variant filter.")

    # Prefer plan rows that produced metrics, but keep plan rows if results are not informative.
    if not results.empty and "metrics_found" in results.columns:
        metrics_flag = results["metrics_found"].astype(str).str.lower().isin(["true", "1", "yes"])
        successful = results[metrics_flag].copy()
        if not successful.empty:
            plan_keys = successful[["target_id", "variant", "project_key"]].drop_duplicates()
            plan = plan.merge(plan_keys, on=["target_id", "variant", "project_key"], how="inner")

    paper_base = load_paper_warnings(Path(args.paper_warnings_file), definitions, targets)
    paper_variant = duplicate_paper_for_variants(paper_base, plan)
    our_issues = fetch_our_issues(plan, definitions, args)

    summaries = build_summaries(paper_variant.copy(), our_issues.copy())

    save_csv(paper_variant, output_dir / OUTPUT_NAMES["paper_enriched"])
    save_csv(our_issues, output_dir / OUTPUT_NAMES["our_enriched"])
    for key in ["type_severity", "category", "rule", "component_path", "missing_rules", "extra_rules"]:
        save_csv(summaries[key], output_dir / OUTPUT_NAMES[key])

    write_notes(
        path=output_dir / OUTPUT_NAMES["notes"],
        args=args,
        targets=targets,
        plan=plan,
        paper=paper_variant,
        ours=our_issues,
        summaries=summaries,
    )

    print("Saved output directory:", output_dir)
    print()
    print("Warning comparison coverage:")
    print("Targets:", len(targets))
    print("Plan rows:", len(plan))
    print("Paper warning rows:", len(paper_variant))
    print("Our issue rows:", len(our_issues))
    print("Paper unique rules:", paper_variant["rule"].nunique() if "rule" in paper_variant else 0)
    print("Our unique rules:", our_issues["rule"].nunique() if "rule" in our_issues else 0)
    print()
    print("Key outputs:")
    for key in [
        "type_severity",
        "category",
        "rule",
        "component_path",
        "missing_rules",
        "extra_rules",
        "notes",
    ]:
        print(output_dir / OUTPUT_NAMES[key])
    print()
    print("Top paper-heavy missing rules:")
    missing = summaries["missing_rules"]
    if missing.empty:
        print("(No missing paper-heavy rules.)")
    else:
        cols = ["repo_name", "time", "variant", "rule", "type", "severity", "category", "paper_count", "our_count", "paper_minus_our"]
        cols = [c for c in cols if c in missing.columns]
        print(missing[cols].head(args.top_print).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
