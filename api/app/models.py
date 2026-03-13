# api/app/models.py
from __future__ import annotations

import uuid
from sqlalchemy import (
    Column, String, Boolean, ForeignKey, Text, DateTime, LargeBinary, Float, event
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .crypto import encrypt_api_key, decrypt_api_key

from .db import Base

# -------------------------
# Users
# -------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="viewer")
    disabled = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")


# -------------------------
# API Keys (for MCP client auth)
# -------------------------
class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # public short id (e.g. "ak_AB12CD")
    key_id = Column(String(32), unique=True, nullable=False)

    # hashed secret part
    secret_hash = Column(String(255), nullable=False)

    label = Column(String(200))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    revoked = Column(Boolean, default=False)

    user = relationship("User", back_populates="api_keys")


# -------------------------
# Client presence heartbeat
# -------------------------
class ClientSeen(Base):
    __tablename__ = "clients_seen"
    client_id = Column(String(200), primary_key=True, index=True)
    last_seen_at = Column(DateTime(timezone=True),
                          server_default=func.now(),
                          onupdate=func.now(),
                          nullable=False)
# -------------------------
# MCP Instructions / Results
# -------------------------
class Instruction(Base):
    __tablename__ = "instructions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(String(200), nullable=False, index=True)
    command_plain = Column(Text, nullable=False)            # plaintext command that was sent
    status = Column(String(20), default="queued", index=True)  # queued|delivered|completed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    delivered_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # At-rest ciphertext (binary). UI requests plaintext from /api/results/{id}?plaintext=1
    # which is decrypted on-demand, not stored in the DB as another column.
    result_cipher = Column(LargeBinary, nullable=True)


# -------------------------
# LLM configuration
# -------------------------
class LLMConfig(Base):
    __tablename__ = "llm_configs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # who owns this config (nullable: allow shared/legacy entries)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    name = Column(String(128), nullable=False)
    provider = Column(String(32), nullable=False)          # e.g. "openai"
    model = Column(String(128), nullable=False)            # e.g. "gpt-4o-mini"
    
    # Both columns exist in your database
    api_key = Column(Text, nullable=True)                  # Legacy plain text
    api_key_enc = Column(Text, nullable=False)             # Encrypted (required in DB)
    
    temperature = Column(Float, nullable=False, default=0.2)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def set_api_key(self, plaintext_key: str):
        '''Set API key with encryption'''
        # Store encrypted version
        self.api_key_enc = encrypt_api_key(plaintext_key)
        # Clear any legacy plain text
        self.api_key = None
    
    def get_api_key(self) -> str:
        '''Get decrypted API key'''
        # Always use encrypted version if available
        if self.api_key_enc:
            return decrypt_api_key(self.api_key_enc)
        # Fall back to legacy plain text if exists
        elif self.api_key:
            return self.api_key
        else:
            raise ValueError("No API key available")

# -------------------------
# Per-client chat sessions
# -------------------------
class ClientChatSession(Base):
    __tablename__ = "client_chat_sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(String(128), nullable=False)

    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # nullable so we can "detach" sessions before deleting an LLMConfig
    llm_config_id = Column(
        UUID(as_uuid=True),
        ForeignKey("llm_configs.id", ondelete="SET NULL"),
        nullable=True,
    )

    system_prompt = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# -------------------------
# Messages within a session
# -------------------------
class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("client_chat_sessions.id"), nullable=False)
    role = Column(String(16), nullable=False)            # "system" | "user" | "assistant" | "tool"
    content = Column(Text, nullable=False)
    tool_name = Column(String(64), nullable=True)
    tool_args = Column(Text, nullable=True)              # JSON as text
    created_at = Column(DateTime(timezone=True), server_default=func.now())
