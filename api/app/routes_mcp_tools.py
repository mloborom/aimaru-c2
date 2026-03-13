"""
MCP Tools REST API
==================

This module exposes the MCP tools defined in mcp_api_server.py as REST endpoints.
This provides backward compatibility while we work on native MCP SSE integration.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from .deps import get_db
from .auth_dep import require_role
from .models import User
from . import mcp_service

router = APIRouter(prefix="/api/mcp-tools", tags=["mcp-tools"])


class ExecuteCommandRequest(BaseModel):
    client_id: str
    command: str
    description: str = ""


class GetResultRequest(BaseModel):
    instruction_id: str
    decrypt: bool = True


class ListQueueRequest(BaseModel):
    client_id: Optional[str] = None
    status: Optional[str] = None
    limit: int = 50


@router.get("/clients")
async def list_clients(
    window_seconds: int = 120,
    db: Session = Depends(get_db),
    user: User = Depends(require_role())
):
    """List all connected Windows clients (MCP Tool: list_clients)"""
    result = await mcp_service.list_clients_service(db, window_seconds)
    return result


@router.post("/execute")
async def execute_command(
    req: ExecuteCommandRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role())
):
    """Execute PowerShell command (MCP Tool: execute_powershell_command)"""
    result = await mcp_service.create_instruction_service(
        db, req.client_id, req.command, user
    )
    if req.description:
        result["description"] = req.description
    return result


@router.get("/result/{instruction_id}")
async def get_result(
    instruction_id: str,
    decrypt: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(require_role())
):
    """Get command result (MCP Tool: get_command_result)"""
    result = await mcp_service.get_result_service(db, instruction_id, decrypt)
    return result


@router.get("/queue")
async def list_queue(
    client_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(require_role())
):
    """List command queue (MCP Tool: list_command_queue)"""
    result = await mcp_service.list_queue_service(db, client_id, status, limit)
    return result


@router.get("/client/{client_id}")
async def get_client_details(
    client_id: str,
    window_seconds: int = 120,
    db: Session = Depends(get_db),
    user: User = Depends(require_role())
):
    """Get client details (MCP Tool: get_client_details)"""
    result = await mcp_service.get_client_details_service(db, client_id, window_seconds)
    return result


@router.delete("/instruction/{instruction_id}")
async def delete_instruction(
    instruction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role())
):
    """Delete instruction (MCP Tool: delete_instruction)"""
    result = await mcp_service.delete_instruction_service(db, instruction_id, user)
    return result
