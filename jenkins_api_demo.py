import os
import yaml
import requests
from dotenv import load_dotenv

load_dotenv()
with open("jenkins_config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

JENKINS_URL = cfg["jenkins_url"]
JOB_NAME = cfg["job_to_run"]
USER = os.getenv("JENKINS_USER")
TOKEN = os.getenv("JENKINS_API_TOKEN")
auth = (USER, TOKEN)

url = JENKINS_URL.rstrip("/")
job_name = JOB_NAME

# Overview
r = requests.get(f"{url}/api/json", auth=auth)
r.raise_for_status()
data = r.json()
print("=== Jenkins overview ===")
print("Jobs:", [j["name"] for j in data.get("jobs", [])])

# Job details
r2 = requests.get(f"{url}/job/{job_name}/api/json?depth=1", auth=auth)
r2.raise_for_status()
job = r2.json()
print(f"\n=== Job: {job_name} ===")
print("Description:", job.get("description") or "(none)")
print("Last build:", job.get("lastBuild", {}).get("number"))
print("Last successful:", job.get("lastSuccessfulBuild", {}).get("number"))

# Last build details
r3 = requests.get(f"{url}/job/{job_name}/lastBuild/api/json", auth=auth)
if r3.status_code == 200:
    build = r3.json()
    print("\n=== Last build ===")
    print("Number:", build.get("number"))
    print("Result:", build.get("result"))
    print("Duration (ms):", build.get("duration"))
    print("Timestamp:", build.get("timestamp"))
else:
    print("\nNo last build yet.")
