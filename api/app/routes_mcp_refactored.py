"""
Refactored MCP Routes - Using MCP Service Layer
================================================

This module uses the MCP service layer for cleaner, more efficient code.
All business logic is in mcp_service.py, routes are thin wrappers.
"""

from __future__ import annotations
from typing import Optional
import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, Body, Query, Response
from sqlalchemy.orm import Session

from .deps import get_db
from .auth_dep import require_role
from .models import User
from . import mcp_service

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["mcp"])


# ==============================================================================
# Client Management Endpoints
# ==============================================================================

@router.get("/clients")
async def get_clients(
    window_seconds: int = Query(120, ge=10, le=3600, description="Connection window in seconds"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
    response: Response = None,
):
    """List all clients with connection status and statistics

    This endpoint uses the MCP service layer for efficient data retrieval.
    """
    # Disable caching
    if response:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"

    log.info("[routes] GET /api/clients (user=%s, window=%d)", user.username, window_seconds)

    # Use MCP service layer
    return await mcp_service.list_clients_service(db, window_seconds)


@router.get("/list-clients")
async def list_clients_alias(
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
    response: Response = None,
):
    """List all clients (alias endpoint for backward compatibility)"""
    if response:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"

    log.info("[routes] GET /api/list-clients (user=%s)", user.username)

    return await mcp_service.list_clients_service(db, window_seconds=120)


@router.post("/clients/heartbeat")
async def client_heartbeat(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Update client heartbeat timestamp

    Clients should call this periodically to indicate they're alive.
    """
    client_id_raw = payload.get("client_id", "").strip()

    try:
        client_id = mcp_service.validate_client_id(client_id_raw)
    except ValueError as e:
        raise HTTPException(400, str(e))

    log.info("[routes] Heartbeat from %s (user=%s)", client_id, user.username)

    return await mcp_service.update_heartbeat_service(db, client_id)


# ==============================================================================
# Command Queue Endpoints
# ==============================================================================

@router.post("/issue-command")
async def issue_command(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Queue a PowerShell command for execution on a client

    Request body:
        {
            "client_id": "DESKTOP-01",
            "command": "Get-Process | Select-Object -First 5"
        }

    Returns:
        {
            "id": "uuid",
            "instruction_id": "uuid",
            "client_id": "DESKTOP-01",
            "command": "...",
            "status": "queued",
            "success": true,
            "message": "Command queued..."
        }
    """
    client_id_raw = payload.get("client_id", "").strip()
    command_raw = payload.get("command", "").strip()

    try:
        client_id = mcp_service.validate_client_id(client_id_raw)
        command = mcp_service.validate_command(command_raw)
    except ValueError as e:
        raise HTTPException(400, str(e))

    log.info(
        "[routes] Issuing command to %s (user=%s, cmd_len=%d)",
        client_id,
        user.username,
        len(command)
    )

    return await mcp_service.create_instruction_service(db, client_id, command, user)


@router.post("/execute-script")
async def execute_script(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Execute a PowerShell script with metadata

    This is used by the AI Chat feature for script execution.
    """
    client_id_raw = payload.get("client_id", "").strip()
    script_content = payload.get("script_content", "").strip()
    script_name = payload.get("script_name", "Uploaded Script")
    execution_mode = payload.get("execution_mode", "direct")

    try:
        client_id = mcp_service.validate_client_id(client_id_raw)
        script_content = mcp_service.validate_command(script_content)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Add metadata to script
    script_with_metadata = f"""# Script: {script_name}
# Execution Mode: {execution_mode}
# Executed by: {user.username}
# Timestamp: {mcp_service.now_utc().isoformat()}
# Client: {client_id}
# --- Script Content ---

{script_content}"""

    log.info(
        "[routes] Executing script on %s (user=%s, name=%s, mode=%s)",
        client_id,
        user.username,
        script_name,
        execution_mode
    )

    result = await mcp_service.create_instruction_service(db, client_id, script_with_metadata, user)

    # Enhance response with script metadata
    result.update({
        "script_name": script_name,
        "execution_mode": execution_mode,
        "lines_count": len(script_content.split('\n')),
        "characters_count": len(script_content)
    })

    return result


@router.get("/list-queue")
async def list_queue(
    status: Optional[str] = Query(None, description="Filter by status: queued, delivered, completed"),
    limit: int = Query(200, ge=1, le=1000, description="Maximum results"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """List instructions in the command queue

    Query parameters:
        - status: Filter by instruction status
        - limit: Maximum number of results (default: 200)

    Returns list of instructions with metadata.
    """
    if status and status not in ["queued", "delivered", "completed"]:
        raise HTTPException(400, "Status must be queued, delivered, or completed")

    log.info("[routes] Listing queue (user=%s, status=%s, limit=%d)", user.username, status, limit)

    return await mcp_service.list_queue_service(db, client_id=None, status=status, limit=limit)


@router.get("/clients/{client_id}/instructions")
async def get_client_instructions(
    client_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Get instructions for a specific client

    Path parameters:
        - client_id: Target client identifier

    Query parameters:
        - status: Filter by instruction status
        - limit: Maximum results
    """
    if status and status not in ["queued", "delivered", "completed"]:
        raise HTTPException(400, "Invalid status value")

    log.info(
        "[routes] Getting instructions for %s (user=%s, status=%s)",
        client_id,
        user.username,
        status
    )

    return await mcp_service.list_queue_service(db, client_id=client_id, status=status, limit=limit)


# ==============================================================================
# Client-Side Endpoints (PowerShell Clients)
# ==============================================================================

@router.get("/get-instruction")
async def get_instruction(
    client_id: str = Query(..., description="Client identifier"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Get next instruction for a client (PowerShell client polling)

    This endpoint is called by PowerShell clients to fetch commands.

    Query parameters:
        - client_id: Client identifier

    Returns:
        - 204 No Content if queue is empty
        - 200 with encrypted instruction if available
    """
    try:
        client_id = mcp_service.validate_client_id(client_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    log.debug("[routes] Client %s polling for instructions", client_id)

    try:
        result = await mcp_service.get_instruction_for_client_service(db, client_id)

        if not result:
            # No instructions available - return 204 No Content
            return Response(status_code=204)

        return result

    except ValueError as e:
        log.error("[routes] Error getting instruction for %s: %s", client_id, e)
        raise HTTPException(400, str(e))


@router.post("/send-result")
async def send_result(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Receive encrypted result from PowerShell client

    Request body:
        {
            "id": "instruction-uuid",
            "client_id": "DESKTOP-01",
            "encryptedResult": "base64-encoded-data"
        }

    The encrypted result format is: IV(16 bytes) || ciphertext
    """
    instruction_id = payload.get("id", "").strip()
    client_id = payload.get("client_id", "").strip()
    encrypted_result_b64 = payload.get("encryptedResult", "").strip()

    if not all([instruction_id, client_id, encrypted_result_b64]):
        raise HTTPException(400, "id, client_id, and encryptedResult required")

    try:
        # Decode base64 to raw bytes
        encrypted_result = base64.b64decode(encrypted_result_b64)

        if len(encrypted_result) < 17:  # IV(16) + at least 1 byte
            raise ValueError("Encrypted result too short")

    except Exception as e:
        log.error("[routes] Failed to decode result: %s", e)
        raise HTTPException(400, f"Invalid encrypted result: {e}")

    log.info("[routes] Receiving result from %s for instruction %s", client_id, instruction_id)

    try:
        return await mcp_service.store_result_service(db, instruction_id, client_id, encrypted_result)
    except ValueError as e:
        log.error("[routes] Failed to store result: %s", e)
        raise HTTPException(404, str(e))


# ==============================================================================
# Result Retrieval Endpoints
# ==============================================================================

@router.get("/results/{instruction_id}")
async def get_result(
    instruction_id: str,
    plaintext: bool = Query(False, description="Decrypt result if true"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Get instruction result by ID

    Path parameters:
        - instruction_id: Instruction UUID

    Query parameters:
        - plaintext: If true, attempt to decrypt the result

    Returns instruction metadata and optionally decrypted result.
    """
    log.info(
        "[routes] Getting result for %s (user=%s, decrypt=%s)",
        instruction_id,
        user.username,
        plaintext
    )

    try:
        return await mcp_service.get_result_service(db, instruction_id, decrypt=plaintext)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/script-result/{instruction_id}")
async def get_script_result(
    instruction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Get script result (alias for AI Chat feature)

    This endpoint automatically decrypts results.
    """
    log.info("[routes] Getting script result for %s (user=%s)", instruction_id, user.username)

    try:
        return await mcp_service.get_result_service(db, instruction_id, decrypt=True)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ==============================================================================
# Debug Endpoints
# ==============================================================================

@router.get("/debug/instruction/{instruction_id}")
async def debug_instruction(
    instruction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role()),
):
    """Debug endpoint to inspect instruction details

    This endpoint provides detailed debugging information about an instruction.
    """
    log.info("[routes] Debug request for instruction %s (user=%s)", instruction_id, user.username)

    try:
        result = await mcp_service.get_result_service(db, instruction_id, decrypt=True)

        # Add debug metadata
        debug_info = {
            "instruction": result,
            "debug_timestamp": mcp_service.now_utc().isoformat(),
            "requested_by": user.username,
        }

        return debug_info

    except ValueError as e:
        return {"error": str(e)}
