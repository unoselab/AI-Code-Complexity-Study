#!/usr/bin/env python3
"""
Build a paper-faithful matched DiD event panel (treatment + PSM-selected
never-treated controls), borrowing event-time logic from
scripts/prepare_panel_event.py WITHOUT modifying or running the original.

Produces TWO outputs in one run:
  --output          : unbalanced panel. Only repo-months present in the
                      git-history time series are kept (months with no commit
                      have no row). Controls whose activity is entirely outside
                      the analysis window disappear after the date filter.
  --balanced-output : window-completed panel. For each repo, missing months in
                      [max(analysis_start, first_commit_month) .. analysis_end]
                      are zero-filled (commits/lines_*/contributors=0,
                      cursor=False). This keeps zero-commit months (paper main
                      setting; the ">0 commits" filter is a separate robustness
                      subset), fills the 28/38 month gaps, restores controls that
                      only had pre-window commits, and zero-fills empty treated
                      pre-adoption windows. Repo-months before a repo's first
                      commit are NOT fabricated.

Key design (both outputs):
  - event_month from metadata (matched_controls_v2_treatment_only.csv), NOT
    re-detected from cursor==True.
  - Treatment post_event is ABSORBING: post_event = (month >= event_month);
    the original cursor-abandonment reset is NOT applied.
  - Controls are PSM-selected never-treated units: no pseudo-event, each unique
    control once; PSM pairing kept only as provenance.
  - ever_treated / is_treatment (absorbing) / is_treatment_dynamic (cursor) /
    cursor are separate columns, supporting both absorbing (Callaway/Borusyak)
    and switching (TWFE) specifications.

NOTE: activity metrics only (commits, lines_added, ...). SonarQube quality
outcomes are merged in a later step.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MONTH_LEAD_AND_LAG = 6
START_DATE = "2024-01-01"
END_DATE = "2025-08-31"

TS_COLUMNS_EXPECTED = [
    "repo_name",
    "month",
    "latest_commit",
    "cursor",
    "commits",
    "lines_added",
    "lines_removed",
    "contributors",
]

ACTIVITY_FILL_ZERO = ["commits", "lines_added", "lines_removed", "contributors", "latest_commit"]


def coerce_cursor(series: pd.Series) -> pd.Series:
    """Return a clean boolean cursor series (handles bool, 'True'/'False', NaN).

    Avoids ``.fillna(False)`` on an object-dtype array: after a left-merge the
    cursor column is object (python bools + NaN for filled rows), and fillna on
    object dtype emits pandas' downcasting FutureWarning (a hard error under
    PYTHONWARNINGS=error::FutureWarning). Mapping each value to a python bool
    yields no NaN, so astype(bool) is a clean, warning-free cast.
    """
    if series.dtype == bool:
        return series  # numpy bool cannot hold NaN; nothing to fill
    truthy = {"true", "1"}
    return series.map(lambda v: str(v).strip().lower() in truthy).astype(bool)


def month_diff(month_str: str, event_str: str) -> int:
    """Whole-month difference (month - event), both 'YYYY-MM'."""
    m = pd.to_datetime(month_str + "-01")
    e = pd.to_datetime(event_str + "-01")
    return (m.year - e.year) * 12 + (m.month - e.month)


def month_range(start: str, end: str) -> list[str]:
    """Inclusive list of 'YYYY-MM' months from start to end."""
    s = pd.Period(start, freq="M")
    e = pd.Period(end, freq="M")
    out: list[str] = []
    p = s
    while p <= e:
        out.append(str(p))
        p += 1
    return out


def complete_repo_months(df: pd.DataFrame, analysis_start: str, analysis_end: str) -> pd.DataFrame:
    """
    Zero-fill missing repo-months within the analysis window.

    For each repo: fill [max(analysis_start, first_observed_month) .. analysis_end].
    Months before the repo's first observed commit are NOT created (no fake
    pre-existence). Months beyond analysis_end are dropped. Activity columns ->
    0, cursor -> False; the merge grid also excludes pre-window rows.
    """
    out = []
    for repo, g in df.groupby("repo_name"):
        source = g["dataset_source"].iloc[0] if "dataset_source" in g.columns else None
        first_observed = g["month"].min()  # zero-padded 'YYYY-MM' -> lexicographic == chronological
        start = max(analysis_start, first_observed)
        grid = pd.DataFrame({"month": month_range(start, analysis_end)})
        merged = grid.merge(
            g.drop(columns=[c for c in ("repo_name", "dataset_source") if c in g.columns]),
            on="month",
            how="left",
        )
        merged.insert(0, "repo_name", repo)
        if source is not None:
            merged["dataset_source"] = source
        for c in ACTIVITY_FILL_ZERO:
            if c in merged.columns:
                merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0)
        if "cursor" in merged.columns:
            merged["cursor"] = coerce_cursor(merged["cursor"])
        out.append(merged)
    completed = pd.concat(out, ignore_index=True)
    logging.info(
        "Window completion [%s..%s]: %d -> %d rows (%d repos)",
        analysis_start, analysis_end, len(df), len(completed), completed["repo_name"].nunique(),
    )
    return completed


def load_treatment_meta(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ("repo_name", "event_month"):
        if col not in df.columns:
            raise SystemExit(f"{path} missing required column: {col}")
    df = df[["repo_name", "event_month"]].dropna().copy()
    df["repo_name"] = df["repo_name"].astype(str).str.strip()
    df["event_month"] = pd.to_datetime(df["event_month"].astype(str)).dt.strftime("%Y-%m")
    df = df.drop_duplicates(subset=["repo_name"], keep="first")
    logging.info("Loaded %d treatment repos with event_month", len(df))
    return df


def load_ts(path: Path, source: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in TS_COLUMNS_EXPECTED if c not in df.columns]
    if missing:
        logging.warning("%s missing columns %s (continuing)", path, missing)
    df = df.copy()
    df["repo_name"] = df["repo_name"].astype(str).str.strip()
    df["month"] = df["month"].astype(str).str.strip()
    df["cursor"] = coerce_cursor(df["cursor"]) if "cursor" in df.columns else False
    df["dataset_source"] = source
    return df


def build_provenance(pairs_path: Path) -> pd.DataFrame:
    """One row per control repo with the treatments/ranks/periods it was matched to."""
    pairs = pd.read_csv(pairs_path)
    needed = {"treatment_repo", "control_repo", "match_rank", "matched_period"}
    if not needed.issubset(pairs.columns):
        logging.warning("pairs file missing some of %s; provenance will be partial", needed)
    pairs = pairs.dropna(subset=["control_repo"]).copy()
    pairs["control_repo"] = pairs["control_repo"].astype(str).str.strip()

    def join_unique(values: pd.Series) -> str:
        return "; ".join(sorted({str(v) for v in values.dropna()}))

    prov = (
        pairs.groupby("control_repo")
        .agg(
            matched_treatment_repos=("treatment_repo", join_unique),
            match_ranks=("match_rank", join_unique),
            matched_periods=("matched_period", join_unique),
        )
        .reset_index()
        .rename(columns={"control_repo": "repo_name"})
    )
    prov["matched_as_control"] = 1
    return prov


def make_lead_lag(time_to_event: pd.Series) -> pd.DataFrame:
    """lead_1..5 / lag_0..5 exact; lead_6 / lag_6 cumulative (matches original)."""
    out = {}
    for lead in range(1, MONTH_LEAD_AND_LAG):
        out[f"lead_{lead}"] = (time_to_event == -lead).astype(int)
    out[f"lead_{MONTH_LEAD_AND_LAG}"] = (time_to_event <= -MONTH_LEAD_AND_LAG).astype(int)
    for lag in range(0, MONTH_LEAD_AND_LAG):
        out[f"lag_{lag}"] = (time_to_event == lag).astype(int)
    out[f"lag_{MONTH_LEAD_AND_LAG}"] = (time_to_event >= MONTH_LEAD_AND_LAG).astype(int)
    return pd.DataFrame(out, index=time_to_event.index)


def build_treatment_panel(treat_ts: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """Treatment rows with absorbing post + event-time indicators (no cursor reset)."""
    event_by_repo = dict(zip(meta["repo_name"], meta["event_month"]))
    frames = []
    for repo, event_month in event_by_repo.items():
        repo_ts = treat_ts[treat_ts["repo_name"] == repo].copy()
        if repo_ts.empty:
            logging.warning("No time series for treatment repo %s; skipping", repo)
            continue
        repo_ts["time_to_event"] = repo_ts["month"].map(lambda m: month_diff(m, event_month))
        repo_ts["event"] = event_month
        repo_ts["post_event"] = (repo_ts["time_to_event"] >= 0).astype(int)  # ABSORBING
        repo_ts["ever_treated"] = 1
        repo_ts["is_treatment"] = repo_ts["post_event"]
        repo_ts["is_treatment_dynamic"] = repo_ts["cursor"].astype(int)
        repo_ts = pd.concat([repo_ts, make_lead_lag(repo_ts["time_to_event"])], axis=1)
        frames.append(repo_ts)

    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)

    for repo, g in panel.groupby("repo_name"):
        pre = g[g["time_to_event"].between(-MONTH_LEAD_AND_LAG, -1)]
        if pre.empty or pre[["commits", "lines_added", "contributors"]].to_numpy().sum() == 0:
            logging.warning("Treated repo %s has empty/zero pre-adoption window", repo)
    return panel


def build_control_panel(control_ts: pd.DataFrame, provenance: pd.DataFrame) -> pd.DataFrame:
    """Control rows as never-treated: no event, no event-time, indicators all 0."""
    panel = control_ts.copy()
    panel["event"] = pd.NA
    panel["time_to_event"] = pd.NA
    panel["post_event"] = 0
    panel["ever_treated"] = 0
    panel["is_treatment"] = 0
    panel["is_treatment_dynamic"] = panel["cursor"].astype(int)
    for lead in range(1, MONTH_LEAD_AND_LAG + 1):
        panel[f"lead_{lead}"] = 0
    for lag in range(0, MONTH_LEAD_AND_LAG + 1):
        panel[f"lag_{lag}"] = 0

    panel = panel.merge(provenance, on="repo_name", how="left")
    panel["matched_as_control"] = pd.to_numeric(panel["matched_as_control"], errors="coerce").fillna(0).astype(int)

    leaked = panel.loc[panel["cursor"] == True, "repo_name"].unique()  # noqa: E712
    if len(leaked):
        logging.warning("Control repos with cursor evidence (NOT never-treated): %s", list(leaked))
    no_prov = panel.loc[panel["matched_as_control"] == 0, "repo_name"].unique()
    if len(no_prov):
        logging.warning("Control repos without PSM provenance: %s", list(no_prov))
    return panel


def filter_by_date(panel: pd.DataFrame) -> pd.DataFrame:
    dt = pd.to_datetime(panel["month"] + "-01")
    before = len(panel)
    panel = panel[(dt >= pd.to_datetime(START_DATE)) & (dt <= pd.to_datetime(END_DATE))]
    logging.info("Date filter [%s..%s]: %d -> %d rows", START_DATE, END_DATE, before, len(panel))
    return panel


def reorder(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.rename(columns={"month": "time"})
    lead_cols = [f"lead_{k}" for k in range(MONTH_LEAD_AND_LAG, 0, -1)]
    lag_cols = [f"lag_{k}" for k in range(0, MONTH_LEAD_AND_LAG + 1)]
    front = (
        ["repo_name", "time", "dataset_source", "ever_treated", "is_treatment",
         "is_treatment_dynamic", "event", "post_event", "time_to_event"]
        + lead_cols + lag_cols
        + ["cursor", "commits", "lines_added", "lines_removed", "contributors"]
    )
    provenance = ["matched_as_control", "matched_treatment_repos", "match_ranks", "matched_periods"]
    ordered = [c for c in front if c in panel.columns]
    ordered += [c for c in provenance if c in panel.columns]
    ordered += [c for c in panel.columns if c not in ordered and c not in ("latest_commit",)]
    return panel[ordered]


def assemble_panel(treat_ts: pd.DataFrame, control_ts: pd.DataFrame,
                   meta: pd.DataFrame, provenance: pd.DataFrame) -> pd.DataFrame:
    treatment_panel = build_treatment_panel(treat_ts, meta)
    control_panel = build_control_panel(control_ts, provenance)
    if treatment_panel.empty and control_panel.empty:
        raise SystemExit("No panel rows produced.")
    panel = pd.concat([treatment_panel, control_panel], ignore_index=True)
    panel = filter_by_date(panel)
    return reorder(panel)


def log_summary(panel: pd.DataFrame, label: str) -> None:
    logging.info(
        "[%s] Rows: %d | treated repos: %d | control repos: %d",
        label, len(panel),
        panel.loc[panel["ever_treated"] == 1, "repo_name"].nunique(),
        panel.loc[panel["ever_treated"] == 0, "repo_name"].nunique(),
    )
    summary = (
        panel.groupby("dataset_source")
        .agg(repos=("repo_name", "nunique"), rows=("repo_name", "size"), post_rows=("post_event", "sum"))
        .reset_index()
    )
    print(f"\n=== {label} panel summary ===")
    print(summary.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build paper-faithful matched DiD event panel(s).")
    parser.add_argument("--treatment-meta", default="tmp_adoption_test/data/matched_controls_v2_treatment_only.csv")
    parser.add_argument("--pairs", default="tmp_adoption_test/data/matched_controls_v2_pairs.csv")
    parser.add_argument("--treatment-ts", default="tmp_adoption_test/data/python_did_test/ts_repos_monthly.csv")
    parser.add_argument("--control-ts", default="tmp_adoption_test/data/python_control_did_test/ts_repos_monthly.csv")
    parser.add_argument("--output", default="tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2.csv",
                        help="Unbalanced panel (months with commits only).")
    parser.add_argument("--balanced-output", default="tmp_adoption_test/data/python_did_test/panel_event_monthly_matched_v2_balanced.csv",
                        help="Window-completed panel (zero-filled months within analysis window).")
    parser.add_argument("--no-balanced", action="store_true", help="Skip the balanced output.")
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    treatment_meta = PROJECT_ROOT / args.treatment_meta
    pairs_path = PROJECT_ROOT / args.pairs
    treatment_ts_path = PROJECT_ROOT / args.treatment_ts
    control_ts_path = PROJECT_ROOT / args.control_ts
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    meta = load_treatment_meta(treatment_meta)
    treat_ts = load_ts(treatment_ts_path, "treatment")
    control_ts = load_ts(control_ts_path, "control")
    provenance = build_provenance(pairs_path)

    # --- Unbalanced panel (existing behavior: months with commits only) ---
    logging.info("=== Building UNBALANCED panel ===")
    unbalanced = assemble_panel(treat_ts, control_ts, meta, provenance)
    unbalanced.to_csv(output_path, index=False)
    logging.info("Saved unbalanced panel: %s", output_path)
    log_summary(unbalanced, "UNBALANCED")

    # --- Balanced panel (window completion: zero-fill missing months) ---
    if not args.no_balanced:
        astart = pd.to_datetime(START_DATE).strftime("%Y-%m")
        aend = pd.to_datetime(END_DATE).strftime("%Y-%m")
        logging.info("=== Building BALANCED panel (window completion) ===")
        treat_ts_b = complete_repo_months(treat_ts, astart, aend)
        control_ts_b = complete_repo_months(control_ts, astart, aend)
        balanced = assemble_panel(treat_ts_b, control_ts_b, meta, provenance)
        balanced_output_path = PROJECT_ROOT / args.balanced_output
        balanced_output_path.parent.mkdir(parents=True, exist_ok=True)
        balanced.to_csv(balanced_output_path, index=False)
        logging.info("Saved balanced panel: %s", balanced_output_path)
        log_summary(balanced, "BALANCED")


if __name__ == "__main__":
    main()