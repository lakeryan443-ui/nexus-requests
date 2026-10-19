import os
import secrets
from pathlib import Path

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from pwdlib import PasswordHash

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SECRET_FILE = DATA_DIR / "session.key"

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    return password_hasher.verify(password, stored_hash)


def get_session_secret() -> str:
    DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

    if SECRET_FILE.exists():
        return SECRET_FILE.read_text().strip()

    secret = secrets.token_urlsafe(48)

    fd = os.open(
        SECRET_FILE,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )

    with os.fdopen(fd, "w") as file:
        file.write(secret)

    return secret


def get_serializer():
    return URLSafeTimedSerializer(
        get_session_secret(),
        salt="nexus-requests-session",
    )


def create_session(session_data: dict) -> str:
    return get_serializer().dumps(session_data)


def verify_session(token: str, max_age: int = 86400):
    try:
        return get_serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
