import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

STORE = Path("/opt/nexus-requests-rebuild/istate/priority_requests.json")
@contextmanager
def priority_store_lock():
    """Exclusively lock priority storage across local processes."""
    lock_path = STORE.with_name(STORE.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)

    try:
        with os.fdopen(fd, "r+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception:
        raise

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
    """Create a priority job while preventing concurrent duplicates."""
    with priority_store_lock():
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

        # The initial status must not be overridden by details.
        jobs[key]["status"] = "waiting"

        save_jobs(jobs)
        return jobs[key]

def update_job(request_id, *, expected_status=None, **changes):
    """Update job metadata under a lock, optionally requiring a status."""
    with priority_store_lock():
        jobs = load_jobs()
        key = str(request_id)

        if key not in jobs:
            raise KeyError(f"Request #{request_id} is not tracked")

        if "status" in changes:
            raise ValueError(
                "Use transition_job() for status changes"
            )

        job = jobs[key]

        if expected_status is not None:
            if job.get("status") != expected_status:
                raise ValueError(
                    f"Job status changed: expected {expected_status}, "
                    f"found {job.get('status')}"
                )

        job.update(changes)
        save_jobs(jobs)
        return job

def cancel_job(request_id):
    """Cancel only waiting priority jobs under an exclusive lock."""
    with priority_store_lock():
        jobs = load_jobs()
        key = str(request_id)

        if key not in jobs:
            return False

        if jobs[key].get("status") != "waiting":
            return False

        jobs[key]["status"] = "cancelled"
        jobs[key]["updated_at"] = (
            datetime.now(timezone.utc).isoformat()
        )

        save_jobs(jobs)
        return True
from datetime import datetime, timezone

ALLOWED_TRANSITIONS = {
    "recovery_claimed": set(),
    "waiting": {"processing", "cancelled"},
    "processing": {"completed", "failed"},
    "failed": {"waiting"},
    "completed": set(),
    "cancelled": set(),
}

def transition_job(request_id, new_status, **details):
    """Atomically validate and update a priority job's status."""
    with priority_store_lock():
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

def validate_recovery_job(request_id):
    """Validate that a priority job is eligible for manual recovery."""
    jobs = load_jobs()
    job = jobs.get(str(request_id))

    if job is None:
        return False, "Priority job does not exist."

    if job.get("status") != "processing":
        return False, (
            "Priority job is no longer interrupted "
            f"(status: {job.get('status')})."
        )

    return True, "Priority job is eligible for administrator review."

def claim_recovery_job(request_id, admin_id, action):
    """
    Atomically claim an interrupted job for administrator review.

    Does not approve requests, restart downloads, or cancel torrents.
    """
    if action not in {"continue", "cancel"}:
        raise ValueError("Recovery action must be continue or cancel")

    with priority_store_lock():
        jobs = load_jobs()
        key = str(request_id)
        job = jobs.get(key)

        if job is None:
            return False, "Priority job does not exist."

        if job.get("status") != "processing":
            return False, (
                "Recovery already claimed or job is not interrupted "
                f"(status: {job.get('status')})."
            )

        job["status"] = "recovery_claimed"
        job["recovery_action"] = action
        job["recovery_admin_id"] = str(admin_id)
        job["recovery_claimed_at"] = (
            datetime.now(timezone.utc).isoformat()
        )
        job["updated_at"] = job["recovery_claimed_at"]

        save_jobs(jobs)

        return True, "Recovery job claimed for administrator review."
