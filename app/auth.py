import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from . import models
from .database import get_db

# On each client VPS set SECRET_KEY to a long random string.
SECRET_KEY = os.getenv("SECRET_KEY", "shopbd-dev-secret-change-me")
ALGORITHM = "HS256"
TOKEN_DAYS = 7

bearer_scheme = HTTPBearer(auto_error=False)


# ---------- password hashing (stdlib pbkdf2, no extra deps) ----------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000).hex()
    return secrets.compare_digest(check, digest)


# ---------- JWT ----------
def create_token(sub: str, role: str) -> str:
    payload = {
        "sub": sub,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ---------- dependencies ----------
def get_current_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.AdminUser:
    if not creds:
        raise HTTPException(401, "Not authenticated")
    payload = decode_token(creds.credentials)
    if not payload or payload.get("role") not in ("admin", "superadmin"):
        raise HTTPException(401, "Admin access required")
    user = db.get(models.AdminUser, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "Admin not found")
    return user


def get_superadmin(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.AdminUser:
    if not creds:
        raise HTTPException(401, "Not authenticated")
    payload = decode_token(creds.credentials)
    if not payload or payload.get("role") != "superadmin":
        raise HTTPException(403, "Super admin access required")
    user = db.get(models.AdminUser, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "Admin not found")
    return user


def get_current_customer(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.Customer:
    if not creds:
        raise HTTPException(401, "Not authenticated")
    payload = decode_token(creds.credentials)
    if not payload or payload.get("role") != "customer":
        raise HTTPException(401, "Customer login required")
    customer = db.get(models.Customer, int(payload["sub"]))
    if not customer:
        raise HTTPException(401, "Customer not found")
    return customer
