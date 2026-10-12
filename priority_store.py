import json
import os
import tempfile
from pathlib import Path

STORE = Path("/opt/nexus-requests/istate/priority_requests.json")


def load_jobs():
    if not STORE.exists():
        return {}

    with STORE.open("r", encoding="utf-8") as file:
        jobs = json.load(file)

    if not isinstance(jobs, dict):
        raise ValueError("Invalid priority tracking file")

    return jobs


def save_jobs(jobs):
    STORE.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        prefix=".priority-",
        dir=STORE.parent,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(jobs, file, indent=2, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())

        os.chmod(temp_path, 0o600)
        os.replace(temp_path, STORE)

    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def add_job(request_id, media_type, media_id, **details):
    jobs = load_jobs()
    key = str(request_id)

    if key in jobs:
        raise ValueError(f"Request #{request_id} is already tracked")

    jobs[key] = {
        "request_id": int(request_id),
        "media_type": media_type,
        "media_id": int(media_id),
        "status": "waiting",
        **details,
    }

    save_jobs(jobs)
    return jobs[key]


def update_job(request_id, **changes):
    jobs = load_jobs()
    key = str(request_id)

    if key not in jobs:
        raise KeyError(f"Request #{request_id} is not tracked")

    jobs[key].update(changes)
    save_jobs(jobs)
    return jobs[key]


def cancel_job(request_id):
    jobs = load_jobs()
    key = str(request_id)

    if key not in jobs:
        return False

    jobs[key]["status"] = "cancelled"
    save_jobs(jobs)
    return True
from datetime import datetime, timezone

ALLOWED_TRANSITIONS = {
    "waiting": {"processing", "cancelled"},
    "processing": {"completed", "failed"},
    "failed": {"waiting"},
    "completed": set(),
    "cancelled": set(),
}


def transition_job(request_id, new_status, **details):
    jobs = load_jobs()
    key = str(request_id)

    if key not in jobs:
        raise KeyError(f"Request #{request_id} is not tracked")

    job = jobs[key]
    old_status = job["status"]

    allowed = ALLOWED_TRANSITIONS.get(old_status, set())

    if new_status not in allowed:
        raise ValueError(
            f"Invalid transition: {old_status} -> {new_status}"
        )

    job["status"] = new_status
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    job.update(details)

    # Prevent details from overriding the validated status.
    job["status"] = new_status

    save_jobs(jobs)
    return job

def find_interrupted_jobs():
    """
    Find priority jobs left in processing state.

    Does not retry, modify, or restart downloads.
    """
    jobs = load_jobs()

    return {
        request_id: job
        for request_id, job in jobs.items()
        if job.get("status") == "processing"
    }
