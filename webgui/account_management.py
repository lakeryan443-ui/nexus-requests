"""Authenticated administrator credential changes."""

import secrets
import sqlite3

from accounts import connect
from auth import hash_password, verify_password


def change_credentials(username, current_password, *,
                       new_username=None, new_password=None):
    if not current_password:
        raise ValueError("Current password is required")

    if new_username is None and new_password is None:
        raise ValueError("No account changes requested")

    if new_username is not None:
        new_username = new_username.strip()
        if not 3 <= len(new_username) <= 32:
            raise ValueError("Username must be 3-32 characters")
        if not new_username.isascii() or not all(
            c.isalnum() or c in "_-" for c in new_username
        ):
            raise ValueError("Username contains invalid characters")

    if new_password is not None and len(new_password) < 12:
        raise ValueError("Password must be at least 12 characters")

    with connect() as db:
        db.execute("BEGIN IMMEDIATE")

        row = db.execute(
            "SELECT id, password_hash FROM administrators "
            "WHERE username = ?",
            (username,),
        ).fetchone()

        if row is None or not verify_password(current_password, row[1]):
            raise ValueError("Current password is incorrect")

        if new_password is not None:
            if secrets.compare_digest(current_password, new_password):
                raise ValueError("New password must differ from current password")
            password_hash = hash_password(new_password)
        else:
            password_hash = row[1]

        try:
            db.execute(
                "UPDATE administrators SET username = ?, password_hash = ? "
                "WHERE id = ?",
                (new_username if new_username is not None else username,
                 password_hash, row[0]),
            )
        except sqlite3.IntegrityError:
            raise ValueError("Username is already in use") from None

    return True
