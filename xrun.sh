# python - <<'PY'
# from pathlib import Path

# p = Path("proc_scripts/run_sonarqube_one_repo_test.py")
# s = p.read_text()

# # Read/write only the temporary one-repo test data.
# s = s.replace(
#     'DATA_DIR = SCRIPT_DIR.parent / "data"',
#     'DATA_DIR = SCRIPT_DIR.parent / "tmp_sonar_one_repo" / "data"'
# )

# # Use one process for a controlled smoke test.
# s = s.replace(
#     "NUM_PROCESSES = 8",
#     "NUM_PROCESSES = 1"
# )

# p.write_text(s)

# print("Patched:", p)
# PY