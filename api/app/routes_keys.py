# api/app/routes_keys.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Header,
    Body,
    Form,
    Query,
    status
)
from sqlalchemy.orm import Session
from sqlalchemy import select

from .deps import get_db
from .auth_dep import require_role
from . import models
from .schemas import MCPKey, MCPKeyCreate, MCPKeyCreateResp
from .security_api_keys import create_api_key, verify_api_key
from .security import Tokens
from .crypto_runtime import RING
import hmac, hashlib

import logging
log = logging.getLogger("api.auth")

router = APIRouter(prefix="/api/keys", tags=["keys"])

def _sanitize_token(tok: str) -> str:
    if not tok:
        return ""
    if len(tok) <= 8:
        return "***"
    return tok[:4] + "…" + tok[-4:]

async def _extract_api_key_any(request: Request) -> tuple[Optional[str], dict]:
    """
    Try *everywhere* and return (token, debug_context).
    We do not raise here; caller decides.
    """
    ctx: dict = {
        "path": str(request.url),
        "client": getattr(request.client, "host", None),
        "auth_hdr_present": False,
        "auth_scheme": None,
        "x_api_key_present": False,
        "query_present": False,
        "json_present": False,
        "form_present": False,
        "raw_body_len": 0,
    }

    token: Optional[str] = None

    # Headers
    auth = request.headers.get("authorization")
    xk   = request.headers.get("x-api-key")
    ctx["auth_hdr_present"] = bool(auth)
    ctx["x_api_key_present"] = bool(xk)

    # Authorization header: accept "ApiKey <...>" or "Bearer <ak_...>"
    if auth:
        parts = auth.strip().split(None, 1)
        if len(parts) == 2:
            scheme, value = parts[0].lower(), parts[1].strip()
            ctx["auth_scheme"] = scheme
            if scheme in ("apikey", "key"):
                token = value
            elif scheme == "bearer" and value.startswith("ak_"):
                token = value

    # X-API-Key header
    if not token and xk:
        token = xk.strip()

    # Query param ?api_key=...
    q = request.query_params.get("api_key")
    if q:
        ctx["query_present"] = True
        if not token:
            token = q.strip()

    # Body: try JSON, form, and raw
    try:
        body = await request.body()
        ctx["raw_body_len"] = len(body or b"")
    except Exception:
        body = b""

    # Try JSON
    if body:
        try:
            data = await request.json()
            ctx["json_present"] = True
            if not token:
                if isinstance(data, str):
                    token = data.strip()
                elif isinstance(data, dict):
                    for k in ("api_key", "token", "key"):
                        if k in data and isinstance(data[k], str):
                            token = data[k].strip()
                            break
        except Exception:
            pass

    # Try form
    if body and not token:
        try:
            form = await request.form()
            ctx["form_present"] = True
            for k in ("api_key", "token", "key"):
                if k in form and isinstance(form[k], str):
                    token = form[k].strip()
                    break
        except Exception:
            pass

    # Last chance: raw text body
    if body and not token:
        try:
            raw = body.decode("utf-8", errors="ignore").strip()
            if raw.startswith("ak_"):
                token = raw
        except Exception:
            pass

    return token, ctx



def row_to_mcpkey(row: models.ApiKey) -> MCPKey:
    return MCPKey(
        id=str(row.id),
        key_id=row.key_id,
        label=row.label,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        expires_at=row.expires_at,
        revoked=row.revoked,
    )

@router.get("", response_model=List[MCPKey])
def list_my_keys(
    user=Depends(require_role()), 
    db: Session = Depends(get_db)
):
    stmt = (
        select(models.ApiKey)
        .where(models.ApiKey.user_id == user.id)
        .order_by(models.ApiKey.created_at.desc())
    )
    rows = db.execute(stmt).scalars().all()
    return [row_to_mcpkey(r) for r in rows]

@router.post("", response_model=MCPKeyCreateResp)
def create_my_key(
    body: MCPKeyCreate, 
    user=Depends(require_role()), 
    db: Session = Depends(get_db)
):
    # Optional TTL → expires_at
    expires_at = None
    if body.ttl_minutes is not None:
        try:
            ttl = int(body.ttl_minutes)
            if ttl > 0:
                expires_at = datetime.utcnow() + timedelta(minutes=ttl)
        except Exception:
            # ignore bad TTLs; create without expiration
            pass

    row, paste_once_token = create_api_key(
        db=db,
        user_id=str(user.id),
        label=body.label,
        expires_at=expires_at,
    )
    return {"token": paste_once_token, "key": row_to_mcpkey(row)}

@router.delete("/{key_db_id}", response_model=dict)
def revoke_my_key(
    key_db_id: str, 
    user=Depends(require_role()), 
    db: Session = Depends(get_db)
):
    row = db.get(models.ApiKey, key_db_id)
    if not row or str(row.user_id) != str(user.id):
        raise HTTPException(404, "not found")
    if row.revoked:
        return {"ok": True}  # already revoked
    row.revoked = True
    db.commit()
    return {"ok": True}

# --------------------------------------------
# /api/auth/token-by-apikey  (for MCP agents)
# --------------------------------------------
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

def hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    t = b""
    okm = b""
    counter = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
        okm += t
        counter += 1
    return okm[:length]

async def _extract_api_key(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    api_key_body: Optional[str] = Body(default=None),
    api_key_form: Optional[str] = Form(default=None),
) -> Optional[str]:
    # Authorization: ApiKey <token>
    if authorization and authorization.lower().startswith("apikey "):
        return authorization.split(" ", 1)[1].strip()
    # X-API-Key header
    if x_api_key:
        return x_api_key.strip()
    # JSON body: either {"api_key": "..."} or raw string
    if api_key_body:
        if isinstance(api_key_body, str):
            return api_key_body.strip()
        if isinstance(api_key_body, dict) and "api_key" in api_key_body:
            return str(api_key_body["api_key"]).strip()
    # form field
    if api_key_form:
        return api_key_form.strip()
    # try parse JSON manually if not bound
    try:
        data = await request.json()
        if isinstance(data, dict) and "api_key" in data:
            return str(data["api_key"]).strip()
    except Exception:
        pass
    return None

@auth_router.post("/token-by-apikey")
async def token_by_apikey(
    request: Request,
    db: Session = Depends(get_db),
    client_id: Optional[str] = Query(default=None),
    x_client_id: Optional[str] = Header(default=None, alias="X-MCP-ClientId"),
):
    # 1) Extract token from anywhere
    api_key_plain, ctx = await _extract_api_key_any(request)
    # Log *sanitized* context
    log.info("[apikey] incoming %s auth=%s xkey=%s q=%s json=%s form=%s bodyLen=%s",
             ctx.get("path"), ctx.get("auth_scheme"),
             ctx.get("x_api_key_present"), ctx.get("query_present"),
             ctx.get("json_present"), ctx.get("form_present"),
             ctx.get("raw_body_len"))

    if not api_key_plain:
        raise HTTPException(status_code=400, detail="missing api_key (send in Authorization: ApiKey, X-API-Key, ?api_key=, JSON, or form)")

    # 2) Parse "ak_xxx.yyy"
    try:
        if not api_key_plain.startswith("ak_") or "." not in api_key_plain:
            raise ValueError("bad format")
        key_id, secret = api_key_plain.split(".", 1)
        key_id = key_id.strip()
        secret = secret.strip()
        if not key_id or not secret:
            raise ValueError("bad format")
    except Exception:
        log.warning("[apikey] bad format token=%s", _sanitize_token(api_key_plain))
        raise HTTPException(status_code=400, detail="invalid api_key format")

    # 3) Verify
    try:
        row: models.ApiKey | None = verify_api_key(db, key_id, secret)  # type: ignore[name-defined]
    except Exception as e:
        log.exception("[apikey] verify exception: %s", e)
        raise HTTPException(status_code=500, detail="verification error")

    if not row:
        log.info("[apikey] invalid or revoked key_id=%s", key_id)
        raise HTTPException(status_code=401, detail="invalid api key")

    # 4) Update last_used_at
    row.last_used_at = datetime.now(timezone.utc)
    db.commit()

    # 5) Issue access token
    user_id = str(row.user_id)
    access = Tokens.create_access(user_id)

    # 6) Register HKDF keys for result decryption
    try:
        cid = (x_client_id or client_id or "").strip() or None
        ikm = api_key_plain.encode("utf-8")
        salt = b"MCPv1-salt"
        kid = "v1"
        def hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
            prk = hmac.new(salt, ikm, hashlib.sha256).digest()
            t = b""
            okm = b""
            counter = 1
            while len(okm) < length:
                t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
                okm += t
                counter += 1
            return okm[:length]
        enc_key = hkdf_sha256(ikm, salt, b"enc")
        mac_key = hkdf_sha256(ikm, salt, b"mac")
        RING.put(cid, kid, enc_key, mac_key)
        log.info("[apikey] ring.put cid=%s kid=%s", cid or "<none>", kid)
    except Exception as e:
        log.warning("[apikey] ring error: %s", e)

    return {"access_token": access, "token_type": "bearer", "user": {"id": user_id}}

