python - <<'PY'
from pathlib import Path

import pandas as pd

issues_path = Path(
    "repo_x02/run-x-d01/model_c_token_py_file_issues.csv"
)
manifest_path = Path(
    "repo_x01/run-x-a05/velocity_did_model_c_snapshot_manifest.csv"
)

reviewed_blobs = {
    # dimatura/pypcd: malformed empty string quotes
    "5f37df295594459a52933b57ba21f690e913dc63",

    # MalevichAI/malevich: incomplete "from " statement
    "9c7e9e864c64a78e2b8fc351e07e7a092159bc27",

    # believethehype/nostrdvm: "LPimport asyncio"
    "326676230780625025ed9bcdb1614da47dca2af7",

    # DataDog template __init__.py: unexpanded {check_class}
    "6e1e729d61695c3d7c25dc2745dc3c7b455ae375",
    "fc1e471ee1487dea039246bc1847cb8657a2015e",
    "d4dfcaa940e37b16e71e547dfe318eec4d853ab5",
    "8efd462eec34088982222eeabf99802b5761f3e1",
}

issues = pd.read_csv(
    issues_path,
    dtype=str,
    keep_default_na=False,
)

manifest = pd.read_csv(
    manifest_path,
    dtype=str,
    keep_default_na=False,
)

parse_errors = issues[
    (issues["issue_stage"] == "raw_file_parse")
    & (issues["issue_type"] == "SyntaxError")
].copy()

# Review each blob once, even when it appears in multiple snapshots or paths.
unique_blobs = parse_errors.drop_duplicates(
    subset=["blob_oid"],
    keep="first",
).copy()

remaining = unique_blobs[
    ~unique_blobs["blob_oid"].isin(reviewed_blobs)
].copy()

print("Parsing-error review status")
print("---------------------------")
print(f"Unique failed blobs:    {len(unique_blobs)}")
print(f"Reviewed blobs:         {len(unique_blobs) - len(remaining)}")
print(f"Remaining blobs:        {len(remaining)}")

if remaining.empty:
    print("\nNo unreviewed parsing-error blobs remain.")
    raise SystemExit(0)

selected = remaining.iloc[0]
repo_name = selected["repo_name"]
commit_sha = selected["commit_sha"]

manifest_match = manifest[
    (manifest["repo_name"] == repo_name)
    & (manifest["latest_commit_effective"] == commit_sha)
]

if manifest_match.empty:
    manifest_match = manifest[
        manifest["repo_name"] == repo_name
    ]

clone_paths = (
    manifest_match["clone_path"]
    .loc[lambda values: values != ""]
    .drop_duplicates()
    .tolist()
)

if len(clone_paths) != 1:
    raise RuntimeError(
        f"Expected one clone_path for {repo_name}, found: {clone_paths}"
    )

clone_path = clone_paths[0]

print("\nNext unique parsing-error blob")
print("------------------------------")
print(f"snapshot_key:  {selected['snapshot_key']}")
print(f"repository:    {repo_name}")
print(f"commit:        {commit_sha}")
print(f"path:          {selected['path']}")
print(f"blob_oid:      {selected['blob_oid']}")
print(f"blob_size:     {selected['blob_size']}")
print(f"issue_message: {selected['issue_message']}")
print(f"clone_path:    {clone_path}")

print("\nCommands")
print("--------")
print(
    f'git -C "{clone_path}" cat-file blob '
    f'{selected["blob_oid"]} | nl -ba'
)
print(
    f'git -C "{clone_path}" cat-file blob '
    f'{selected["blob_oid"]} | '
    "grep -nE "
    "'^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+'"
)
print(
    f'git -C "{clone_path}" cat-file blob '
    f'{selected["blob_oid"]} > /tmp/next-parse-failure.py'
)
print(
    "/home/user1-system12/miniconda3/envs/agcparse312/bin/python "
    "-m py_compile /tmp/next-parse-failure.py"
)
PY

