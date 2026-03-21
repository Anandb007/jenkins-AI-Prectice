import os
import re
import json
import yaml
import argparse
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =========================
# Config + Env
# =========================
load_dotenv()

CONFIG_FILE = "jenkins_config.yaml"
STATE_FILE = "fetch_state.json"
OUTPUT_FILE = "all_builds_dataset.csv"
TARGET_OUTPUT_FILE = "target_failed_build_root_cause.csv"

DEFAULTS = {
    "jenkins_url": "http://localhost:8080",
    "lookback_builds_per_job": 5,
    "request_timeout_sec": 8,
    "max_workers": 8,
    "incremental_mode": False
}

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        cfg = yaml.safe_load(f) or {}
else:
    cfg = {}

cfg = {**DEFAULTS, **cfg}

JENKINS_URL = str(cfg["jenkins_url"]).rstrip("/")
LOOKBACK = int(cfg["lookback_builds_per_job"])
TIMEOUT = int(cfg["request_timeout_sec"])
MAX_WORKERS = int(cfg["max_workers"])
INCREMENTAL_MODE = bool(cfg["incremental_mode"])

USER = os.getenv("JENKINS_USER")
TOKEN = os.getenv("JENKINS_API_TOKEN")

if not USER or not TOKEN:
    raise ValueError("Missing JENKINS_USER or JENKINS_API_TOKEN in .env")

# =========================
# CLI args
# =========================
parser = argparse.ArgumentParser(description="Fetch Jenkins build data + root cause")
parser.add_argument("--job-name", type=str, default="", help="Target only this job name")
parser.add_argument("--build-number", type=int, default=0, help="Target specific build number for --job-name")
parser.add_argument("--only-failed", action="store_true", help="When targeting a job, include only non-success builds")
args = parser.parse_args()

TARGET_JOB = args.job_name.strip()
TARGET_BUILD = int(args.build_number) if args.build_number else 0
ONLY_FAILED = bool(args.only_failed)

# =========================
# HTTP Session
# =========================
session = requests.Session()
session.auth = (USER, TOKEN)

retries = Retry(
    total=3,
    backoff_factor=0.3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)
adapter = HTTPAdapter(max_retries=retries, pool_connections=50, pool_maxsize=50)
session.mount("http://", adapter)
session.mount("https://", adapter)


def safe_get_json(url: str):
    r = session.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def safe_get_text(url: str):
    r = session.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


# =========================
# State (optional incremental for all-jobs mode)
# =========================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_max_timestamp_ms": 0}


def save_state(max_timestamp_ms: int):
    with open(STATE_FILE, "w") as f:
        json.dump({"last_max_timestamp_ms": int(max_timestamp_ms)}, f, indent=2)


state = load_state()
last_max_ts = int(state.get("last_max_timestamp_ms", 0))

# =========================
# Root cause rules
# =========================
ROOT_CAUSE_RULES = [
    {
        "category": "OOM_MEMORY",
        "confidence": "high",
        "recommended_action": "Increase memory limits/heap; check leaks.",
        "patterns": [r"OutOfMemoryError", r"Java heap space", r"OOMKilled", r"Killed process .* out of memory"]
    },
    {
        "category": "DISK_SPACE",
        "confidence": "high",
        "recommended_action": "Free disk space; rotate logs/artifacts; expand volume.",
        "patterns": [r"No space left on device", r"ENOSPC", r"disk full"]
    },
    {
        "category": "PERMISSION_ISSUE",
        "confidence": "high",
        "recommended_action": "Fix permissions/credentials/role bindings.",
        "patterns": [r"Permission denied", r"EACCES", r"AccessDenied", r"not authorized"]
    },
    {
        "category": "NETWORK_CONNECTIVITY",
        "confidence": "medium",
        "recommended_action": "Check DNS/firewall/proxy/endpoints and retry policies.",
        "patterns": [r"Connection refused", r"Connection timed out", r"Read timed out", r"Name or service not known"]
    },
    {
        "category": "SCM_CHECKOUT_FAILURE",
        "confidence": "high",
        "recommended_action": "Validate repo URL, branch, credentials, agent network.",
        "patterns": [r"Failed to fetch from", r"Could not read from remote repository", r"Repository not found", r"checkout failed"]
    },
    {
        "category": "DEPENDENCY_MISSING",
        "confidence": "high",
        "recommended_action": "Install/pin missing tools/dependencies.",
        "patterns": [r"command not found", r"No module named", r"ModuleNotFoundError"]
    },
    {
        "category": "TEST_FAILURE",
        "confidence": "high",
        "recommended_action": "Inspect failed test cases and assertions.",
        "patterns": [r"AssertionError", r"FAILURES!!!", r"FAILED \(failures=", r"test failed"]
    },
    {
        "category": "COMPILATION_OR_BUILD_ERROR",
        "confidence": "medium",
        "recommended_action": "Review compile/build step and fix code/build config.",
        "patterns": [r"Compilation failed", r"BUILD FAILED", r"syntax error", r"failed with exit code"]
    },
    {
        "category": "QUALITY_GATE_FAILURE",
        "confidence": "high",
        "recommended_action": "Fix quality/security gate violations.",
        "patterns": [r"Quality Gate.*FAILED", r"quality gate failure", r"sonar.*failed"]
    },
]

COMPILED_RULES = [
    {
        "category": rule["category"],
        "confidence": rule["confidence"],
        "recommended_action": rule["recommended_action"],
        "patterns": [re.compile(p, re.IGNORECASE) for p in rule["patterns"]]
    }
    for rule in ROOT_CAUSE_RULES
]

NON_SUCCESS_STATUSES = {"FAILURE", "UNSTABLE", "ABORTED", "NOT_BUILT"}


def detect_root_cause(lines):
    for line in lines:
        s = line.strip()
        for rule in COMPILED_RULES:
            for pat in rule["patterns"]:
                if pat.search(s):
                    return (
                        rule["category"],
                        s[:300],
                        rule["confidence"],
                        rule["recommended_action"]
                    )
    return (
        "UNKNOWN",
        "",
        "low",
        "Review full console log and stack trace."
    )


def enrich_build_row(build_row):
    build_url = build_row.get("build_url", "")
    if not build_url:
        return build_row

    console_url = f"{build_url}consoleText"

    error_pat = re.compile(r"ERROR", re.IGNORECASE)
    fail_pat = re.compile(r"FAIL", re.IGNORECASE)
    exc_pat = re.compile(r"Exception", re.IGNORECASE)

    try:
        text = safe_get_text(console_url)
        lines = text.splitlines()

        build_row["log_line_count"] = len(lines)
        build_row["error_count"] = sum(1 for ln in lines if error_pat.search(ln))
        build_row["fail_count"] = sum(1 for ln in lines if fail_pat.search(ln))
        build_row["exception_count"] = sum(1 for ln in lines if exc_pat.search(ln))

        if build_row["status"] in NON_SUCCESS_STATUSES:
            cat, evd, conf, action = detect_root_cause(lines)
            build_row["root_cause_category"] = cat
            build_row["root_cause_evidence"] = evd
            build_row["root_cause_confidence"] = conf
            build_row["recommended_action"] = action
        elif build_row["status"] == "SUCCESS":
            build_row["root_cause_category"] = "NA_SUCCESS"
            build_row["root_cause_confidence"] = "na"

    except Exception:
        if build_row["status"] in NON_SUCCESS_STATUSES:
            build_row["root_cause_category"] = "UNKNOWN"
            build_row["root_cause_confidence"] = "low"
            build_row["recommended_action"] = "Console unavailable; inspect build in Jenkins UI."

    return build_row


def build_row_from_json(job_name, b):
    ts = int(b.get("timestamp") or 0)
    result = b.get("result")
    status = result if result is not None else "IN_PROGRESS"

    return {
        "job_name": job_name,
        "build_number": int(b.get("number") or 0),
        "status": status,
        "duration_sec": round((b.get("duration") or 0) / 1000.0, 3),
        "timestamp_ms": ts,
        "build_time_utc": (
            datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).isoformat() if ts > 0 else ""
        ),
        "build_url": b.get("url") or "",
        "log_line_count": 0,
        "error_count": 0,
        "fail_count": 0,
        "exception_count": 0,
        "root_cause_category": "",
        "root_cause_evidence": "",
        "root_cause_confidence": "",
        "recommended_action": ""
    }


def output_dataframe(rows, output_file):
    if not rows:
        print("No rows to write.")
        return

    df = pd.DataFrame(rows)
    final_cols = [
        "job_name",
        "build_number",
        "status",
        "duration_sec",
        "log_line_count",
        "error_count",
        "fail_count",
        "exception_count",
        "root_cause_category",
        "root_cause_evidence",
        "root_cause_confidence",
    ]
    df = df[final_cols].sort_values(by=["job_name", "build_number"], ascending=[True, False]).reset_index(drop=True)
    df.to_csv(output_file, index=False)
    print(f"Wrote: {output_file}")
    print(df.head(20).to_string(index=False))


def run_target_mode(job_name, build_number, only_failed):
    """
    Fast mode for a known job/build failure:
      --job-name my-job --build-number 123
    or
      --job-name my-job --only-failed
    """
    rows = []

    if build_number > 0:
        # Specific build only
        api = f"{JENKINS_URL}/job/{job_name}/{build_number}/api/json"
        data = safe_get_json(api)
        row = build_row_from_json(job_name, data)
        if only_failed and row["status"] == "SUCCESS":
            print("Target build is SUCCESS; nothing to report with --only-failed.")
            return
        rows.append(enrich_build_row(row))
    else:
        # Last N builds of that one job
        api = (
            f"{JENKINS_URL}/job/{job_name}/api/json"
            f"?tree=builds[number,result,duration,timestamp,url]{{0,{LOOKBACK}}}"
        )
        data = safe_get_json(api)
        for b in data.get("builds", []):
            row = build_row_from_json(job_name, b)
            if only_failed and row["status"] == "SUCCESS":
                continue
            rows.append(row)

        # Enrich in parallel
        enriched = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = [ex.submit(enrich_build_row, r) for r in rows]
            for f in as_completed(futures):
                enriched.append(f.result())
        rows = enriched

    output_dataframe(rows, TARGET_OUTPUT_FILE)

    # Print concise root-cause summary for fast troubleshooting
    failed = [r for r in rows if r["status"] in NON_SUCCESS_STATUSES]
    if failed:
        print("\n=== Failed Build Root Cause Summary ===")
        for r in sorted(failed, key=lambda x: x["build_number"], reverse=True):
            print(
                f"job={r['job_name']} build={r['build_number']} status={r['status']} "
                f"root_cause={r['root_cause_category']} confidence={r['root_cause_confidence']}"
            )
            if r["root_cause_evidence"]:
                print(f"evidence: {r['root_cause_evidence']}")
            if r["recommended_action"]:
                print(f"action: {r['recommended_action']}")
            print("-" * 80)
    else:
        print("No failed/non-success builds found for target mode.")


def run_all_jobs_mode():
    jobs_api = f"{JENKINS_URL}/api/json?tree=jobs[name,url]"
    jobs_data = safe_get_json(jobs_api)
    jobs = jobs_data.get("jobs", [])

    if not jobs:
        print("No jobs found in Jenkins.")
        return

    print(f"Discovered jobs: {len(jobs)}")

    build_rows = []
    max_ts_seen = last_max_ts

    for job in jobs:
        job_name = job.get("name")
        if not job_name:
            continue

        api = (
            f"{JENKINS_URL}/job/{job_name}/api/json"
            f"?tree=builds[number,result,duration,timestamp,url]{{0,{LOOKBACK}}}"
        )
        try:
            job_info = safe_get_json(api)
        except Exception as e:
            print(f"[WARN] job={job_name} metadata fetch failed: {e}")
            continue

        for b in job_info.get("builds", []):
            row = build_row_from_json(job_name, b)

            if INCREMENTAL_MODE and row["timestamp_ms"] <= last_max_ts:
                continue

            build_rows.append(row)
            if row["timestamp_ms"] > max_ts_seen:
                max_ts_seen = row["timestamp_ms"]

    if not build_rows:
        print("No new builds to process.")
        return

    print(f"Collected build metadata rows: {len(build_rows)}")

    enriched_rows = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(enrich_build_row, r) for r in build_rows]
        for f in as_completed(futures):
            enriched_rows.append(f.result())

    output_dataframe(enriched_rows, OUTPUT_FILE)

    if INCREMENTAL_MODE:
        save_state(max_ts_seen)


# =========================
# Main
# =========================
if TARGET_JOB:
    # fast root-cause mode for a specific job/build
    run_target_mode(TARGET_JOB, TARGET_BUILD, ONLY_FAILED)
else:
    # existing all-jobs behavior
    run_all_jobs_mode()
