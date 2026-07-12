import os
import requests
from dotenv import load_dotenv

# Load environment variables from the project .env file
load_dotenv(dotenv_path=".env")

sonar_host = os.getenv("SONAR_HOST")
sonar_token = os.getenv("SONAR_TOKEN")
sonar_scanner_path = os.getenv("SONAR_SCANNER_PATH")

print("SONAR_HOST is set:", bool(sonar_host))
print("SONAR_TOKEN is set:", bool(sonar_token))
print("SONAR_SCANNER_PATH is set:", bool(sonar_scanner_path))

if not sonar_host:
    raise SystemExit("Missing SONAR_HOST in .env")

# Check whether the SonarQube server is reachable
status_url = f"{sonar_host.rstrip('/')}/api/system/status"
response = requests.get(status_url, timeout=10)
print("System status HTTP:", response.status_code)
print("System status response:", response.text[:300])

# Check whether the token is valid, if provided
if sonar_token:
    validate_url = f"{sonar_host.rstrip('/')}/api/authentication/validate"
    response = requests.get(validate_url, auth=(sonar_token, ""), timeout=10)
    print("Authentication validate HTTP:", response.status_code)
    print("Authentication validate response:", response.text[:300])
else:
    print("Skipping authentication test because SONAR_TOKEN is not set")
