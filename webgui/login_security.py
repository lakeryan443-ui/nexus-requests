import threading
import time
from collections import defaultdict

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 900

_attempts = defaultdict(list)
_lock = threading.Lock()


def is_blocked(ip):
    now = time.monotonic()

    with _lock:
        attempts = [
            t for t in _attempts[ip]
            if now - t < WINDOW_SECONDS
        ]

        if attempts:
            _attempts[ip] = attempts
        else:
            _attempts.pop(ip, None)

        return len(attempts) >= MAX_ATTEMPTS


def record_failure(ip):
    now = time.monotonic()

    with _lock:
        _attempts[ip] = [
            t for t in _attempts[ip]
            if now - t < WINDOW_SECONDS
        ]
        _attempts[ip].append(now)


def clear_failures(ip):
    with _lock:
        _attempts.pop(ip, None)
