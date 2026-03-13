# AIMARU MCP Platform - File Manifest

This document provides a complete inventory of all files in the GitHub release package.

## 📁 Directory Structure

### Root Directory Files

| File | Description | Required |
|------|-------------|----------|
| `README.md` | Main project documentation and quick start guide | ✅ Yes |
| `docker-compose.yml` | Docker Compose orchestration configuration | ✅ Yes |
| `Dockerfile` | API server container definition | ✅ Yes |
| `.env.example` | Environment variables template | ✅ Yes |
| `.gitignore` | Git ignore patterns | ✅ Yes |
| `requirements.txt` | Python dependencies for backend | ✅ Yes |
| `start.sh` | Quick start script | ✅ Yes |
| `start-full.sh` | Full start script with build | ✅ Yes |
| `stop.sh` | Stop all services script | ✅ Yes |
| `status.sh` | Check service status script | ✅ Yes |
| `PSMCP.ps1` | PowerShell client (version 1) | ✅ Yes |
| `PSMCP_v2.ps1` | PowerShell client (version 2 - latest) | ✅ Yes |
| `QUICK_START_AGENTIC_ITERATION.md` | Quick start guide for enhanced auto-iteration | 📖 Docs |
| `TECHNICAL_USER_GUIDE.md` | Part 1: Architecture & API Reference | 📖 Docs |
| `TECHNICAL_USER_GUIDE_PART2.md` | Part 2: Features & Operations | 📖 Docs |
| `TECHNICAL_USER_GUIDE_PART3.md` | Part 3: Security & Troubleshooting | 📖 Docs |
| `TECHNICAL_USER_GUIDE_INDEX.md` | Master documentation index | 📖 Docs |
| `FILE_MANIFEST.md` | This file - complete file inventory | 📖 Docs |

### `/api` - Backend API

| File/Folder | Description |
|-------------|-------------|
| `api/requirements.txt` | Python dependencies for FastAPI backend |
| `api/app/` | Application source code directory |
| `api/app/main.py` | FastAPI application entry point |
| `api/app/config.py` | Configuration management |
| `api/app/db.py` | Database connection and session management |
| `api/app/deps.py` | Dependency injection utilities |
| `api/app/auth_dep.py` | Authentication dependencies |
| `api/app/models.py` | SQLAlchemy database models |
| `api/app/models_mcp.py` | MCP-specific models |
| `api/app/schemas.py` | Pydantic request/response schemas |
| `api/app/security.py` | Authentication and security utilities |
| `api/app/security_api_keys.py` | API key management |
| `api/app/crypto.py` | Cryptographic functions (AES-256-GCM) |
| `api/app/crypto_runtime.py` | Runtime encryption utilities |
| `api/app/routes_auth.py` | Authentication endpoints |
| `api/app/routes_users.py` | User management endpoints |
| `api/app/routes_keys.py` | Encryption key management endpoints |
| `api/app/routes_chat.py` | **AI Chat endpoints with auto-iteration** |
| `api/app/routes_llm.py` | LLM service endpoints |
| `api/app/routes_mcp_refactored.py` | MCP protocol endpoints |
| `api/app/routes_mcp_tools.py` | MCP tools endpoints |
| `api/app/routes_client_builder.py` | PowerShell client builder endpoints |
| `api/app/routes_amsi_deployment.py` | AMSI bypass deployment endpoints |
| `api/app/routes_tools.py` | Security tools generation endpoints |
| `api/app/llm_service.py` | **OpenAI/Claude integration with auto-iteration** |
| `api/app/chat_tools.py` | Chat tool definitions for LLM |
| `api/app/mcp_service.py` | MCP service implementation |
| `api/app/mcp_api_server.py` | MCP API server |
| `api/app/mcp_middleware.py` | MCP middleware |
| `api/app/client_template_v2.py` | PowerShell client template (v2) |
| `api/app/amsi_status_tracker.py` | AMSI bypass status tracking |

### `/ui-app` - Frontend React Application

| File/Folder | Description |
|-------------|-------------|
| `ui-app/package.json` | Node.js dependencies and scripts |
| `ui-app/package-lock.json` | Locked dependency versions |
| `ui-app/tsconfig.json` | TypeScript configuration |
| `ui-app/vite.config.ts` | Vite build configuration |
| `ui-app/tailwind.config.js` | Tailwind CSS configuration |
| `ui-app/postcss.config.js` | PostCSS configuration |
| `ui-app/index.html` | HTML entry point |
| `ui-app/src/` | Source code directory |
| `ui-app/src/main.tsx` | React application entry point |
| `ui-app/src/App.tsx` | Main application component |
| `ui-app/src/api.ts` | API client functions |
| `ui-app/src/styles.css` | Global styles and Aimaru theme |
| `ui-app/src/auth/` | Authentication components |
| `ui-app/src/components/` | React UI components |
| `ui-app/src/components/Layout.tsx` | **Main layout with updated About screen** |
| `ui-app/src/pages/` | Page components |
| `ui-app/public/` | Static assets |

### `/nginx` - Nginx Reverse Proxy

| File | Description |
|------|-------------|
| `nginx/Dockerfile` | Nginx container definition |
| `nginx/nginx.conf` | Nginx configuration with SSL and reverse proxy |

### `/db` - Database

| File | Description |
|------|-------------|
| `db/schema.sql` | PostgreSQL database schema |

### `/certs` - SSL Certificates

| File | Description |
|------|-------------|
| `certs/.gitkeep` | Placeholder to keep directory in Git |
| *(user must generate)* `certs/server.key` | SSL private key |
| *(user must generate)* `certs/server.crt` | SSL certificate |

### `/AMSI` - AMSI Bypass Scripts

| File | Description |
|------|-------------|
| `AMSI/INvoke_AS4MS1_alt4.ps1` | AMSI bypass PowerShell script |

## 🔑 Critical Files for Operation

### Must Configure Before First Run:
1. `.env` - Copy from `.env.example` and add API keys
2. `certs/server.key` - Generate SSL private key
3. `certs/server.crt` - Generate SSL certificate

### Core Application Files:
1. `docker-compose.yml` - Orchestrates all services
2. `api/app/main.py` - Backend entry point
3. `ui-app/src/main.tsx` - Frontend entry point
4. `db/schema.sql` - Database structure

### Key Feature Files:
1. `api/app/routes_chat.py` - AI chat with **enhanced agentic auto-iteration**
2. `api/app/llm_service.py` - LLM integration with **5-level complexity escalation**
3. `ui-app/src/components/Layout.tsx` - UI with **updated About screen**
4. `api/app/routes_client_builder.py` - PowerShell client generator
5. `api/app/routes_amsi_deployment.py` - AMSI bypass deployment

## 📊 File Statistics

- **Total Directories**: 9
- **Python Files**: ~29
- **TypeScript/JavaScript Files**: ~15
- **Configuration Files**: 8
- **Documentation Files**: 6
- **Shell Scripts**: 4
- **PowerShell Scripts**: 3

## 🔄 Files Modified in Recent Updates

### Enhanced Agentic Auto-Iteration Implementation:
- `api/app/routes_chat.py` - Added multi-step auto-iteration (lines 253-267)
- `api/app/llm_service.py` - Enhanced with 5-level complexity escalation
- `ui-app/src/components/Layout.tsx` - Updated About screen with new features

### Documentation Updates:
- `TECHNICAL_USER_GUIDE.md` - Comprehensive Part 1 created
- `TECHNICAL_USER_GUIDE_PART2.md` - Features & Operations created
- `TECHNICAL_USER_GUIDE_PART3.md` - Security & Troubleshooting created
- `TECHNICAL_USER_GUIDE_INDEX.md` - Master index created
- `QUICK_START_AGENTIC_ITERATION.md` - Quick start guide created

## 📝 Notes

1. **Excluded from Repository** (see `.gitignore`):
   - `node_modules/` - Install via `npm install`
   - `.venv/` - Create via `python -m venv .venv`
   - `__pycache__/` - Auto-generated Python cache
   - `.env` - User-specific configuration (use `.env.example`)
   - Actual SSL certificates - Generate per deployment
   - API keys - User must provide

2. **Optional but Recommended**:
   - Create a `LICENSE` file if open-sourcing
   - Create a `CONTRIBUTING.md` for contribution guidelines
   - Create a `CHANGELOG.md` for version tracking

3. **Security Considerations**:
   - Never commit `.env` with real API keys
   - Never commit actual SSL certificates
   - Review all code before deployment
   - Change default admin password immediately

## ✅ Pre-Upload Checklist

- [x] All source code files copied
- [x] Configuration templates created
- [x] Documentation complete and up-to-date
- [x] `.gitignore` configured properly
- [x] `README.md` created with quick start
- [x] Sensitive files excluded (API keys, certs)
- [x] Scripts have correct permissions
- [x] Database schema included
- [x] Example environment file created

---

**Last Updated**: 2026-03-11
**Version**: GitHub Release v1.0
