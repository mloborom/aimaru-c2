# api/app/routes_auth.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, Request
from sqlalchemy.orm import Session
from sqlalchemy import select
import hmac, hashlib, json
import logging
from typing import Optional

from .deps import get_db
from . import models
from .security import Tokens, hash_pw, verify_pw
from .schemas import LoginReq, LoginResp
from .crypto_runtime import RING

router = APIRouter(prefix="/api", tags=["auth"])
log = logging.getLogger("api.auth")

# --- HKDF config: MUST MATCH YOUR POWERSHELL CLIENT ---
HKDF_SALT = b"MCPv1-salt"  # same salt as client
ENC_INFO  = b"enc"         # same 'info' labels as client
MAC_INFO  = b"mac"
KID       = "v1"           # key id label

def hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    """HKDF-Expand with SHA-256 (includes Extract step)."""
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    t = b""
    okm = b""
    counter = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
        okm += t
        counter += 1
    return okm[:length]

# ---------- Username/password login (dashboard) ----------
@router.post("/auth/token", response_model=LoginResp)
def auth_token(body: LoginReq, resp: Response, db: Session = Depends(get_db)):
    """
    Username/password login.
    - If the users table is empty, bootstrap the first user as admin with provided creds.
    - Sets an HttpOnly refresh cookie for silent renew.
    """
    user = db.query(models.User).filter(models.User.username == body.username).first()

    # Bootstrap first admin if DB has no users yet
    if not user:
        if db.query(models.User).count() == 0:
            user = models.User(username=body.username, password_hash=hash_pw(body.password), role="admin")
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            raise HTTPException(status_code=401, detail="invalid credentials")

    if user.disabled:
        raise HTTPException(status_code=403, detail="user disabled")

    if not verify_pw(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")

    access = Tokens.create_access(str(user.id))
    refresh = Tokens.create_refresh(str(user.id))

    # HttpOnly refresh cookie for /api/auth/refresh
    resp.set_cookie(
        "rtok",
        refresh,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/api/auth/refresh",
    )

    return {
        "access_token": access,
        "user": {
            "id": str(user.id),
            "username": user.username,
            "role": user.role,
            "disabled": user.disabled,
        },
    }

# ---------- Refresh token ----------
@router.post("/auth/refresh", response_model=LoginResp)
def auth_refresh(rtok: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    """
    Exchange HttpOnly refresh cookie for a new access token.
    """
    if not rtok:
        raise HTTPException(status_code=401, detail="no refresh token")

    sub = Tokens.verify_refresh(rtok)
    if not sub:
        raise HTTPException(status_code=401, detail="invalid refresh token")

    user = db.query(models.User).get(sub)
    if not user or user.disabled:
        raise HTTPException(status_code=401, detail="user not allowed")

    access = Tokens.create_access(str(user.id))
    return {
        "access_token": access,
        "user": {
            "id": str(user.id),
            "username": user.username,
            "role": user.role,
            "disabled": user.disabled,
        },
    }

# ---------- MCP client: token by paste-once API key ----------
def _hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    t = b""
    okm = b""
    counter = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
        okm += t
        counter += 1
    return okm[:length]

async def _extract_api_key_any(request: Request) -> tuple[Optional[str], Optional[str], dict]:
    """
    Returns (api_key, client_id, debug_ctx).
    Accept api_key from:
      - Authorization: ApiKey <token>  (preferred)
      - Authorization: Bearer ak_...
      - X-API-Key: <token>
      - ?api_key=...
      - JSON body: {"api_key":"..."}, or raw string "ak_..."
      - form fields: api_key|token|key
    Accept client_id from:
      - X-MCP-ClientId header
      - ?client_id=...
      - JSON body: {"client_id":"..."}
      - form fields: client_id
    """
    ctx = {
        "path": str(request.url),
        "auth_hdr": bool(request.headers.get("authorization")),
        "x_api_key_hdr": bool(request.headers.get("x-api-key")),
        "x_client_hdr": bool(request.headers.get("x-mcp-clientid")),
        "query_api_key": False,
        "query_client_id": False,
        "json_present": False,
        "form_present": False,
        "raw_len": 0,
        "auth_scheme": None,
    }

    token: Optional[str] = None
    client_id: Optional[str] = None

    # Headers
    auth = request.headers.get("authorization")
    if auth:
        parts = auth.strip().split(None, 1)
        if len(parts) == 2:
            scheme, value = parts[0].lower(), parts[1].strip()
            ctx["auth_scheme"] = scheme
            if scheme in ("apikey", "key"):
                token = value
            elif scheme == "bearer" and value.startswith("ak_"):
                token = value

    if not token:
        xk = request.headers.get("x-api-key")
        if xk:
            token = xk.strip()

    xcid = request.headers.get("x-mcp-clientid")
    if xcid:
        client_id = xcid.strip()

    # Query
    q_api = request.query_params.get("api_key")
    if q_api:
        ctx["query_api_key"] = True
        if not token:
            token = q_api.strip()

    q_cid = request.query_params.get("client_id")
    if q_cid:
        ctx["query_client_id"] = True
        if not client_id:
            client_id = q_cid.strip()

    # Body (read raw once)
    body = await request.body()
    ctx["raw_len"] = len(body or b"")
    if body:
        # Try JSON
        try:
            data = json.loads(body.decode("utf-8", "ignore"))
            ctx["json_present"] = True
            if isinstance(data, str) and data.startswith("ak_"):
                if not token:
                    token = data.strip()
            elif isinstance(data, dict):
                if not token:
                    for k in ("api_key", "token", "key"):
                        v = data.get(k)
                        if isinstance(v, str) and v:
                            token = v.strip()
                            break
                if not client_id:
                    v = data.get("client_id")
                    if isinstance(v, str) and v:
                        client_id = v.strip()
        except Exception:
            pass

        # Try form
        if token is None or client_id is None:
            try:
                form = await request.form()
                ctx["form_present"] = True
                if token is None:
                    for k in ("api_key", "token", "key"):
                        v = form.get(k)
                        if isinstance(v, str) and v:
                            token = v.strip()
                            break
                if client_id is None:
                    v = form.get("client_id")
                    if isinstance(v, str) and v:
                        client_id = v.strip()
            except Exception:
                pass

        # Raw text fallback (token only)
        if token is None:
            raw = body.decode("utf-8", "ignore").strip()
            if raw.startswith("ak_"):
                token = raw

    return token, client_id, ctx

@router.post("/auth/token-by-apikey")
async def token_by_apikey(
    request: Request,
    db: Session = Depends(get_db),
):
    api_key, client_id, ctx = await _extract_api_key_any(request)

    log.info("[apikey] incoming path=%s auth=%s xkey=%s xcid=%s q_api=%s q_cid=%s json=%s form=%s raw=%s",
             ctx["path"], ctx["auth_scheme"], ctx["x_api_key_hdr"], ctx["x_client_hdr"],
             ctx["query_api_key"], ctx["query_client_id"],
             ctx["json_present"], ctx["form_present"], ctx["raw_len"])

    if not api_key:
        raise HTTPException(400, detail="missing api_key")
    if not client_id:
        raise HTTPException(400, detail="missing client_id")

    # Optional: strictly verify token with your DB helper (uncomment if desired)
    # from .security_api_keys import verify_api_key
    # if "." not in api_key or not api_key.startswith("ak_"):
    #     raise HTTPException(400, "invalid api_key format")
    # kid, secret = api_key.split(".", 1)
    # row = verify_api_key(db, kid, secret)
    # if not row:
    #     raise HTTPException(401, "invalid api_key")

    # Ensure service user exists (or use the row.user_id above if verifying)
    svc_username = "mcp-client"
    user = db.query(models.User).filter(models.User.username == svc_username).first()
    if not user:
        user = models.User(username=svc_username, password_hash=hash_pw("disabled"), role="operator", disabled=False)
        db.add(user); db.commit(); db.refresh(user)

    access = Tokens.create_access(str(user.id))

    # Derive session keys (MUST match client)
    ikm = api_key.encode("utf-8")
    enc_key = hkdf_sha256(ikm, HKDF_SALT, ENC_INFO, 32)
    mac_key = hkdf_sha256(ikm, HKDF_SALT, MAC_INFO, 32)

    # Register keys for this client in the in-memory ring
    RING.put(client_id, KID, enc_key, mac_key)
    log.info("[apikey] ring.put cid=%s kid=%s", client_id, KID)

    return {"access_token": access, "kid": KID}
