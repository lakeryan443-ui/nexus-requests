import secrets
from pathlib import Path

TOKEN_FILE = Path(__file__).resolve().parent / "data" / "setup.token"


def verify_setup_token(token):
    if not isinstance(token, str) or not token:
        return False

    try:
        expected = TOKEN_FILE.read_text().strip()
    except (OSError, UnicodeError):
        return False

    return bool(expected) and secrets.compare_digest(token, expected)


def invalidate_setup_token():
    TOKEN_FILE.unlink(missing_ok=True)
