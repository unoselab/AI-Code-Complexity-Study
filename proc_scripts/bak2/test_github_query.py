import os
from dotenv import load_dotenv
from github import Github

load_dotenv(dotenv_path=".env")

token = os.getenv("GITHUB_TOKEN")
if not token:
    raise SystemExit("GITHUB_TOKEN is not set")

g = Github(token, per_page=5)

print("Authenticated rate limit:")
rate = g.get_rate_limit()
print("  Core:", rate.core.remaining, "/", rate.core.limit)
print("  Search:", rate.search.remaining, "/", rate.search.limit)

query = "filename:.cursorrules"
print("\nQuery:", query)

results = g.search_code(query=query)
print("Total count:", results.totalCount)

print("\nFirst 5 results:")
for i, item in enumerate(results[:5], start=1):
    print(f"{i}. {item.repository.full_name} :: {item.path}")
    print(f"   {item.html_url}")
