# api/app/security_apikeys.py
from __future__ import annotations
import secrets, string
from datetime import datetime
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from .models import ApiKey

# Keep a tiny, local CryptContext to AVOID importing security.py (prevents circular imports)
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

_ALPH = string.ascii_uppercase + string.digits

def gen_key_id(n: int = 6) -> str:                 # short public piece
    return "ak_" + "".join(secrets.choice(_ALPH) for _ in range(n))

def gen_key_secret(n: int = 32) -> str:            # long secret part
    return secrets.token_urlsafe(n)

def make_api_key_full(key_id: str, secret: str) -> str:
    # final token shown once to the user
    return f"{key_id}.{secret}"

def create_api_key(db: Session, user_id: str, label: str | None = None, expires_at=None):
    """
    Returns (row, paste_once_token)
    """
    key_id = gen_key_id()
    secret = gen_key_secret()
    secret_hash = _pwd.hash(secret)

    row = ApiKey(
        user_id=user_id,
        key_id=key_id,
        secret_hash=secret_hash,
        label=label,
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, make_api_key_full(key_id, secret)

def verify_api_key(db: Session, full_token: str) -> ApiKey | None:
    """
    Validate "ak_xxxxxx.secret" → return ApiKey row if valid (and update last_used_at), else None.
    """
    if "." not in full_token:
        return None
    key_id, secret = full_token.split(".", 1)
    row = db.query(ApiKey).filter(ApiKey.key_id == key_id, ApiKey.revoked == False).first()
    if not row:
        return None
    if row.expires_at and row.expires_at < datetime.utcnow():
        return None
    if not _pwd.verify(secret, row.secret_hash):
        return None
    row.last_used_at = datetime.utcnow()
    db.commit()
    return row
