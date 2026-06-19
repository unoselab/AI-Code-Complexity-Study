from google.cloud import bigquery

PROJECT_ID = "se-project-438721"
MAX_BYTES = 1 * 1024 * 1024 * 1024  # 1 GiB

client = bigquery.Client(project=PROJECT_ID)

query = """
SELECT type, COUNT(*) AS n
FROM `githubarchive.day.20250101`
GROUP BY type
ORDER BY n DESC
"""

print("Client project:", client.project)

# --- 1 Dry run first
dry_config = bigquery.QueryJobConfig(
    dry_run=True,
    use_query_cache=False,
)

dry_job = client.query(query, job_config=dry_config)

print("Dry run OK")
print("Bytes processed:", dry_job.total_bytes_processed)
print("GiB processed:", dry_job.total_bytes_processed / 1024**3)

# --- 2 Actual run with safety cap
run_config = bigquery.QueryJobConfig(
    maximum_bytes_billed=MAX_BYTES,
    use_query_cache=False,
)

job = client.query(query, job_config=run_config)

print("\nActual query result:")
for row in job.result():
    print(row["type"], row["n"])


