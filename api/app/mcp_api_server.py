"""
PSMCP MCP API Server
====================

This module provides MCP (Model Context Protocol) server capabilities for the PSMCP backend.
It exposes the same functionality as the REST API but using the standardized MCP protocol.

Architecture:
- MCP Server with SSE transport for real-time communication
- Reuses all existing business logic from mcp_service.py
- Works alongside REST API (backward compatible)
- Enables native Claude integration and real-time updates

Benefits:
- Standardized protocol (MCP) instead of custom REST
- Real-time push notifications via SSE
- Built-in tool discovery and schema validation
- Better integration with MCP-aware clients (Claude Desktop, etc.)
"""

from __future__ import annotations
import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from sqlalchemy.orm import Session

from . import mcp_service
from .deps import get_db
from .models import User

log = logging.getLogger(__name__)

# Initialize FastMCP Server
mcp_api_server = FastMCP("psmcp-api-server")

log.info("[MCP API Server] Initialized PSMCP MCP API Server")


# =============================================================================
# Context Management (for dependency injection)
# =============================================================================

class MCPRequestContext:
    """Context object to pass database session and user through MCP calls"""
    def __init__(self, db: Session, user: Optional[User] = None):
        self.db = db
        self.user = user


# Global context storage (will be set per request)
_current_context: Optional[MCPRequestContext] = None


def set_request_context(db: Session, user: Optional[User] = None):
    """Set the current request context"""
    global _current_context
    _current_context = MCPRequestContext(db, user)


def get_request_context() -> MCPRequestContext:
    """Get the current request context"""
    if _current_context is None:
        raise RuntimeError("No request context available. Call set_request_context first.")
    return _current_context


# =============================================================================
# MCP TOOLS - Command & Control Operations
# =============================================================================

@mcp_api_server.tool()
async def list_clients(window_seconds=120):
    """List all connected Windows clients with their status and statistics

    Args:
        window_seconds: Time window in seconds to consider a client "online" (default: 120)
    """
    ctx = get_request_context()

    log.info(f"[MCP Tool] list_clients called (window={window_seconds}s)")

    try:
        result = await mcp_service.list_clients_service(ctx.db, window_seconds)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        log.error(f"[MCP Tool] list_clients error: {e}")
        return json.dumps({"error": str(e), "success": False})


@mcp_api_server.tool()
async def execute_powershell_command(
    client_id,
    command,
    description=""
):
    """Execute a PowerShell command on a remote Windows client

    Args:
        client_id: Target Windows client identifier (e.g., DESKTOP-ABC123)
        command: PowerShell command or script to execute
        description: Optional description of what this command does (for logging)

    Returns:
        JSON string with instruction ID and status
    """
    ctx = get_request_context()

    log.info(f"[MCP Tool] execute_powershell_command on {client_id}: {command[:100]}")

    if not ctx.user:
        return json.dumps({"error": "Authentication required", "success": False})

    try:
        result = await mcp_service.create_instruction_service(
            ctx.db,
            client_id,
            command,
            ctx.user
        )

        # Add description to response if provided
        if description:
            result["description"] = description

        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        log.error(f"[MCP Tool] execute_powershell_command error: {e}")
        return json.dumps({"error": str(e), "success": False})


@mcp_api_server.tool()
async def get_command_result(
    instruction_id,
    decrypt=True
):
    """Get the result of a previously executed PowerShell command

    Args:
        instruction_id: The instruction ID returned from execute_powershell_command
        decrypt: Whether to decrypt the result (default: True)

    Returns:
        JSON string with command result, status, and execution details
    """
    ctx = get_request_context()

    log.info(f"[MCP Tool] get_command_result for instruction {instruction_id}")

    try:
        result = await mcp_service.get_result_service(
            ctx.db,
            instruction_id,
            decrypt
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        log.error(f"[MCP Tool] get_command_result error: {e}")
        return json.dumps({"error": str(e), "success": False})


@mcp_api_server.tool()
async def list_command_queue(
    client_id=None,
    status=None,
    limit=50
):
    """List commands in the queue with optional filtering

    Args:
        client_id: Optional client ID to filter by
        status: Optional status to filter by (queued, delivered, completed)
        limit: Maximum number of results to return (default: 50)

    Returns:
        JSON string with list of queued commands
    """
    ctx = get_request_context()

    log.info(f"[MCP Tool] list_command_queue (client={client_id}, status={status}, limit={limit})")

    try:
        result = await mcp_service.list_queue_service(
            ctx.db,
            client_id=client_id,
            status=status,
            limit=limit
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        log.error(f"[MCP Tool] list_command_queue error: {e}")
        return json.dumps({"error": str(e), "success": False})


@mcp_api_server.tool()
async def get_client_details(client_id, window_seconds=120):
    """Get detailed information about a specific client

    Args:
        client_id: The client identifier
        window_seconds: Time window to consider for online status (default: 120)

    Returns:
        JSON string with detailed client information and statistics
    """
    ctx = get_request_context()

    log.info(f"[MCP Tool] get_client_details for {client_id}")

    try:
        result = await mcp_service.get_client_details_service(
            ctx.db,
            client_id,
            window_seconds
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        log.error(f"[MCP Tool] get_client_details error: {e}")
        return json.dumps({"error": str(e), "success": False})


@mcp_api_server.tool()
async def delete_instruction(instruction_id):
    """Delete a queued instruction (before it's delivered)

    Args:
        instruction_id: The instruction ID to delete

    Returns:
        JSON string with deletion status
    """
    ctx = get_request_context()

    log.info(f"[MCP Tool] delete_instruction {instruction_id}")

    if not ctx.user:
        return json.dumps({"error": "Authentication required", "success": False})

    try:
        result = await mcp_service.delete_instruction_service(
            ctx.db,
            instruction_id,
            ctx.user
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        log.error(f"[MCP Tool] delete_instruction error: {e}")
        return json.dumps({"error": str(e), "success": False})


# =============================================================================
# MCP RESOURCES - Read-only Data Access
# =============================================================================

@mcp_api_server.resource("psmcp://clients/list")
async def clients_list_resource():
    """Resource: Current list of all clients with status

    Returns:
        JSON string with current client list
    """
    ctx = get_request_context()

    log.info("[MCP Resource] clients_list_resource accessed")

    try:
        result = await mcp_service.list_clients_service(ctx.db, 120)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        log.error(f"[MCP Resource] clients_list_resource error: {e}")
        return json.dumps({"error": str(e)})


@mcp_api_server.resource("psmcp://queue/pending")
async def queue_pending_resource():
    """Resource: All pending commands in the queue

    Returns:
        JSON string with pending commands
    """
    ctx = get_request_context()

    log.info("[MCP Resource] queue_pending_resource accessed")

    try:
        result = await mcp_service.list_queue_service(
            ctx.db,
            status="queued",
            limit=100
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        log.error(f"[MCP Resource] queue_pending_resource error: {e}")
        return json.dumps({"error": str(e)})


@mcp_api_server.resource("psmcp://queue/recent")
async def queue_recent_resource():
    """Resource: Recently completed commands

    Returns:
        JSON string with recent completed commands
    """
    ctx = get_request_context()

    log.info("[MCP Resource] queue_recent_resource accessed")

    try:
        result = await mcp_service.list_queue_service(
            ctx.db,
            status="completed",
            limit=50
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        log.error(f"[MCP Resource] queue_recent_resource error: {e}")
        return json.dumps({"error": str(e)})


# ============================================================================
# RESOURCE TEMPLATES (Phase 5)
# ============================================================================
# Resource templates allow dynamic URIs with parameters

@mcp_api_server.resource("psmcp://client/{client_id}")
async def client_detail_resource(client_id: str):
    """Resource Template: Individual client details

    Args:
        client_id: The client identifier (e.g., DESKTOP-ABC123)

    Returns:
        JSON string with detailed client information including:
        - Connection status
        - Last seen timestamp
        - Queued and completed command counts
        - Recent command history
    """
    ctx = get_request_context()

    log.info(f"[MCP Resource Template] client_detail_resource accessed for {client_id}")

    try:
        result = await mcp_service.get_client_details_service(ctx.db, client_id)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        log.error(f"[MCP Resource Template] client_detail_resource error: {e}")
        return json.dumps({"error": str(e)})


@mcp_api_server.resource("psmcp://instruction/{instruction_id}")
async def instruction_detail_resource(instruction_id: str):
    """Resource Template: Individual instruction/command details

    Args:
        instruction_id: The instruction UUID

    Returns:
        JSON string with instruction details including:
        - Command text (decrypted)
        - Status (queued/delivered/completed)
        - Target client ID
        - Timestamps (created, delivered, completed)
        - Result output (if completed)
    """
    ctx = get_request_context()

    log.info(f"[MCP Resource Template] instruction_detail_resource accessed for {instruction_id}")

    try:
        result = await mcp_service.get_instruction_service(
            ctx.db,
            instruction_id,
            decrypt=True
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        log.error(f"[MCP Resource Template] instruction_detail_resource error: {e}")
        return json.dumps({"error": str(e)})


@mcp_api_server.resource("psmcp://client/{client_id}")
async def client_details_resource(client_id):
    """Resource: Detailed information about a specific client

    Args:
        client_id: The client identifier

    Returns:
        JSON string with client details
    """
    ctx = get_request_context()

    log.info(f"[MCP Resource] client_details_resource for {client_id}")

    try:
        result = await mcp_service.get_client_details_service(
            ctx.db,
            client_id,
            120
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        log.error(f"[MCP Resource] client_details_resource error: {e}")
        return json.dumps({"error": str(e)})


# ============================================================================
# MCP PROMPTS (Phase 5)
# ============================================================================
# Prompts provide pre-defined workflows for common operations

@mcp_api_server.prompt()
async def list_all_clients_prompt():
    """List all connected clients with their status

    Returns a prompt that guides the user through listing all clients
    """
    from mcp.types import PromptMessage, TextContent

    return [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text="Please list all connected Windows clients and show their current status, including last seen time and command queue statistics."
            )
        )
    ]


@mcp_api_server.prompt()
async def system_info_prompt(client_id: str):
    """Gather system information from a client

    Args:
        client_id: The target client ID (e.g., DESKTOP-ABC123)

    Returns:
        Prompt for collecting system information from the specified client
    """
    from mcp.types import PromptMessage, TextContent

    return [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=f"Please execute the following PowerShell commands on client {client_id} to gather system information:\n\n1. Get-ComputerInfo | Select-Object WindowsVersion, OsHardwareAbstractionLayer\n2. Get-WmiObject Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber\n3. Get-WmiObject Win32_Processor | Select-Object Name, NumberOfCores\n4. Get-WmiObject Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum\n\nThen retrieve and display all results."
            )
        )
    ]


@mcp_api_server.prompt()
async def check_running_processes_prompt(client_id: str):
    """Check running processes on a client

    Args:
        client_id: The target client ID

    Returns:
        Prompt for checking running processes on the specified client
    """
    from mcp.types import PromptMessage, TextContent

    return [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=f"Please execute the following PowerShell command on client {client_id}:\n\nGet-Process | Sort-Object CPU -Descending | Select-Object -First 10 Name, CPU, WorkingSet\n\nThis will show the top 10 processes by CPU usage."
            )
        )
    ]


# =============================================================================
# Utility Functions
# =============================================================================

async def initialize_mcp_server():
    """Initialize MCP server and log available tools/resources"""
    log.info("=" * 80)
    log.info("[MCP API Server] Initialization Complete")
    log.info("=" * 80)
    log.info(f"Server Name: {mcp_api_server.name}")
    log.info("Available Tools (6):")
    log.info("  - list_clients")
    log.info("  - execute_powershell_command")
    log.info("  - get_command_result")
    log.info("  - list_command_queue")
    log.info("  - get_client_details")
    log.info("  - delete_instruction")
    log.info("Available Resources (3 static):")
    log.info("  - psmcp://clients/list")
    log.info("  - psmcp://queue/pending")
    log.info("  - psmcp://queue/recent")
    log.info("Available Resource Templates (2) [Phase 5]:")
    log.info("  - psmcp://client/{client_id}")
    log.info("  - psmcp://instruction/{instruction_id}")
    log.info("Available Prompts (3) [Phase 5]:")
    log.info("  - list_all_clients_prompt")
    log.info("  - system_info_prompt")
    log.info("  - check_running_processes_prompt")
    log.info("=" * 80)


# Initialize on module load
import asyncio
try:
    asyncio.create_task(initialize_mcp_server())
except RuntimeError:
    # If no event loop, log synchronously
    log.info("[MCP API Server] Module loaded (will initialize on first request)")
