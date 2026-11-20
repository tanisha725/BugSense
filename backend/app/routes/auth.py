"""Sign-up, sign-in, and the checks that protect every other route."""

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


class SignUp(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def lower_case(cls, value):
        return value.strip().lower()


class SignIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=200)


def token_from(request):
    """The token from the Authorization header, or from ?token= (download links
    are plain links, which cannot carry a header)."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.query_params.get("token")


def current_user(request: Request, db: Session = Depends(get_db)):
    """Used by every protected route: the signed-in user, or 401."""
    token = token_from(request)
    user_id = auth.read_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in", headers={"WWW-Authenticate": "Bearer"})
    return user


def ingest_allowed(request: Request):
    """OpenTelemetry senders: free when INGEST_TOKEN is not set, otherwise
    they must send "Authorization: Bearer <INGEST_TOKEN>"."""
    expected = auth.ingest_token()
    if not expected:
        return
    given = token_from(request) or ""
    if not hmac.compare_digest(given, expected):
        raise HTTPException(status_code=401, detail="Wrong or missing ingest token")


def public(user):
    return {"id": user.id, "name": user.name, "email": user.email}


@router.get("/status")
def status(db: Session = Depends(get_db)):
    """What the sign-in page needs to know: can a new account be created?"""
    return {"signup_open": auth.signup_open(db), "has_users": auth.real_users(db) > 0}


@router.post("/signup", status_code=201)
def signup(data: SignUp, db: Session = Depends(get_db)):
    if not auth.signup_open(db):
        raise HTTPException(status_code=403, detail="Sign-up is closed. Ask the owner for an account.")
    if db.scalar(select(func.count()).select_from(User).where(User.email == data.email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(name=data.name.strip(), email=data.email, password_hash=auth.hash_password(data.password))
    db.add(user)
    db.commit()
    return {"token": auth.make_token(user.id), "user": public(user)}


@router.post("/signin")
def signin(data: SignIn, db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(User.email == data.email.strip().lower())).first()
    # The same message for "no such email" and "wrong password", so it does not
    # reveal which emails have an account
    if user is None or not auth.check_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    return {"token": auth.make_token(user.id), "user": public(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return public(user)
