"""Login: sign-up rules, sign-in, tokens, and that every feature is protected."""

import base64

from sqlalchemy import select

from app.models import User
from app.services import auth

OWNER = {"name": "Tanisha", "email": "Owner@Example.com", "password": "correct horse 42"}


def sign_up(client, **changes):
    return client.post("/auth/signup", json={**OWNER, **changes})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_features_need_a_signed_in_user(anonymous_client):
    for path in ("/logs", "/projects", "/incidents", "/monitor", "/tools", "/telemetry/services", "/datasets"):
        assert anonymous_client.get(path).status_code == 401, path
    # These stay open: the health check and the sign-in page's status
    assert anonymous_client.get("/health").status_code == 200
    assert anonymous_client.get("/auth/status").json() == {"signup_open": True, "has_users": False}


def test_first_account_is_the_owner_then_signup_closes(anonymous_client, monkeypatch):
    monkeypatch.delenv("ALLOW_SIGNUP", raising=False)
    first = sign_up(anonymous_client)
    assert first.status_code == 201
    assert first.json()["user"]["email"] == "owner@example.com"  # stored in lower case

    assert anonymous_client.get("/auth/status").json() == {"signup_open": False, "has_users": True}
    second = sign_up(anonymous_client, email="stranger@example.com")
    assert second.status_code == 403 and "closed" in second.json()["detail"]

    monkeypatch.setenv("ALLOW_SIGNUP", "true")
    assert sign_up(anonymous_client, email="teammate@example.com").status_code == 201
    assert sign_up(anonymous_client, email="teammate@example.com").status_code == 409


def test_passwords_are_hashed_not_stored(anonymous_client, session_factory):
    sign_up(anonymous_client)
    with session_factory() as db:
        stored = db.scalar(select(User.password_hash))
    assert OWNER["password"] not in stored and stored.startswith("scrypt$")
    assert auth.check_password(OWNER["password"], stored)
    assert not auth.check_password("wrong password", stored)
    assert not auth.check_password("anything", "!")  # the old demo user can never sign in


def test_sign_in_and_use_the_token(anonymous_client):
    sign_up(anonymous_client)
    wrong = anonymous_client.post("/auth/signin", json={"email": OWNER["email"], "password": "nope nope"})
    unknown = anonymous_client.post("/auth/signin", json={"email": "who@example.com", "password": "nope nope"})
    # The same answer for both, so it does not reveal which emails exist
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]

    token = anonymous_client.post("/auth/signin", json={"email": "owner@example.com", "password": OWNER["password"]}).json()["token"]
    assert anonymous_client.get("/auth/me", headers=bearer(token)).json()["name"] == "Tanisha"
    assert anonymous_client.get("/projects", headers=bearer(token)).status_code == 200
    # Download links cannot send headers, so ?token= works too
    assert anonymous_client.get("/logs/export", params={"token": token}).status_code == 200


def test_tokens_cannot_be_forged_or_used_after_expiry(anonymous_client):
    user_id = sign_up(anonymous_client).json()["user"]["id"]
    assert auth.read_token(auth.make_token(user_id)) == user_id
    assert auth.read_token("not-a-token") is None

    # Someone changes the expiry (or the user id) but cannot make a new signature
    uid, expires, signature = base64.urlsafe_b64decode(auth.make_token(user_id)).decode().split(".")
    for changed in (f"{uid}.{int(expires) + 999999}.{signature}", f"{int(uid) + 1}.{expires}.{signature}"):
        forged = base64.urlsafe_b64encode(changed.encode()).decode()
        assert anonymous_client.get("/auth/me", headers=bearer(forged)).status_code == 401
    expired = auth.make_token(user_id, days=-1)
    assert auth.read_token(expired) is None
    assert anonymous_client.get("/auth/me", headers=bearer(expired)).status_code == 401
    assert auth.read_token(auth.make_token(user_id, days=1)) == user_id


def test_signup_input_is_checked(anonymous_client):
    assert sign_up(anonymous_client, password="short").status_code == 422
    assert sign_up(anonymous_client, email="not-an-email").status_code == 422
    assert sign_up(anonymous_client, name="").status_code == 422


def test_ingest_token_protects_opentelemetry(anonymous_client, monkeypatch):
    body = {"resourceSpans": []}
    assert anonymous_client.post("/v1/traces", json=body).status_code == 200  # no token set: open
    monkeypatch.setenv("INGEST_TOKEN", "s3cret-ingest")
    assert anonymous_client.post("/v1/traces", json=body).status_code == 401
    assert anonymous_client.post("/v1/traces", json=body, headers=bearer("wrong")).status_code == 401
    assert anonymous_client.post("/v1/traces", json=body, headers=bearer("s3cret-ingest")).status_code == 200
