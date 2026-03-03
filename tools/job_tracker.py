"""
tools/job_tracker.py
Single source of truth for all job state and API usage logging.
Every other tool calls into this module.
"""

import csv
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
JOBS_CSV = BASE_DIR / "jobs.csv"
API_LOG  = BASE_DIR / ".tmp" / "api_usage_log.csv"

JOBS_HEADERS = [
    "job_id", "client_handle", "brief_summary", "poster_size",
    "brand_dna_version", "prompt_used", "variations", "status",
    "re_edit_count", "total_cost_usd", "created_at", "approved_at",
    "parent_job_id", "output_paths"
]

API_LOG_HEADERS = [
    "timestamp", "job_id", "service", "model_or_endpoint",
    "call_type", "units_used", "estimated_cost_usd", "notes"
]


def _ensure_jobs_csv():
    """Create jobs.csv with headers if it doesn't exist."""
    if not JOBS_CSV.exists():
        JOBS_CSV.parent.mkdir(parents=True, exist_ok=True)
        with open(JOBS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=JOBS_HEADERS)
            writer.writeheader()


def _ensure_api_log():
    """Create api_usage_log.csv with headers if it doesn't exist."""
    API_LOG.parent.mkdir(parents=True, exist_ok=True)
    if not API_LOG.exists():
        with open(API_LOG, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=API_LOG_HEADERS)
            writer.writeheader()


def generate_job_id() -> str:
    """Returns a short job ID: JS-YYYYMMDD-XXXXXX"""
    now = datetime.now(timezone.utc)
    return f"JS-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def create_job(
    client_handle: str,
    brief_summary: str,
    poster_size: str,
    parent_job_id: str | None = None
) -> str:
    """
    Appends a new row to jobs.csv with status=pending.
    Returns the new job_id.
    """
    _ensure_jobs_csv()
    job_id = generate_job_id()
    now = datetime.now(timezone.utc).isoformat()

    row = {h: "" for h in JOBS_HEADERS}
    row.update({
        "job_id": job_id,
        "client_handle": client_handle.lstrip("@"),
        "brief_summary": brief_summary[:200],
        "poster_size": poster_size,
        "status": "pending",
        "re_edit_count": "0",
        "total_cost_usd": "0.00",
        "created_at": now,
        "parent_job_id": parent_job_id or "",
    })

    with open(JOBS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=JOBS_HEADERS)
        writer.writerow(row)

    return job_id


def update_job(job_id: str, **fields) -> None:
    """
    Updates specific fields on an existing job row.
    Uses atomic file replacement to prevent corruption on concurrent writes.
    """
    _ensure_jobs_csv()
    rows = []
    found = False

    with open(JOBS_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["job_id"] == job_id:
                row.update({k: str(v) for k, v in fields.items()})
                found = True
            rows.append(row)

    if not found:
        return

    tmp_path = Path(str(JOBS_CSV) + ".tmp")
    try:
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=JOBS_HEADERS)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp_path, JOBS_CSV)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def get_job(job_id: str) -> dict | None:
    """Returns a job dict by job_id, or None if not found."""
    _ensure_jobs_csv()
    with open(JOBS_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["job_id"] == job_id:
                return dict(row)
    return None


def get_all_jobs() -> list[dict]:
    """Returns all jobs from jobs.csv, newest first."""
    _ensure_jobs_csv()
    rows = []
    with open(JOBS_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return list(reversed(rows))


def log_api_call(
    job_id: str,
    service: str,
    model_or_endpoint: str,
    call_type: str,
    units_used: int | float,
    estimated_cost_usd: float,
    notes: str = ""
) -> None:
    """
    Appends one row to .tmp/api_usage_log.csv.
    service: "gemini" | "pollinations" | "instaloader"
    call_type: "vision_analysis" | "image_generation" | "profile_scrape"
    """
    _ensure_api_log()
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "job_id": job_id,
        "service": service,
        "model_or_endpoint": model_or_endpoint,
        "call_type": call_type,
        "units_used": str(units_used),
        "estimated_cost_usd": f"{estimated_cost_usd:.4f}",
        "notes": notes,
    }
    with open(API_LOG, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=API_LOG_HEADERS)
        writer.writerow(row)


def get_api_usage_today(service: str) -> int:
    """Returns count of API calls for a given service today. Used for rate limit checks."""
    if not API_LOG.exists():
        return 0
    today = datetime.now(timezone.utc).date().isoformat()
    count = 0
    with open(API_LOG, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("service") == service and row.get("timestamp", "").startswith(today):
                count += 1
    return count
