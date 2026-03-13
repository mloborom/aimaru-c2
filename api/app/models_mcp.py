from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.types import DateTime
from sqlalchemy.sql import func
import uuid
from .db import Base

class MCPClient(Base):
    __tablename__ = 'mcp_clients'
    id = Column(String, primary_key=True)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    meta = Column(JSONB, server_default='{}', nullable=False)

class MCPInstruction(Base):
    __tablename__ = 'mcp_instructions'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(String, ForeignKey('mcp_clients.id', ondelete='CASCADE'), nullable=False)
    command_plain = Column(Text, nullable=False)
    status = Column(String, default='queued', nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    delivered_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

class MCPResult(Base):
    __tablename__ = 'mcp_results'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instruction_id = Column(UUID(as_uuid=True), ForeignKey('mcp_instructions.id', ondelete='CASCADE'), nullable=False)
    client_id = Column(String, nullable=False)
    encrypted_result = Column(Text)
    raw_decrypted = Column(Text)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
