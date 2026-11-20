"""Login: password hashing, sign-in tokens, and who may create an account.

Passwords are never stored. Only a scrypt hash is kept: a slow, salted hash,
so even someone who copies the database cannot read or quickly guess the
passwords. (scrypt is in Python's standard library, nothing to install.)

After signing in, the browser gets a TOKEN: "user id . expiry time . HMAC
signature". The signature is made with SECRET_KEY, which only the server
knows, so a token cannot be changed or forged. The browser sends it with
every request ("Authorization: Bearer <token>").

Who may create an account: the FIRST account can always be created (it is
the owner). After that, sign-up is closed unless ALLOW_SIGNUP=true, so a
deployed BugSense cannot be used by strangers.
"""

import base64
import hashlib
import hmac
import os
import secrets
import time

from sqlalchemy import func, select

from app.models import User

TOKEN_DAYS = 7
SCRYPT = {"n": 2**14, "r": 8, "p": 1}  # standard cost settings for scrypt

# Without SECRET_KEY a random key is made at start-up: it works, but everyone
# has to sign in again after a restart. A deployment always sets SECRET_KEY.
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password, stored):
    try:
        method, salt, digest = stored.split("$")
    except ValueError:
        return False  # for example the old demo user's "!": it can never sign in
    if method != "scrypt":
        return False
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **SCRYPT)
    # compare_digest takes the same time whatever the input (no timing hints)
    return hmac.compare_digest(candidate.hex(), digest)


def _sign(text):
    return hmac.new(SECRET_KEY.encode(), text.encode(), hashlib.sha256).hexdigest()


def make_token(user_id, days=TOKEN_DAYS):
    expires = int(time.time()) + days * 86400
    payload = f"{user_id}.{expires}"
    return base64.urlsafe_b64encode(f"{payload}.{_sign(payload)}".encode()).decode()


def read_token(token):
    """The user id in a valid, unexpired token, or None."""
    try:
        user_id, expires, signature = base64.urlsafe_b64decode(token.encode()).decode().split(".")
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(signature, _sign(f"{user_id}.{expires}")):
        return None
    if int(expires) < time.time():
        return None
    return int(user_id)


def real_users(db):
    """Accounts that can sign in (the old built-in demo user cannot)."""
    return db.scalar(select(func.count()).select_from(User).where(User.password_hash.startswith("scrypt$")))


def signup_open(db):
    return real_users(db) == 0 or os.getenv("ALLOW_SIGNUP", "").lower() == "true"


def ingest_token():
    """When INGEST_TOKEN is set, OpenTelemetry senders must present it."""
    return os.getenv("INGEST_TOKEN", "").strip()
