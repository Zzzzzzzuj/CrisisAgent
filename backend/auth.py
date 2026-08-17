import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from backend.db.models import User
from backend.db.session import get_session_factory


VALID_ROLES = {"operator", "legal_reviewer", "admin"}
REVIEW_ROLES = {"legal_reviewer", "admin"}
_bearer = HTTPBearer(auto_error=False)


def is_auth_enabled() -> bool:
    return os.getenv("AUTH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def hash_password(password: str, salt: bytes | None = None, iterations: int = 120_000) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        _b64encode(salt),
        _b64encode(digest),
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, expected_raw = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = _b64decode(salt_raw)
        expected = _b64decode(expected_raw)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def authenticate_user(username: str, password: str) -> dict | None:
    with get_session_factory()() as db:
        user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            return None
        return serialize_user(user)


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
    }


def create_access_token(user: dict, expires_minutes: int | None = None) -> str:
    secret = _get_secret_key()
    expires_minutes = expires_minutes or int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)).timestamp()),
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = "{}.{}".format(
        _json_b64encode(header),
        _json_b64encode(payload),
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64encode(signature)}"


def decode_access_token(token: str) -> dict:
    try:
        header_raw, payload_raw, signature_raw = token.split(".", 2)
        signing_input = f"{header_raw}.{payload_raw}"
        expected = hmac.new(
            _get_secret_key().encode("utf-8"),
            signing_input.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_b64decode(signature_raw), expected):
            raise ValueError("invalid signature")
        payload = json.loads(_b64decode(payload_raw).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("token expired")
        role = payload.get("role")
        if role not in VALID_ROLES:
            raise ValueError("invalid role")
        return {
            "id": int(payload["sub"]),
            "username": str(payload["username"]),
            "role": role,
        }
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict | None:
    if not is_auth_enabled():
        return None
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return decode_access_token(credentials.credentials)


def require_reviewer(user: dict | None) -> dict | None:
    if not is_auth_enabled():
        return None
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if user.get("role") not in REVIEW_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient role for human review.")
    return user


def can_view_state(user: dict | None, state) -> bool:
    if not is_auth_enabled() or user is None:
        return True
    role = user.get("role")
    if role in {"admin", "legal_reviewer"}:
        return True
    creator = (state.metadata or {}).get("created_by", {})
    return role == "operator" and str(creator.get("id", "")) == str(user.get("id"))


def build_created_by(user: dict | None) -> dict | None:
    if not is_auth_enabled() or user is None:
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
    }


def build_review_identity(user: dict | None, body: dict) -> dict:
    if is_auth_enabled() and user is not None:
        return {
            "reviewer": user["username"],
            "reviewer_id": user["id"],
            "reviewer_username": user["username"],
            "reviewer_role": user["role"],
            "comment": str(body.get("comment", "")),
        }
    reviewer = str(body.get("reviewer", "human"))
    return {
        "reviewer": reviewer,
        "reviewer_id": None,
        "reviewer_username": reviewer,
        "reviewer_role": "",
        "comment": str(body.get("comment", "")),
    }


def _get_secret_key() -> str:
    secret = os.getenv("SECRET_KEY", "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="SECRET_KEY is required when auth is enabled.")
    return secret


def _json_b64encode(data: dict) -> str:
    return _b64encode(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))
