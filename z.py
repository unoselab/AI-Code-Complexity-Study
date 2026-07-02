import pandas as pd
D = "tmp_jsts_test/data"
m = pd.read_csv(f"{D}/jsts_did_final/panel_event_monthly_matched_final_clean.csv")
s = pd.read_csv(f"{D}/jsts_did_final/panel_event_monthly_matched_final_clean_1to3_only.csv")
pairs = pd.read_csv(f"{D}/jsts_matched_control_pairs_main_398_clone_usable.csv")
cov = pd.read_csv(f"{D}/jsts_control_pair_coverage_main_398_clone_usable.csv")

mt = set(m.loc[m.ever_treated==1,"repo_name"]); st = set(s.loc[s.ever_treated==1,"repo_name"])
mc = set(m.loc[m.ever_treated==0,"repo_name"]); sc = set(s.loc[s.ever_treated==0,"repo_name"])
print("treated  main/strict/strict에서빠짐:", len(mt), len(st), len(mt-st))
print("control  main/strict/strict에서빠짐:", len(mc), len(sc), len(mc-sc))

# 가설 A: strict treated = usable control 3개 전부 보유한 treated
covA = set(cov.loc[cov.num_usable_controls==3,"treatment_repo"])
# 가설 B: strict treated = usable control 1개 이상 보유한 treated
covB = set(cov.loc[cov.num_usable_controls>=1,"treatment_repo"])
print("가설A(3개 전부 요구)와 일치?", st == (covA & mt))
print("가설B(1개 이상)와 일치?",   st == (covB & mt))

# control 쪽: strict control이 '유지된 treated의 짝 control'로 정확히 한정되는지
paired = set(pairs.loc[pairs["treatment_repo"].isin(st), "control_repo"])
print("strict control ⊆ 유지 treated의 짝 control?", sc <= paired)
print("strict control == 그 짝 control 전부?", sc == (paired & mc))




