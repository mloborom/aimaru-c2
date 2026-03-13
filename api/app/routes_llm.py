from __future__ import annotations
from uuid import UUID
import uuid
import json
import logging
from datetime import datetime, timezone

import time
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .deps import get_db
from .auth_dep import require_role
from . import models 
from .models import Instruction, LLMConfig, ClientChatSession, ChatMessage, User

# Setup logging
logger = logging.getLogger(__name__)

# Alias for backward compatibility
LlmConfig = models.LLMConfig
ClientChatMessage = models.ChatMessage  # Use ChatMessage from models

router = APIRouter(prefix="/api/llm", tags=["llm"])

# ---------- helpers ----------
def now_utc():
    return datetime.now(timezone.utc)

def call_openai_chat(api_key: str, model: str, messages: list[dict], temperature: float = 0.2, max_retries: int = 1):
    import json, requests
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "tools": [{
            "type": "function",
            "function": {
                "name": "issue_command",
                "description": "Queue a PowerShell command to be executed by the specified MCP client.",
                "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
            },
        }],
        "tool_choice": "auto",
    }

    attempt = 0
    while True:
        attempt += 1
        try:
            r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        except requests.exceptions.RequestException as e:
            raise HTTPException(502, f"OpenAI request error: {e}")

        ct = r.headers.get("content-type", "")
        body_txt = r.text

        if r.status_code == 429:
            # extract provider message
            try:
                j = r.json()
                prov_msg = j.get("error", {}).get("message") or "rate limit / insufficient quota"
            except Exception:
                prov_msg = "rate limit / insufficient quota"
            # log and decide retry
            logger.error(f"[llm][err] OpenAI 429 :: {prov_msg}")
            retry_after = r.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else 2.0
            if attempt <= max_retries:
                time.sleep(wait)
                continue
            # bubble a **429** to the UI so it can show a clear message
            raise HTTPException(429, f"LLM quota/rate limit: {prov_msg}")

        if r.status_code >= 400:
            # other provider errors -> 502 with trimmed body
            snippet = body_txt[:500].replace("\n", " ")
            logger.error(f"[llm][err] OpenAI {r.status_code} {r.reason} :: {snippet}")
            try:
                j = r.json()
                specific = j.get("error", {}).get("message")
                msg = f"LLM provider error {r.status_code}: {r.reason}"
                if specific:
                    msg += f" – {specific}"
            except Exception:
                msg = f"LLM provider error {r.status_code}: {r.reason}"
            raise HTTPException(502, msg)

        try:
            j = r.json()
        except Exception:
            logger.error(f"[llm][err] Non-JSON response: ct={ct} head={body_txt[:200]}")
            raise HTTPException(502, "LLM returned non-JSON response")

        if not j.get("choices"):
            logger.error(f"[llm][err] No choices in response: {j}")
            raise HTTPException(502, "LLM returned no choices")

        return j["choices"][0]

# ---------- admin: configs ----------
@router.get("/configs")
def list_configs(
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """List LLM configurations for the current user"""
    try:
        configs = db.execute(
            select(LLMConfig).where(
                # Filter by owner if owner_user_id is set, otherwise show all
                (LLMConfig.owner_user_id == user.id) | (LLMConfig.owner_user_id.is_(None))
            ).order_by(LLMConfig.created_at.desc())
        ).scalars().all()
        
        return {
            "configs": [
                {
                    "id": str(config.id),
                    "name": config.name,
                    "provider": config.provider,
                    "model": config.model,
                    "temperature": config.temperature,
                    "is_active": config.is_active,
                    "created_at": config.created_at.isoformat() if config.created_at else None,
                    "owner_user_id": str(config.owner_user_id) if config.owner_user_id else None
                }
                for config in configs
            ]
        }
    except Exception as e:
        logger.error(f"[llm] Failed to list configs: {e}")
        return {"configs": []}

@router.post("/configs")
def create_config(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Create a new LLM configuration"""
    name = payload.get("name")
    provider = payload.get("provider")
    model = payload.get("model")
    api_key = payload.get("api_key")
    temperature = payload.get("temperature", 0.2)
    
    # Handle both 'active' and 'is_active' from frontend
    is_active = payload.get("is_active", payload.get("active", True))
    
    if not all([name, provider, model, api_key]):
        raise HTTPException(400, "name, provider, model, and api_key are required")
    
    if not isinstance(temperature, (int, float)) or temperature < 0 or temperature > 2:
        raise HTTPException(400, "temperature must be a number between 0 and 2")
    
    try:
        # Create LLM config with correct field names
        row = LLMConfig(
            name=name,
            provider=provider,
            model=model,
            temperature=float(temperature),
            is_active=bool(is_active),
            owner_user_id=user.id    # Use owner_user_id, not created_by
        )
        
        # Use the set_api_key method to encrypt the API key
        row.set_api_key(api_key)
        
        db.add(row)
        db.commit()
        db.refresh(row)
        
        logger.info(f"[llm] Created config {row.id} by user {user.id}")
        
        return {
            "id": str(row.id),
            "name": row.name,
            "provider": row.provider,
            "model": row.model,
            "temperature": row.temperature,
            "is_active": row.is_active,
            "created_at": row.created_at.isoformat() if row.created_at else None
        }
        
    except Exception as e:
        logger.error(f"[llm] Failed to create config: {e}")
        db.rollback()
        raise HTTPException(500, f"Failed to create configuration: {str(e)}")

@router.patch("/configs/{cfg_id}")
def update_config(
    cfg_id: str, 
    payload: dict = Body(...), 
    user: User = Depends(require_role('admin')), 
    db: Session = Depends(get_db)
):
    row = db.get(LlmConfig, UUID(cfg_id))
    if not row:
        raise HTTPException(404, "not found")
    
    name = payload.get("name")
    model = payload.get("model")
    temp = payload.get("temperature")
    api_key = payload.get("api_key")
    
    if name is not None:
        row.name = str(name)
    if model is not None:
        row.model = str(model)
    if temp is not None:
        row.temperature = float(temp)
    if api_key is not None:
        # Use the encryption method for updating API key
        row.set_api_key(str(api_key))
    
    db.commit()
    db.refresh(row)
    return {"ok": True}

@router.delete("/configs/{cfg_id}")
def delete_config(
    cfg_id: str, 
    user: User = Depends(require_role('admin')), 
    db: Session = Depends(get_db)
):
    row = db.get(LlmConfig, UUID(cfg_id))
    if not row:
        raise HTTPException(404, "not found")
    try:
        db.delete(row)
        db.commit()
        return {"ok": True}
    except IntegrityError:
        db.rollback()
        # still referenced by sessions → 409 with a helpful payload
        raise HTTPException(
            status_code=409,
            detail={"reason": "in_use", "hint": "Detach sessions first: POST /api/llm/configs/{id}/detach-sessions"}
        )
        
@router.patch("/configs/{config_id}/activate")
def toggle_config_active(
    config_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Activate or deactivate an LLM configuration"""
    try:
        config_uuid = uuid.UUID(config_id)
    except ValueError:
        raise HTTPException(400, "Invalid config ID format")
    
    is_active = payload.get("is_active", payload.get("active"))
    if is_active is None:
        raise HTTPException(400, "is_active field is required")
    
    config = db.execute(
        select(LLMConfig).where(
            LLMConfig.id == config_uuid,
            (LLMConfig.owner_user_id == user.id) | (LLMConfig.owner_user_id.is_(None))
        )
    ).scalar_one_or_none()
    
    if not config:
        raise HTTPException(404, "Configuration not found")
    
    config.is_active = bool(is_active)
    db.commit()
    
    logger.info(f"[llm] Config {config_id} {'activated' if is_active else 'deactivated'} by user {user.id}")
    
    return {
        "id": str(config.id),
        "is_active": config.is_active,
        "message": f"Configuration {'activated' if is_active else 'deactivated'}"
    }

@router.post("/configs/{cfg_id}/deactivate")
def deactivate_config(
    cfg_id: str, 
    user: User = Depends(require_role('admin')), 
    db: Session = Depends(get_db)
):
    row = db.get(LlmConfig, UUID(cfg_id))
    if not row:
        raise HTTPException(404, "not found")
    row.is_active = False  # Changed from 'active' to 'is_active'
    db.commit()
    return {"ok": True}

@router.post("/configs/{cfg_id}/test")
def test_config(
    cfg_id: str, 
    user: User = Depends(require_role('admin')), 
    db: Session = Depends(get_db)
):
    cfg = db.get(LlmConfig, UUID(cfg_id))
    if not cfg:
        raise HTTPException(404, "not found")
    
    # Get the decrypted API key
    try:
        api_key = cfg.get_api_key()
    except Exception as e:
        raise HTTPException(500, f"Failed to decrypt API key: {str(e)}")
    
    choice = call_openai_chat(
        api_key, 
        cfg.model, 
        [{"role": "user", "content": "reply with 'pong'"}], 
        float(cfg.temperature or 0.2)
    )
    return {"ok": True, "sample": choice["message"].get("content", "")}

@router.get("/configs/{config_id}/usage")
def get_config_usage(
    config_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),  # Allow any authenticated user
):
    """Get usage statistics for an LLM configuration"""
    try:
        config_uuid = uuid.UUID(config_id)
    except ValueError:
        raise HTTPException(400, "Invalid config ID format")
    
    # Verify user has access to this config
    config = db.execute(
        select(LLMConfig).where(
            LLMConfig.id == config_uuid,
            (LLMConfig.owner_user_id == user.id) | (LLMConfig.owner_user_id.is_(None))
        )
    ).scalar_one_or_none()
    
    if not config:
        raise HTTPException(404, "Configuration not found or access denied")
    
    # Count sessions using this config
    sessions_using = db.scalar(
        select(func.count(ClientChatSession.id)).where(
            ClientChatSession.llm_config_id == config_uuid
        )
    ) or 0
    
    return {
        "config_id": str(config.id),
        "sessions_using": sessions_using,
        "config_name": config.name
    }

@router.post("/configs/{cfg_id}/detach-sessions")
def detach_sessions(
    cfg_id: str, 
    user: User = Depends(require_role('admin')), 
    db: Session = Depends(get_db)
):
    u = (
        update(ClientChatSession)
        .where(ClientChatSession.llm_config_id == UUID(cfg_id))
        .values(llm_config_id=None)
    )
    db.execute(u)
    db.commit()
    return {"ok": True}

# ---------- per-client session ----------
@router.post("/clients/{client_id}/session")
def create_or_update_session(
    client_id: str,
    payload: dict = Body(...),
    user: User = Depends(require_role()),
    db: Session = Depends(get_db)
):
    llm_config_id = payload.get("llm_config_id")
    system_prompt = payload.get("system_prompt", "")
    if not llm_config_id:
        raise HTTPException(400, "llm_config_id required")

    # create new session
    sess = ClientChatSession(
        client_id=client_id,
        system_prompt=system_prompt or "",
        llm_config_id=UUID(llm_config_id),
        owner_user_id=user.id  # Changed from created_by to owner_user_id
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    
    # persist system as first message
    if system_prompt:
        db.add(ChatMessage(
            session_id=sess.id, 
            role="system", 
            content=system_prompt
        ))
        db.commit()
    
    return {"id": str(sess.id)}

@router.get("/clients/{client_id}/session/{sid}/messages")
def get_messages(
    client_id: str, 
    sid: str, 
    user: User = Depends(require_role()), 
    db: Session = Depends(get_db)
):
    sess = db.get(ClientChatSession, UUID(sid))
    if not sess or sess.client_id != client_id:
        raise HTTPException(404, "session not found")
    
    rows = db.execute(
        select(ChatMessage).where(
            ChatMessage.session_id == sess.id
        ).order_by(ChatMessage.created_at.asc())
    ).scalars().all()
    
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "tool_name": m.tool_name,
            "tool_args": m.tool_args,
            "created_at": m.created_at.isoformat()
        }
        for m in rows
    ]

# ---------- chat: send message and possibly queue MCP command ----------
@router.post("/clients/{client_id}/session/{sid}/send")
def chat_send(
    client_id: str, 
    sid: str, 
    payload: dict = Body(...),
    user: User = Depends(require_role()), 
    db: Session = Depends(get_db)
):
    text = (payload.get("message") or "").strip()
    if not text:
        raise HTTPException(400, "message required")

    sess = db.get(ClientChatSession, UUID(sid))
    if not sess or sess.client_id != client_id:
        raise HTTPException(404, "session not found")

    cfg = db.get(LlmConfig, sess.llm_config_id)
    if not cfg:
        raise HTTPException(400, "llm config missing")
    
    # Check if config is active
    if hasattr(cfg, "is_active") and cfg.is_active is False:
        raise HTTPException(400, "llm config is inactive")
    
    # Get decrypted API key
    try:
        api_key = cfg.get_api_key()
    except Exception as e:
        raise HTTPException(500, f"Failed to decrypt API key: {str(e)}")
    
    if not api_key or not cfg.model:
        raise HTTPException(400, "llm config missing api_key or model")

    # store user msg
    db.add(ChatMessage(session_id=sess.id, role="user", content=text))
    db.commit()

    # build messages from history
    msgs = []
    if sess.system_prompt:
        msgs.append({"role": "system", "content": sess.system_prompt})
    
    hist = db.execute(
        select(ChatMessage).where(
            ChatMessage.session_id == sess.id
        ).order_by(ChatMessage.created_at.asc())
    ).scalars().all()
    
    for m in hist:
        if m.role in ("system", "user", "assistant"):
            msgs.append({"role": m.role, "content": m.content})
        elif m.role == "tool":
            msgs.append({
                "role": "tool",
                "content": json.dumps(m.tool_args or {}),
                "name": m.tool_name or "tool"
            })

    # call provider
    if cfg.provider != "openai":
        raise HTTPException(400, f"provider {cfg.provider} not implemented")
    
    choice = call_openai_chat(api_key, cfg.model, msgs, float(cfg.temperature or 0.2))

    assistant_text = choice["message"].get("content") or ""
    tools = choice["message"].get("tool_calls") or []
    
    db.add(ChatMessage(session_id=sess.id, role="assistant", content=assistant_text))
    db.commit()

    queued_id = None
    for t in tools:
        if t.get("type") == "function" and (t.get("function") or {}).get("name") == "issue_command":
            try:
                args = json.loads((t["function"].get("arguments") or "{}"))
            except Exception:
                args = {}
            cmd = (args.get("command") or "").strip()
            if cmd:
                db.add(ChatMessage(
                    session_id=sess.id,
                    role="tool",
                    content="queued",
                    tool_name="issue_command",
                    tool_args={"command": cmd}
                ))
                row = Instruction(
                    client_id=client_id,
                    command_plain=cmd,
                    status="queued",
                    created_at=now_utc()
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                queued_id = str(row.id)

    return {"assistant": assistant_text, "queued_instruction_id": queued_id}

@router.post("/register")
def legacy_register(
    provider: str = Query(...),
    api_key: str = Query(...),
    user: User = Depends(require_role('admin')),
    db: Session = Depends(get_db)
):
    # choose a default model per provider
    model = "gpt-4o-mini" if provider.lower() == "openai" else "unknown"
    name = f"{provider} default"

    row = LlmConfig(
        name=name,
        provider=provider.lower(),
        model=model,
        temperature=0.2,
        owner_user_id=user.id  # Changed from created_by
    )
    
    # Use the encryption method
    row.set_api_key(api_key)
    
    db.add(row)
    db.commit()
    db.refresh(row)
    
    return {
        "id": str(row.id),
        "name": row.name,
        "provider": row.provider,
        "model": row.model
    }


@router.put("/configs/{config_id}")
def update_config_user(
    config_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),  # Allow any authenticated user
):
    """Update an LLM configuration owned by the current user"""
    try:
        config_uuid = uuid.UUID(config_id)
    except ValueError:
        raise HTTPException(400, "Invalid config ID format")
    
    # Find config owned by user or shared (no owner)
    config = db.execute(
        select(LLMConfig).where(
            LLMConfig.id == config_uuid,
            (LLMConfig.owner_user_id == user.id) | (LLMConfig.owner_user_id.is_(None))
        )
    ).scalar_one_or_none()
    
    if not config:
        raise HTTPException(404, "Configuration not found or access denied")
    
    # Update fields if provided
    name = payload.get("name")
    provider = payload.get("provider") 
    model = payload.get("model")
    temperature = payload.get("temperature")
    api_key = payload.get("api_key")
    
    if name is not None:
        if not name.strip():
            raise HTTPException(400, "Name cannot be empty")
        config.name = str(name).strip()
    
    if provider is not None:
        if provider not in ["openai", "anthropic"]:
            raise HTTPException(400, "Provider must be 'openai' or 'anthropic'")
        config.provider = str(provider)
    
    if model is not None:
        if not model.strip():
            raise HTTPException(400, "Model cannot be empty")
        config.model = str(model).strip()
    
    if temperature is not None:
        try:
            temp_float = float(temperature)
            if temp_float < 0 or temp_float > 2:
                raise HTTPException(400, "Temperature must be between 0 and 2")
            config.temperature = temp_float
        except (TypeError, ValueError):
            raise HTTPException(400, "Temperature must be a valid number")
    
    if api_key is not None and api_key.strip():
        # Only update API key if provided and not empty
        try:
            config.set_api_key(str(api_key).strip())
        except Exception as e:
            logger.error(f"[llm] Failed to encrypt API key: {e}")
            raise HTTPException(500, "Failed to update API key")
    
    try:
        db.commit()
        db.refresh(config)
        
        logger.info(f"[llm] Updated config {config_id} by user {user.id}")
        
        return {
            "id": str(config.id),
            "name": config.name,
            "provider": config.provider,
            "model": config.model,
            "temperature": config.temperature,
            "is_active": config.is_active,
            "message": "Configuration updated successfully"
        }
        
    except Exception as e:
        logger.error(f"[llm] Failed to update config {config_id}: {e}")
        db.rollback()
        raise HTTPException(500, f"Failed to update configuration: {str(e)}")

@router.get("/debug/configs")
def debug_configs(
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Debug endpoint to see LLM configs and their API keys"""
    configs = db.execute(
        select(LLMConfig).where(
            (LLMConfig.owner_user_id == user.id) | (LLMConfig.owner_user_id.is_(None))
        )
    ).scalars().all()
    
    result = []
    for config in configs:
        try:
            api_key = config.get_api_key()
            key_preview = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "short_key"
        except Exception as e:
            key_preview = f"ERROR: {str(e)}"
        
        result.append({
            "id": str(config.id),
            "name": config.name,
            "is_active": config.is_active,
            "api_key_preview": key_preview
        })
    
    return {"configs": result}
