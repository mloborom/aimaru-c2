# api/app/auth_dep.py
from __future__ import annotations

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Security, HTTPException, Depends
from sqlalchemy.orm import Session

from .deps import get_db
from .security import Tokens
from . import models

bearer = HTTPBearer(auto_error=False)

def require_role(role: str | None = None):
    """
    Dependency that:
      - requires a valid Bearer access token
      - loads the user from DB
      - (optionally) enforces the user's role; admins always pass

    Usage in routes:
        @router.get("/secure")
        def handler(user=Depends(require_role("operator"))):
            ...
    """
    def dep(
        creds: HTTPAuthorizationCredentials = Security(bearer),
        db: Session = Depends(get_db),
    ) -> models.User:
        if not creds:
            raise HTTPException(status_code=401, detail="unauthorized")

        sub = Tokens.verify_access(creds.credentials)
        if not sub:
            raise HTTPException(status_code=401, detail="invalid token")

        user = db.query(models.User).get(sub)
        if not user or user.disabled:
            raise HTTPException(status_code=401, detail="user not allowed")

        if role and user.role not in (role, "admin"):
            raise HTTPException(status_code=403, detail="forbidden")

        return user

    return dep

__all__ = ["require_role"]
