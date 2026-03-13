from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from .deps import get_db
from .auth_dep import require_role
from . import models
from .security import hash_pw
from .schemas import UserOut, UserCreate, UserPatch

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/users", response_model=list[UserOut])
def users_list(user=Depends(require_role("admin")), db: Session = Depends(get_db)):
    rows = db.query(models.User).all()
    return [
        {
            "id": str(r.id),
            "username": r.username,
            "role": r.role,
            "disabled": r.disabled,
        }
        for r in rows
    ]


@router.post("/users", response_model=UserOut)
def users_create(body: UserCreate, user=Depends(require_role("admin")), db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == body.username).first():
        raise HTTPException(status_code=400, detail="username exists")

    row = models.User(
        username=body.username,
        password_hash=hash_pw(body.password),
        role=body.role,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "id": str(row.id),
        "username": row.username,
        "role": row.role,
        "disabled": row.disabled,
    }


@router.patch("/users/{uid}", response_model=UserOut)
def users_patch(uid: str, body: UserPatch, user=Depends(require_role("admin")), db: Session = Depends(get_db)):
    row = db.query(models.User).get(uid)
    if not row:
        raise HTTPException(status_code=404, detail="not found")

    if body.role is not None:
        row.role = body.role
    if body.disabled is not None:
        row.disabled = body.disabled

    db.commit()
    db.refresh(row)

    return {
        "id": str(row.id),
        "username": row.username,
        "role": row.role,
        "disabled": row.disabled,
    }


@router.post("/users/{uid}/password")
def users_set_password(uid: str, payload: dict = Body(...), user=Depends(require_role("admin")), db: Session = Depends(get_db)):
    row = db.query(models.User).get(uid)
    if not row:
        raise HTTPException(status_code=404, detail="not found")

    pw = (payload or {}).get("password")
    if not pw:
        raise HTTPException(status_code=400, detail="password required")

    row.password_hash = hash_pw(pw)
    db.commit()
    return {"ok": True}


@router.delete("/users/{uid}")
def users_delete(uid: str, user=Depends(require_role("admin")), db: Session = Depends(get_db)):
    row = db.query(models.User).get(uid)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
