import os

# Match docker-compose env names
PG_DSN = os.getenv("MCP_PG_DSN", "postgresql+psycopg2://mcp:mcp@postgres:5432/mcp")
JWT_SECRET = os.getenv("MCP_JWT_SECRET", "change_me_access")
REFRESH_SECRET = os.getenv("MCP_REFRESH_SECRET", "change_me_refresh")
SHARED_SECRET = os.getenv("MCP_SHARED_SECRET", "change_me_shared")
HMAC_KEY = os.getenv("MCP_HMAC_KEY", "change_me_hmac")
CORS_ORIGINS = [o.strip() for o in os.getenv("MCP_CORS_ORIGINS", "").split(",") if o.strip()]