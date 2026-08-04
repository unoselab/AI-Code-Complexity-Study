#!/usr/bin/env python3
"""
Map cloc whole-repository language labels to paper/GitHub language taxonomy.

Inputs:
  - C04 cloc language-level results
  - C04a paper language type outputs

Outputs:
  - language mapping table
  - mapped cloc language rows
  - paper-language aggregate table
  - needs-review table
  - QC table
  - summary table

This script is intentionally conservative:
  - exact paper-language matches are accepted
  - selected known cloc aliases are mapped only when the target paper label exists
  - ambiguous labels are preserved and marked for review
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Map C04 cloc language labels to paper/GitHub language taxonomy."
    )
    parser.add_argument("--cloc-language-results", required=True)
    parser.add_argument("--paper-language-types", required=True)
    parser.add_argument("--paper-primary-language-types", required=True)
    parser.add_argument("--mapping-output", required=True)
    parser.add_argument("--mapped-language-results-output", required=True)
    parser.add_argument("--paper-language-aggregate-output", required=True)
    parser.add_argument("--needs-review-output", required=True)
    parser.add_argument("--qc-output", required=True)
    parser.add_argument("--summary-output", required=True)
    return parser.parse_args()


def require_file(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(f"{label} not found or empty: {path}")


def read_csv(path: Path, label: str) -> pd.DataFrame:
    require_file(path, label)
    return pd.read_csv(path, dtype=str, low_memory=False)


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def collect_language_values(df: pd.DataFrame) -> set[str]:
    candidate_cols = [
        "language",
        "paper_language",
        "paper_language_type",
        "language_type",
        "repo_primary_language",
        "primary_language",
        "repo_language",
        "github_language",
    ]

    out: set[str] = set()

    for col in candidate_cols:
        if col in df.columns:
            out.update(clean_text(x) for x in df[col].dropna().tolist())

    if "repo_languages" in df.columns:
        for value in df["repo_languages"].dropna().tolist():
            for part in str(value).split(";"):
                label = part.split(":", 1)[0].strip()
                if label:
                    out.add(label)

    return {x for x in out if x and x.lower() not in {"nan", "none", "null"}}


def add_case_lookup(labels: set[str]) -> dict[str, str]:
    return {label.lower(): label for label in labels}


def choose_alias_target(candidates: list[str], paper_languages: set[str]) -> str | None:
    for candidate in candidates:
        if candidate in paper_languages:
            return candidate
    lower_lookup = add_case_lookup(paper_languages)
    for candidate in candidates:
        if candidate.lower() in lower_lookup:
            return lower_lookup[candidate.lower()]
    return None


def build_mapping(cloc_summary: pd.DataFrame, paper_languages: set[str]) -> pd.DataFrame:
    exact_lookup = add_case_lookup(paper_languages)

    alias_candidates = {
        "Vuejs Component": ["Vue"],
        "Bourne Shell": ["Shell"],
        "Bourne Again Shell": ["Shell"],
        "Zsh": ["Shell"],
        "Fish Shell": ["Shell"],
        "make": ["Makefile"],
        "LESS": ["Less"],
        "Sass": ["Sass", "SCSS"],
        "Protocol Buffers": ["Protocol Buffer"],
        "PO File": ["Gettext Catalog", "PO File"],
        "Jinja Template": ["Jinja", "Jinja Template"],
        "C/C++ Header": ["C++", "C"],
    }

    rows = []

    for _, row in cloc_summary.iterrows():
        cloc_language = clean_text(row["language"])
        paper_language = ""
        status = "unmapped_review"
        note = "No exact or safe alias mapping found."

        if cloc_language in paper_languages:
            paper_language = cloc_language
            status = "exact"
            note = "cloc language exactly matches paper language."
        elif cloc_language.lower() in exact_lookup:
            paper_language = exact_lookup[cloc_language.lower()]
            status = "case_normalized"
            note = "cloc language matches paper language after case normalization."
        elif cloc_language in alias_candidates:
            target = choose_alias_target(alias_candidates[cloc_language], paper_languages)
            if target:
                paper_language = target
                status = "alias"
                note = "mapped by conservative known cloc-to-paper alias."
            else:
                paper_language = cloc_language
                status = "alias_target_missing_review"
                note = "known alias exists, but target paper label was not found."
        else:
            paper_language = cloc_language

        rows.append(
            {
                "cloc_language": cloc_language,
                "paper_language": paper_language,
                "mapping_status": status,
                "mapping_note": note,
                "cloc_language_rows": int(row["language_rows"]),
                "cloc_files_sum": int(row["files_sum"]),
                "cloc_code_sum": int(row["code_sum"]),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["mapping_status", "cloc_code_sum", "cloc_language"],
        ascending=[True, False, True],
    )


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def main() -> None:
    args = parse_args()

    cloc_path = Path(args.cloc_language_results)
    paper_lang_path = Path(args.paper_language_types)
    paper_primary_path = Path(args.paper_primary_language_types)

    cloc = read_csv(cloc_path, "C04 cloc language results")
    paper_lang = read_csv(paper_lang_path, "C04a paper language types")
    paper_primary = read_csv(paper_primary_path, "C04a paper primary language types")

    required_cloc_cols = ["language", "files", "code"]
    missing = [col for col in required_cloc_cols if col not in cloc.columns]
    if missing:
        raise ValueError(f"C04 cloc language results missing columns: {missing}")

    cloc["language"] = cloc["language"].map(clean_text)
    cloc["files_num"] = pd.to_numeric(cloc["files"], errors="coerce").fillna(0).astype(int)
    cloc["code_num"] = pd.to_numeric(cloc["code"], errors="coerce").fillna(0).astype(int)

    paper_languages = collect_language_values(paper_lang) | collect_language_values(paper_primary)

    if not paper_languages:
        raise ValueError(
            "No paper language labels were found from C04a outputs. "
            "Check paper_repo_language_types.csv and paper_primary_language_types.csv."
        )

    cloc_summary = (
        cloc.groupby("language", dropna=False)
        .agg(
            language_rows=("language", "size"),
            files_sum=("files_num", "sum"),
            code_sum=("code_num", "sum"),
        )
        .reset_index()
        .sort_values("code_sum", ascending=False)
    )

    mapping = build_mapping(cloc_summary, paper_languages)

    mapped = cloc.merge(
        mapping[["cloc_language", "paper_language", "mapping_status", "mapping_note"]],
        left_on="language",
        right_on="cloc_language",
        how="left",
    )

    mapped["paper_language"] = mapped["paper_language"].fillna(mapped["language"])
    mapped["mapping_status"] = mapped["mapping_status"].fillna("missing_mapping_review")
    mapped["mapping_note"] = mapped["mapping_note"].fillna("mapping row was not generated.")

    group_cols = ["paper_language"]
    if "scope_role" in mapped.columns:
        group_cols.append("scope_role")

    aggregate = (
        mapped.groupby(group_cols, dropna=False)
        .agg(
            cloc_language_count=("language", "nunique"),
            language_rows=("language", "size"),
            files_sum=("files_num", "sum"),
            code_sum=("code_num", "sum"),
        )
        .reset_index()
        .sort_values("code_sum", ascending=False)
    )

    needs_review_statuses = {
        "unmapped_review",
        "alias_target_missing_review",
        "missing_mapping_review",
    }
    needs_review = mapping[mapping["mapping_status"].isin(needs_review_statuses)].copy()

    total_code = int(mapping["cloc_code_sum"].sum())
    review_code = int(needs_review["cloc_code_sum"].sum()) if len(needs_review) else 0
    mapped_code = total_code - review_code

    qc_rows = [
        ("paper_language_types", len(paper_languages), "info"),
        ("cloc_language_types", mapping["cloc_language"].nunique(), "info"),
        ("mapping_exact", int((mapping["mapping_status"] == "exact").sum()), "info"),
        ("mapping_alias", int((mapping["mapping_status"] == "alias").sum()), "info"),
        ("mapping_case_normalized", int((mapping["mapping_status"] == "case_normalized").sum()), "info"),
        ("mapping_needs_review", int(len(needs_review)), "review" if len(needs_review) else "pass"),
        ("cloc_code_total", total_code, "info"),
        ("cloc_code_mapped_or_accepted", mapped_code, "info"),
        ("cloc_code_needs_review", review_code, "review" if review_code else "pass"),
        ("mapped_language_rows", len(mapped), "info"),
    ]

    qc = pd.DataFrame(qc_rows, columns=["check_name", "value", "status"])

    summary = pd.DataFrame(
        [
            ("implementation_version", "v1"),
            ("mapping_policy", "exact plus conservative alias; ambiguous labels preserved for review"),
            ("paper_language_type_input", str(paper_lang_path)),
            ("paper_primary_language_type_input", str(paper_primary_path)),
            ("cloc_language_results_input", str(cloc_path)),
            ("cloc_language_types", str(mapping["cloc_language"].nunique())),
            ("needs_review_language_types", str(len(needs_review))),
            ("cloc_code_total", str(total_code)),
            ("cloc_code_needs_review", str(review_code)),
        ],
        columns=["metric", "value"],
    )

    write_csv(mapping, Path(args.mapping_output))
    write_csv(mapped, Path(args.mapped_language_results_output))
    write_csv(aggregate, Path(args.paper_language_aggregate_output))
    write_csv(needs_review, Path(args.needs_review_output))
    write_csv(qc, Path(args.qc_output))
    write_csv(summary, Path(args.summary_output))

    print("C04b mapping completed.")
    print("Paper language labels:", len(paper_languages))
    print("cloc language labels:", mapping["cloc_language"].nunique())
    print("Needs-review labels:", len(needs_review))
    print("Total cloc code:", total_code)
    print("Needs-review cloc code:", review_code)
    print()
    print("Top mapping rows:")
    print(mapping.sort_values("cloc_code_sum", ascending=False).head(30).to_string(index=False))
    print()
    print("Needs review:")
    if len(needs_review) == 0:
        print("(none)")
    else:
        print(needs_review.sort_values("cloc_code_sum", ascending=False).to_string(index=False))


if __name__ == "__main__":
    main()
