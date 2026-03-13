from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from .config import JWT_SECRET, REFRESH_SECRET

# bcrypt via passlib (pin: passlib[bcrypt]==1.7.4, bcrypt==3.2.2)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_pw(password: str) -> str:
    return pwd.hash(password)

def verify_pw(password: str, password_hash: str) -> bool:
    try:
        return pwd.verify(password, password_hash)
    except Exception:
        return False

ACCESS_TTL = timedelta(minutes=60)
REFRESH_TTL = timedelta(days=7)
ALG = "HS256"

class Tokens:
    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def create_access(sub: str) -> str:
        now = Tokens._now()
        return jwt.encode(
            {"sub": sub, "iat": int(now.timestamp()), "exp": int((now+ACCESS_TTL).timestamp()), "typ": "access"},
            JWT_SECRET, algorithm=ALG
        )

    @staticmethod
    def create_refresh(sub: str) -> str:
        now = Tokens._now()
        return jwt.encode(
            {"sub": sub, "iat": int(now.timestamp()), "exp": int((now+REFRESH_TTL).timestamp()), "typ": "refresh"},
            REFRESH_SECRET, algorithm=ALG
        )

    @staticmethod
    def verify_access(tok: str) -> Optional[str]:
        try:
            data = jwt.decode(tok, JWT_SECRET, algorithms=[ALG])
            return str(data["sub"]) if data.get("typ") == "access" else None
        except (JWTError, Exception):
            return None

    @staticmethod
    def verify_refresh(tok: str) -> Optional[str]:
        try:
            data = jwt.decode(tok, REFRESH_SECRET, algorithms=[ALG])
            return str(data["sub"]) if data.get("typ") == "refresh" else None
        except (JWTError, Exception):
            return None
