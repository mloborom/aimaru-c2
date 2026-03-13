CREATE TABLE IF NOT EXISTS instructions (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  command_plain TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  hmac_signature TEXT
);
CREATE TABLE IF NOT EXISTS results (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  raw_encrypted TEXT NOT NULL,
  raw_decrypted TEXT,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- clients seen by MCP
CREATE TABLE IF NOT EXISTS mcp_clients (
  id TEXT PRIMARY KEY,
  last_seen timestamptz NOT NULL DEFAULT now(),
  meta JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- instructions queue
CREATE TABLE IF NOT EXISTS mcp_instructions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id TEXT NOT NULL REFERENCES mcp_clients(id) ON DELETE CASCADE,
  command_plain TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued', -- queued | delivered | completed
  created_at timestamptz NOT NULL DEFAULT now(),
  delivered_at timestamptz,
  completed_at timestamptz
);

-- results returned by clients
CREATE TABLE IF NOT EXISTS mcp_results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  instruction_id uuid NOT NULL REFERENCES mcp_instructions(id) ON DELETE CASCADE,
  client_id TEXT NOT NULL,
  encrypted_result TEXT,
  raw_decrypted TEXT,
  received_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_instr_client_status ON mcp_instructions(client_id, status);

-- db/schema.sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS api_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  key_id TEXT NOT NULL,              -- short public id, e.g. "ak_8F3K2M"
  secret_hash TEXT NOT NULL,         -- bcrypt/argon2 of key secret
  label TEXT,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz,
  expires_at timestamptz,
  revoked BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE(user_id, key_id)
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_keyid ON api_keys(key_id);

-- instructions queue
CREATE TABLE IF NOT EXISTS instructions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id VARCHAR(200) NOT NULL,
  command_plain TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'queued', -- queued|delivered|completed
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at TIMESTAMPTZ NULL,
  completed_at TIMESTAMPTZ NULL,
  result_cipher TEXT NULL
);

-- index to fetch next job quickly
CREATE INDEX IF NOT EXISTS idx_instructions_client_status_created
  ON instructions (client_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_instr_client_created
  ON instructions (client_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_instr_client_status
  ON instructions (client_id, status);

CREATE TABLE IF NOT EXISTS clients_seen (
  client_id    VARCHAR(200) PRIMARY KEY,
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
