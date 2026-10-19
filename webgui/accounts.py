import os
import sqlite3
from pathlib import Path

from auth import hash_password, verify_password

DATA_DIR = Path(__file__).resolve().parent / "data"
DATABASE = DATA_DIR / "accounts.db"


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(DATA_DIR, 0o700)

    db = sqlite3.connect(DATABASE, timeout=10)
    db.execute("""
        CREATE TABLE IF NOT EXISTS administrators (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL
        )
    """)
    db.commit()

    if DATABASE.exists():
        os.chmod(DATABASE, 0o600)

    return db


def admin_exists():
    with connect() as db:
        return db.execute(
            "SELECT 1 FROM administrators LIMIT 1"
        ).fetchone() is not None


def create_admin(username, password):
    username = username.strip()

    if not 3 <= len(username) <= 32:
        raise ValueError("Username must be 3-32 characters")

    if not username.isascii() or not all(
        c.isalnum() or c in "_-" for c in username
    ):
        raise ValueError("Username contains invalid characters")

    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")

    password_hash = hash_password(password)

    with connect() as db:
        # Atomic first-admin creation, including concurrent requests.
        db.execute("BEGIN IMMEDIATE")

        if db.execute(
            "SELECT 1 FROM administrators LIMIT 1"
        ).fetchone():
            raise ValueError("Administrator already configured")

        db.execute(
            "INSERT INTO administrators (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )


def authenticate(username, password):
    with connect() as db:
        row = db.execute(
            "SELECT password_hash FROM administrators WHERE username = ?",
            (username,),
        ).fetchone()

    if row is None:
        return False

    return verify_password(password, row[0])



def get_admin_session_version(username):
    """Return a fingerprint tied to the administrator's password."""
    import hashlib

    with connect() as db:
        row = db.execute(
            "SELECT password_hash FROM administrators WHERE username = ?",
            (username,),
        ).fetchone()

    if row is None:
        return None

    return hashlib.sha256(row[0].encode()).hexdigest()
