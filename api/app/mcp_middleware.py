"""
MCP Authentication Middleware
==============================

This middleware wraps the FastMCP SSE app to provide:
1. JWT token authentication
2. Database session injection
3. User context for tool execution
"""

import logging
from typing import Callable, Optional
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy.orm import Session

from .deps import get_db
from .security import Tokens
from .models import User

log = logging.getLogger(__name__)


class MCPAuthMiddleware:
    """
    ASGI Middleware for authenticating MCP requests.

    This middleware:
    - Extracts JWT token from Authorization header
    - Validates the token
    - Creates database session
    - Injects user and DB session into request context
    - Calls set_request_context() for MCP tools to access
    """

    def __init__(self, app: ASGIApp, get_db_func: Callable, set_context_func: Callable):
        self.app = app
        self.get_db = get_db_func
        self.set_context = set_context_func

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only process HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract headers
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()

        # Check for Bearer token
        if not auth_header.startswith("Bearer "):
            # Phase 4: Enforce strict authentication
            log.error("[MCP Auth] No authentication provided - rejecting request")
            await self._send_error(scope, receive, send, "Authentication required")
            return

        # Extract token
        token = auth_header[7:]  # Remove "Bearer " prefix

        try:
            # Validate token and get user
            user_id = Tokens.verify_access(token)

            if not user_id:
                log.error("[MCP Auth] Invalid token: no user ID")
                await self._send_error(scope, receive, send, "Invalid token")
                return

            # Get database session
            db_gen = self.get_db()
            db = next(db_gen)

            try:
                # Get user from database
                user = db.query(User).filter(User.id == user_id).first()

                if not user:
                    log.error(f"[MCP Auth] User not found: {user_id}")
                    await self._send_error(scope, receive, send, "User not found")
                    return

                if user.disabled:
                    log.error(f"[MCP Auth] User disabled: {user.username}")
                    await self._send_error(scope, receive, send, "User disabled")
                    return

                log.info(f"[MCP Auth] ✅ Authenticated user: {user.username}")

                # Set request context for MCP tools
                self.set_context(db, user)

                # Store in scope for downstream use
                scope["user"] = user
                scope["db"] = db

                # Call the wrapped app
                await self.app(scope, receive, send)

            finally:
                # Cleanup database session
                try:
                    next(db_gen)
                except StopIteration:
                    pass

        except Exception as e:
            log.error(f"[MCP Auth] Authentication error: {e}")
            await self._send_error(scope, receive, send, f"Authentication failed: {str(e)}")
            return

    async def _send_error(self, scope: Scope, receive: Receive, send: Send, message: str):
        """Send JSON error response"""
        response = JSONResponse(
            {"error": message, "detail": "Authentication required"},
            status_code=401
        )
        await response(scope, receive, send)


class MCPContextMiddleware:
    """
    Simplified middleware that just sets context without auth.

    Use this for development/testing when auth is disabled.
    """

    def __init__(self, app: ASGIApp, get_db_func: Callable, set_context_func: Callable):
        self.app = app
        self.get_db = get_db_func
        self.set_context = set_context_func

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Get database session
        db_gen = self.get_db()
        db = next(db_gen)

        try:
            # For testing: create a default admin user context
            # In production, this should require authentication
            user = db.query(User).filter(User.username == "admin").first()

            if user:
                log.info(f"[MCP Context] Setting context for user: {user.username}")
                self.set_context(db, user)
                scope["user"] = user
                scope["db"] = db
            else:
                log.warning("[MCP Context] No admin user found - tools may fail")
                self.set_context(db, None)

            # Call the wrapped app
            await self.app(scope, receive, send)

        finally:
            # Cleanup
            try:
                next(db_gen)
            except StopIteration:
                pass
