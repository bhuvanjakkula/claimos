import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import User

SECRET_KEY = "claimos-cold-chain-secure-token-secret-key-2026"


def hash_password(password: str) -> str:
    salt = "claimos_salt_9981"
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return key.hex()


def verify_password(password: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_password(password), hashed)


def sign_token(user_id: int, email: str) -> str:
    payload = json.dumps({"uid": user_id, "em": email})
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_token(token: str) -> Optional[int]:
    try:
        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            return None
        payload, sig = parts
        expected_sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        data = json.loads(payload)
        return int(data.get("uid"))
    except Exception:
        return None


def get_current_user(request: Request, db: Session) -> Optional[User]:
    token = request.cookies.get("claimos_session")
    if not token:
        return None
    uid = verify_token(token)
    if not uid:
        return None
    return db.get(User, uid)


def set_user_cookie(response: Response, user: User) -> None:
    token = sign_token(user.id, user.email)
    response.set_cookie(
        key="claimos_session",
        value=token,
        httponly=True,
        max_age=30 * 24 * 3600,
        samesite="lax"
    )


def clear_user_cookie(response: Response) -> None:
    response.delete_cookie("claimos_session")
