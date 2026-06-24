from pathlib import Path
import pandas as pd


def count_language_file(path: str, label: str) -> None:
    path_obj = Path(path)

    if not path_obj.exists():
        print()
        print(f"== {label} ==")
        print(f"File not found yet: {path}")
        print("Skip this section for now.")
        return

    df = pd.read_csv(path_obj, dtype=str, low_memory=False)

    primary_ts = df["repo_primary_language"].eq("TypeScript").sum()
    contains_ts = (
        df["repo_languages"].fillna("").str.contains(r"\bTypeScript:", regex=True).sum()
        if "repo_languages" in df.columns
        else None
    )
    primary_js = df["repo_primary_language"].eq("JavaScript").sum()
    primary_ts_or_js = df["repo_primary_language"].isin(["TypeScript", "JavaScript"]).sum()

    print()
    print(f"== {label} ==")
    print("File:", path)
    print("Rows:", len(df))
    print("Primary TypeScript:", primary_ts)
    print("Contains TypeScript:", contains_ts)
    print("Primary JavaScript:", primary_js)
    print("Primary TypeScript or JavaScript:", primary_ts_or_js)

    print()
    print("Primary language counts:")
    print(df["repo_primary_language"].fillna("(missing)").value_counts().head(20).to_string())

    if "rank" in df.columns:
        print()
        print("Top TypeScript candidates:")
        cols = [
            "rank", "repo_name", "event_month",
            "pre_panel_months", "post_panel_months",
            "balanced_window", "cursor_commit_share",
            "cursor_commit_rows", "repo_commits",
            "repo_contributors", "repo_stars",
            "repo_primary_language"
        ]
        cols = [c for c in cols if c in df.columns]
        ts = df[df["repo_primary_language"].eq("TypeScript")].copy()
        if len(ts) == 0:
            print("(No primary TypeScript rows in this file.)")
        else:
            print(ts[cols].head(30).to_string(index=False))


def main() -> None:
    count_language_file(
        "data_baseline_backup/repos.csv",
        "baseline repos metadata"
    )

    count_language_file(
        "tmp_typescript_test/data/top_typescript_clone_candidates.csv",
        "top_n candidates"
    )

    count_language_file(
        "tmp_typescript_test/data/top_typescript_clone_candidates_all_eligible.csv",
        "all eligible candidates"
    )


if __name__ == "__main__":
    main()
