import os
import requests
import yaml
from dotenv import load_dotenv
import pandas as pd

load_dotenv()
with open("jenkins_config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

url = cfg["jenkins_url"].rstrip("/")
auth = (os.getenv("JENKINS_USER"), os.getenv("JENKINS_API_TOKEN"))

jobs_resp = requests.get(f"{url}/api/json", auth=auth)
jobs_resp.raise_for_status()
jobs_data = jobs_resp.json().get("jobs", [])

builds = []
for job_info in jobs_data:
    name = job_info.get("name")
    job_url = job_info.get("url")
    if not name or not job_url:
        continue
    build_resp = requests.get(f"{job_url}lastBuild/api/json", auth=auth)
    if build_resp.status_code != 200:
        continue
    b = build_resp.json()
    builds.append({
        "job": name,
        "number": b.get("number", 0),
        "status": b.get("result", "UNKNOWN"),
        "duration_sec": (b.get("duration", 0) or 0) // 1000,
    })

df = pd.DataFrame(builds)
print("=== Pandas demo ===")
print("DataFrame (builds):")
print(df)

failed = df[df["status"] == "FAILURE"]
print("\nFailed builds:")
print(failed)

count_per_job = df.groupby("job")["number"].count()
avg_duration = df.groupby("job")["duration_sec"].mean()
print("\nCount per job:", count_per_job.to_dict())
print("Avg duration per job (sec):", avg_duration.to_dict())

df.to_csv("builds.csv", index=False)
print("\nWritten to builds.csv")
