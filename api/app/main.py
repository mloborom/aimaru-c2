# api/app/main.py
import os
import logging
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from .config import CORS_ORIGINS
from . import models # ensures all tables (including LLM ones) are registered with Base
from .routes_auth import router as auth_router
from .routes_users import router as users_router
from .routes_keys import router as keys_router, auth_router as apikey_auth_router
from .routes_llm import router as llm_router
from .routes_chat import router as chat_router
from .routes_client_builder import router as client_builder_router
from .routes_tools import router as tools_router
from .routes_mcp_tools import router as mcp_tools_router
from .routes_amsi_deployment import router as amsi_deployment_router
from .auth_dep import require_role
from .models import User
from .deps import get_db
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# MCP Routes - Use refactored version by default, fallback to original
USE_REFACTORED_MCP = os.getenv("USE_REFACTORED_MCP", "true").lower() == "true"

if USE_REFACTORED_MCP:
    from .routes_mcp_refactored import router as mcp_router
    print("[main] Using refactored MCP routes (service layer)")
else:
    from .routes_mcp import router as mcp_router
    print("[main] Using original MCP routes")

app = FastAPI(title="MCP API")

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# register routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(keys_router)
app.include_router(mcp_router)
app.include_router(mcp_tools_router)
app.include_router(llm_router)
app.include_router(chat_router)
app.include_router(apikey_auth_router)
app.include_router(client_builder_router)
app.include_router(tools_router)
app.include_router(amsi_deployment_router)

# Optional: healthcheck
@app.get("/api/health")
def health():
    return {"ok": True, "service": "mcp-api"}


# =============================================================================
# MCP SERVER SSE ENDPOINT
# =============================================================================

# Enable MCP Server via environment variable (default: enabled)
ENABLE_MCP_SERVER = os.getenv("ENABLE_MCP_SERVER", "true").lower() == "true"

if ENABLE_MCP_SERVER:
    from .mcp_api_server import mcp_api_server, set_request_context
    from .mcp_middleware import MCPAuthMiddleware, MCPContextMiddleware

    log.info("[main] MCP Server Layer ENABLED")
    log.info("[main]   - MCP tools defined in mcp_api_server.py")
    log.info("[main]   - MCP tools exposed via REST at /api/mcp-tools/*")

    # Phase 2: Native MCP SSE Protocol Support
    # FastMCP provides sse_app() which returns a Starlette ASGI app
    # We can mount this directly into FastAPI

    try:
        # Get the SSE app from FastMCP
        # This handles the full MCP protocol over SSE
        mcp_sse_asgi_app = mcp_api_server.sse_app()

        # Phase 2.5: Wrap with authentication middleware
        # Use environment variable to choose strict auth vs. dev mode
        USE_STRICT_AUTH = os.getenv("MCP_USE_STRICT_AUTH", "false").lower() == "true"

        if USE_STRICT_AUTH:
            log.info("[main] 🔒 Using strict JWT authentication for MCP")
            wrapped_app = MCPAuthMiddleware(
                mcp_sse_asgi_app,
                get_db_func=get_db,
                set_context_func=set_request_context
            )
        else:
            log.info("[main] 🔓 Using context middleware (no strict auth) for MCP")
            log.info("[main]    Set MCP_USE_STRICT_AUTH=true for production")
            wrapped_app = MCPContextMiddleware(
                mcp_sse_asgi_app,
                get_db_func=get_db,
                set_context_func=set_request_context
            )

        # Mount the wrapped app
        app.mount("/mcp", wrapped_app)

        log.info("[main] ✅ Native MCP SSE protocol ENABLED")
        log.info("[main]   - SSE endpoint: /mcp/sse")
        log.info("[main]   - Messages endpoint: /mcp/messages")
        log.info("[main]   - Full MCP protocol support active")
        log.info("[main]   - Authentication middleware: ACTIVE")

    except Exception as e:
        log.warning(f"[main] Could not mount MCP SSE app: {e}")
        log.info("[main] Falling back to REST-only mode")
        log.info("[main] MCP tools available via /api/mcp-tools/*")

else:
    log.info("[main] MCP Server SSE endpoint DISABLED (set ENABLE_MCP_SERVER=true to enable)")