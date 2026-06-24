python - <<'PY'
import pandas as pd
from pathlib import Path

check_path = Path("tmp_jsts_test/data/jsts_did_test/adoption_month_check.csv")

out_dir = Path("tmp_jsts_test/data")
df = pd.read_csv(check_path)

# Main sample: all valid event-month repos
main = df.copy()

# Exact matched sample
exact = df[df["match_status"].eq("matched")].copy()

# Within-one-month validation sample
month_diff = pd.to_numeric(df["month_difference"], errors="coerce")
within1 = df[
    df["match_status"].eq("matched")
    | (
        df["match_status"].eq("mismatched")
        & month_diff.abs().le(1)
    )
].copy()

# Diagnostic sample: missing local adoption or large mismatch
diagnostic = df[
    df["match_status"].eq("missing_adoption_month")
    | (
        df["match_status"].eq("mismatched")
        & ~month_diff.abs().le(1)
    )
].copy()

files = {
    "main": out_dir / "jsts_treatment_sample_main_398.csv",
    "exact": out_dir / "jsts_treatment_sample_exact_match_381.csv",
    "within1": out_dir / "jsts_treatment_sample_within1_month_388.csv",
    "diagnostic": out_dir / "jsts_treatment_sample_diagnostic_10.csv",
}

main.to_csv(files["main"], index=False)
exact.to_csv(files["exact"], index=False)
within1.to_csv(files["within1"], index=False)
diagnostic.to_csv(files["diagnostic"], index=False)

print("Input rows:", len(df))
print("Main rows:", len(main), "->", files["main"])
print("Exact matched rows:", len(exact), "->", files["exact"])
print("Within-one-month rows:", len(within1), "->", files["within1"])
print("Diagnostic rows:", len(diagnostic), "->", files["diagnostic"])

print()
print("Diagnostic repos:")
cols = [
    "repo_name",
    "repo_primary_language",
    "event_month",
    "adoption_month",
    "match_status",
    "month_difference",
    "confidence",
    "evidence_paths",
]
cols = [c for c in cols if c in diagnostic.columns]
print(diagnostic[cols].to_string(index=False))
PY