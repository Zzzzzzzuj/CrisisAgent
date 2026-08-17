import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import User
from backend.db.session import get_db_session


ROLE_OPERATOR = "operator"
ROLE_LEGAL_REVIEWER = "legal_reviewer"
ROLE_ADMIN = "admin"
VALID_ROLES = {ROLE_OPERATOR, ROLE_LEGAL_REVIEWER, ROLE_ADMIN}
REVIEW_ROLES = {ROLE_LEGAL_REVIEWER, ROLE_ADMIN}

_security = HTTPBearer(auto_error=False)


def is_auth_enabled() -> bool:
    return os.getenv("AUTH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256$120000${salt}${base64.urlsafe_b64encode(digest).decode('ascii')}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt, encoded_digest = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
    expected = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
    return hmac.compare_digest(digest, expected)


def create_access_token(user: User, expires_minutes: int | None = None) -> str:
    expires_minutes = expires_minutes or int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "480"))
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return _encode_jwt(payload, _get_secret_key())


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def create_user(db: Session, username: str, password: str, role: str) -> User:
    if role not in VALID_ROLES:
        raise ValueError(f"Unsupported role: {role}")
    user = User(username=username, password_hash=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_auth_db_session():
    if not is_auth_enabled():
        yield None
        return
    yield from get_db_session()


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_security)],
    db: Annotated[Session | None, Depends(get_auth_db_session)],
) -> dict | None:
    if not is_auth_enabled():
        return None
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    payload = _decode_jwt(credentials.credentials, _get_secret_key())
    if db is None:
        raise HTTPException(status_code=500, detail="Auth database session is unavailable.")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found.")
    return user_to_claims(user)


def require_reviewer(current_user: Annotated[dict | None, Depends(get_current_user)]) -> dict | None:
    if not is_auth_enabled():
        return None
    if current_user is None or current_user.get("role") not in REVIEW_ROLES:
        raise HTTPException(status_code=403, detail="Reviewer role required.")
    return current_user


def user_to_claims(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
    }


def _get_secret_key() -> str:
    secret = os.getenv("SECRET_KEY", "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="SECRET_KEY is required when AUTH_ENABLED=true.")
    return secret


def _encode_jwt(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = ".".join(
        [
            _b64url_json(header),
            _b64url_json(payload),
        ]
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def _decode_jwt(token: str, secret: str) -> dict:
    try:
        header_part, payload_part, signature_part = token.split(".", 2)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token.") from exc
    signing_input = f"{header_part}.{payload_part}"
    expected_signature = _b64url(
        hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(signature_part, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid token signature.")
    payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=401, detail="Token expired.")
    if payload.get("role") not in VALID_ROLES:
        raise HTTPException(status_code=401, detail="Invalid role.")
    return payload


def _b64url_json(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _b64url(raw)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode((raw + padding).encode("ascii"))
