import csv
import os
import psutil
from datetime import datetime, timedelta

CSV_PATH = "utilisation.csv"
WINDOW_MINUTES = 10

def get_live_metrics():
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    mem_percent = (mem.total - mem.available) / mem.total * 100 if mem.total else 0
    return {
        "timestamp": datetime.now().isoformat(),
        "cpu": round(cpu, 2),
        "memory": round(mem_percent, 2),
    }

# Append current sample
row = get_live_metrics()
file_exists = os.path.exists(CSV_PATH)
with open(CSV_PATH, "a", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["timestamp", "cpu", "memory"])
    if not file_exists:
        w.writeheader()
    w.writerow(row)

# Keep only last 10 minutes
cutoff = datetime.now() - timedelta(minutes=WINDOW_MINUTES)
rows_to_keep = []
with open(CSV_PATH, "r", newline="") as f:
    r = csv.DictReader(f)
    fieldnames = r.fieldnames
    for rrow in r:
        try:
            ts = datetime.fromisoformat(rrow["timestamp"])
            if ts >= cutoff:
                rows_to_keep.append(rrow)
        except Exception:
            rows_to_keep.append(rrow)

with open(CSV_PATH, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows_to_keep)
