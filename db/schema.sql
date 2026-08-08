-- db/schema.sql
-- Complete Schema for MCP Platform

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ==========================================
-- 1. USERS & AUTHENTICATION
-- ==========================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20),
    disabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_id TEXT NOT NULL,              -- short public id, e.g. "ak_8F3K2M"
    secret_hash TEXT NOT NULL,         -- bcrypt/argon2 of key secret
    label TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(user_id, key_id)
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_keyid ON api_keys(key_id);

-- ==========================================
-- 2. LLM CONFIGURATIONS
-- ==========================================

CREATE TABLE IF NOT EXISTS llm_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    api_key_enc TEXT NOT NULL,
    temperature NUMERIC(3,2) DEFAULT 0.2 NOT NULL,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    api_key TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    base_url TEXT
);

CREATE INDEX IF NOT EXISTS idx_llm_configs_active ON llm_configs(is_active);
CREATE INDEX IF NOT EXISTS idx_llm_configs_owner ON llm_configs(owner_user_id);

-- ==========================================
-- 3. CLIENTS & INSTRUCTIONS QUEUE
-- ==========================================

CREATE TABLE IF NOT EXISTS mcp_clients (
    id TEXT PRIMARY KEY,
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS clients_seen (
    client_id VARCHAR(200) PRIMARY KEY,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Main instructions queue
CREATE TABLE IF NOT EXISTS instructions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL,
    command_plain TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued', -- queued | delivered | completed
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    hmac_signature TEXT,
    result_cipher BYTEA
);

CREATE INDEX IF NOT EXISTS idx_instructions_client_status_created 
  ON instructions (client_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_instr_client_created 
  ON instructions (client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_instr_client_status 
  ON instructions (client_id, status);

-- MCP specific instructions queue
CREATE TABLE IF NOT EXISTS mcp_instructions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES mcp_clients(id) ON DELETE CASCADE,
    command_plain TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_mcp_instr_client_status 
  ON mcp_instructions(client_id, status);

-- ==========================================
-- 4. RESULTS
-- ==========================================

CREATE TABLE IF NOT EXISTS results (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    raw_encrypted TEXT NOT NULL,
    raw_decrypted TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mcp_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instruction_id UUID NOT NULL REFERENCES mcp_instructions(id) ON DELETE CASCADE,
    client_id TEXT NOT NULL,
    encrypted_result TEXT,
    raw_decrypted TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ==========================================
-- 5. CHAT & SESSIONS
-- ==========================================

CREATE TABLE IF NOT EXISTS client_chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL,
    system_prompt TEXT NOT NULL DEFAULT '',
    llm_config_id UUID REFERENCES llm_configs(id) ON DELETE SET NULL,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    owner_user_id UUID
);

CREATE INDEX IF NOT EXISTS idx_ccs_client_created 
  ON client_chat_sessions(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_client_chat_sessions_client 
  ON client_chat_sessions(client_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES client_chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    tool_name VARCHAR(64),
    tool_args TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at);

CREATE TABLE IF NOT EXISTS client_chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES client_chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    content TEXT NOT NULL,
    tool_name TEXT,
    tool_args JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ccm_session_created 
  ON client_chat_messages(session_id, created_at);
